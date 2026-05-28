"""Seed ~/.puppy_desk/chat_messages.db from existing pkl session files.

Scans both:
  ~/.code_puppy/ws_sessions/   — live WS sessions (HMAC-signed pickle)
  ~/.code_puppy/autosaves/     — CLI autosave sessions (raw or legacy-signed pickle)

For each .pkl file not already in the DB:
  1. Deserialises the pickle natively (no subprocess, no JSON round-trip)
  2. Serialises each ModelMessage with ModelMessagesTypeAdapter.dump_json()
     → stored verbatim in the pydantic_json column for perfect replay
  3. Extracts display fields (role, content, thinking, tool calls) from message parts
  4. Writes session + messages + tool_calls in a single transaction

Idempotent: existing sessions are skipped.  Safe to call on every startup.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import pickle
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from code_puppy.api.db.message_utils import (
    extract_content,
    extract_thinking,
    get_message_timestamp,
    get_role,
    pydantic_json_for_message,
)

logger = logging.getLogger(__name__)
# ---------------------------------------------------------------------------
# One-time migration marker — written after a successful complete seed.
# On subsequent startups the seeder skips entirely (no more pkl to import).
# ---------------------------------------------------------------------------
_SEEDER_DONE_MARKER = Path("~/.puppy_desk/.seeder_migration_done").expanduser()


# ---------------------------------------------------------------------------
# Legacy pickle header constants (from session_storage.py)
# ---------------------------------------------------------------------------

_LEGACY_SIGNED_HEADER = b"CPSESSION\x01"
_LEGACY_SIGNATURE_SIZE = 32


def _get_hmac_key() -> bytes:
    """Return HMAC key for verifying WS session pickle files.

    Copied from session_context to make seeder.py self-contained after
    _get_hmac_key was removed from session_context in desk-puppy-cr1x.
    """
    import os

    key_env = os.environ.get("CODE_PUPPY_SESSION_KEY", "")
    if key_env:
        return key_env.encode()
    # Fall back to a machine-stable key derived from the DB path
    db_path = str(Path("~/.puppy_desk/chat_messages.db").expanduser())
    return db_path.encode()


def _extract_pickle_payload(raw: bytes) -> bytes:
    """Strip legacy or new-format prefix and return the raw pickle bytes."""
    if raw.startswith(_LEGACY_SIGNED_HEADER):
        offset = len(_LEGACY_SIGNED_HEADER) + _LEGACY_SIGNATURE_SIZE
        return raw[offset:]
    return raw


def _verify_and_load_ws_pickle(raw: bytes, hmac_key: bytes) -> Optional[list[Any]]:
    """Load a WS session pickle after HMAC verification.

    WS session pkls are written by session_context.py:
        file = 32-byte-HMAC-SHA256 + pickle(history)

    Returns None if verification fails or the file is too small.
    """
    if len(raw) < 33:  # 32-byte sig + at least 1 byte of pickle
        return None
    sig, blob = raw[:32], raw[32:]
    expected = hmac.new(hmac_key, blob, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        logger.warning("HMAC verification failed — skipping")
        return None
    try:
        data = pickle.loads(blob)  # noqa: S301
        return data if isinstance(data, list) else None
    except Exception as exc:
        logger.warning("Pickle load error: %s", exc)
        return None


def _load_autosave_pickle(raw: bytes) -> Optional[list[Any]]:
    """Load an autosave pickle (no HMAC — strip legacy header if present)."""
    payload = _extract_pickle_payload(raw)
    try:
        data = pickle.loads(payload)  # noqa: S301
        return data if isinstance(data, list) else None
    except Exception as exc:
        logger.warning("Autosave pickle load error: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Message part extraction helpers (content/thinking/role moved to message_utils)
# ---------------------------------------------------------------------------

_PART_TYPE_TOOL_CALL = {"ToolCallPart"}
_PART_TYPE_TOOL_RETURN = {"ToolReturnPart"}


def _extract_tool_calls(msg: Any) -> list[dict[str, Any]]:
    """Extract ToolCallPart entries from a ModelResponse."""
    parts = getattr(msg, "parts", [])
    result = []
    for part in parts:
        if type(part).__name__ not in _PART_TYPE_TOOL_CALL:
            continue
        args = getattr(part, "args", {})
        if hasattr(args, "model_dump"):
            args = args.model_dump()
        elif hasattr(args, "__dict__"):
            args = dict(args.__dict__)
        result.append(
            {
                "id": getattr(part, "tool_call_id", "") or str(uuid.uuid4()),
                "name": getattr(part, "tool_name", "unknown"),
                "args": args,
            }
        )
    return result


def _extract_tool_returns(msg: Any) -> list[dict[str, Any]]:
    """Extract ToolReturnPart entries from a ModelRequest."""
    parts = getattr(msg, "parts", [])
    result = []
    for part in parts:
        if type(part).__name__ not in _PART_TYPE_TOOL_RETURN:
            continue
        content = getattr(part, "content", "")
        try:
            result_val = json.loads(content) if isinstance(content, str) else content
        except Exception:
            result_val = content
        result.append(
            {
                "id": getattr(part, "tool_call_id", ""),
                "name": getattr(part, "tool_name", "unknown"),
                "result": result_val,
            }
        )
    return result


def _get_timestamp(msg: Any, wrapper: Optional[dict], fallback: str) -> str:
    """Best-effort timestamp extraction."""
    # Try wrapper ts first
    if wrapper:
        ts = wrapper.get("ts", "")
        if ts:
            return str(ts)
    # Try message-level timestamp
    ts_attr_result = get_message_timestamp(msg)
    if ts_attr_result is not None:
        return ts_attr_result
    return fallback


# ---------------------------------------------------------------------------
# Per-session import
# ---------------------------------------------------------------------------

_SESSION_CONTEXT_RE = re.compile(r"^\[Session Context:[^\]]*\]\n\n?")


def _strip_session_context(raw: str) -> Optional[str]:
    cleaned = _SESSION_CONTEXT_RE.sub("", raw).lstrip()
    return cleaned if cleaned != raw else None


async def _import_session(
    session_id: str,
    history: list[Any],
    meta: dict[str, Any],
    now_iso: str,
) -> int:
    """Write one session and all its messages/tool_calls to the DB.

    Returns the number of message rows written.
    """
    from code_puppy.api.db.queries import (
        insert_messages_batch,
        insert_tool_calls_batch,
        upsert_session,
    )

    created_at = meta.get("timestamp") or now_iso
    title = meta.get("title", "")
    agent_name = meta.get("agent_name", "code-puppy")
    model_name = meta.get("model_name", "")
    working_directory = meta.get("working_directory", "")
    pinned = bool(meta.get("pinned", False))
    total_tokens = meta.get("total_tokens", 0)

    await upsert_session(
        session_id=session_id,
        title=title,
        agent_name=agent_name,
        model_name=model_name,
        working_directory=working_directory,
        pinned=pinned,
        created_at=created_at,
        updated_at=created_at,
        message_count=len(history),
        total_tokens=total_tokens,
        deleted_at=None,
    )

    message_rows: list[dict[str, Any]] = []
    tool_call_rows: list[dict[str, Any]] = []
    seq = 0
    # Track pending tool calls by id for result matching
    pending_tool_calls: dict[str, dict[str, Any]] = {}

    for item in history:
        # ---- Unwrap the item ----------------------------------------
        wrapper: Optional[dict] = None
        msg: Any

        if isinstance(item, dict) and item.get("msg") == "system":
            # System message in WS format: {'msg': 'system', 'content': ..., 'path': ...}
            seq += 1
            message_rows.append(
                {
                    "session_id": session_id,
                    "seq": seq,
                    "role": "system",
                    "content": item.get("content", ""),
                    "type": "system",
                    "agent_name": item.get("agent", agent_name),
                    "model_name": item.get("model", model_name),
                    "timestamp": item.get("ts", now_iso),
                    "system_message_type": item.get("system_message_type", ""),
                    "system_message_path": item.get("path", ""),
                    "pydantic_json": None,
                    "token_count": 0,
                }
            )
            continue

        if isinstance(item, dict) and "msg" in item:
            wrapper = item
            msg = item["msg"]
        else:
            msg = item

        # ---- Skip if not a pydantic-ai message ----------------------
        if not hasattr(msg, "parts"):
            continue

        role = get_role(msg)
        ts = _get_timestamp(msg, wrapper, now_iso)
        content = extract_content(msg)
        thinking = extract_thinking(msg)
        pydantic_json = pydantic_json_for_message(msg)

        msg_agent = wrapper.get("agent", agent_name) if wrapper else agent_name
        msg_model = wrapper.get("model", model_name) if wrapper else model_name

        # clean_content: strip [Session Context: ...] for user messages
        clean_content: Optional[str] = None
        raw_clean = wrapper.get("clean_content") if wrapper else None
        if raw_clean:
            clean_content = raw_clean
        elif role == "user" and content:
            clean_content = _strip_session_context(content)

        # attachments_json
        attachments = wrapper.get("attachments") if wrapper else None
        attachments_json = json.dumps(attachments) if attachments else None

        seq += 1
        message_seq = seq

        # ---- Estimate token count (simple char/4 heuristic) ---------
        token_count = max(1, len(content) // 4)

        message_rows.append(
            {
                "session_id": session_id,
                "seq": message_seq,
                "role": role,
                "content": content,
                "type": type(msg).__name__,
                "agent_name": msg_agent,
                "model_name": msg_model,
                "timestamp": ts,
                "thinking": thinking,
                "attachments_json": attachments_json,
                "clean_content": clean_content,
                "pydantic_json": pydantic_json,
                "token_count": token_count,
            }
        )

        # ---- Tool calls from assistant messages ---------------------
        if role == "assistant":
            for tc in _extract_tool_calls(msg):
                pending_tool_calls[tc["id"]] = {
                    "tc_id": tc["id"],
                    "name": tc["name"],
                    "args": tc["args"],
                    "parent_seq": message_seq,
                    "agent": msg_agent,
                    "model": msg_model,
                    "ts": ts,
                }

        # ---- Tool returns from user messages (Anthropic API format) -
        if role == "user":
            for tr in _extract_tool_returns(msg):
                tid = tr["id"]
                if tid in pending_tool_calls:
                    tc = pending_tool_calls.pop(tid)
                    seq += 1
                    try:
                        args_json = json.dumps(tc["args"])
                    except Exception:
                        args_json = str(tc["args"])
                    # Serialize result - handle Pydantic models and complex objects
                    result_val = tr["result"]
                    try:
                        if hasattr(result_val, "model_dump"):
                            result_json = json.dumps(result_val.model_dump())
                        elif hasattr(result_val, "dict"):
                            result_json = json.dumps(result_val.dict())
                        elif hasattr(result_val, "__dict__"):
                            result_json = json.dumps(vars(result_val))
                        else:
                            result_json = json.dumps(result_val)
                    except Exception:
                        try:
                            result_json = json.dumps(str(result_val))
                        except Exception:
                            result_json = json.dumps({"raw": str(result_val)})

                    tool_ts_str = tc.get("ts", ts)
                    try:
                        tool_ts = datetime.fromisoformat(
                            str(tool_ts_str).replace("Z", "+00:00")
                        ).timestamp()
                    except Exception:
                        tool_ts = time.time()

                    tool_call_rows.append(
                        {
                            "id": tid,
                            "session_id": session_id,
                            "parent_message_seq": tc["parent_seq"],
                            "seq": seq,
                            "tool_name": tc["name"],
                            "args_json": args_json,
                            "result_json": result_json,
                            "status": "success",
                            "agent_name": tc["agent"],
                            "model_name": tc["model"],
                            "timestamp": tool_ts,
                        }
                    )

    # Write everything in batches (each batch uses its own transaction)
    await insert_messages_batch(message_rows)
    await insert_tool_calls_batch(tool_call_rows)
    return len(message_rows)


# ---------------------------------------------------------------------------
# Directory scanners
# ---------------------------------------------------------------------------


def _load_meta(meta_path: Path) -> dict[str, Any]:
    try:
        if meta_path.exists():
            return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


async def _seed_directory(
    sessions_dir: Path,
    is_ws: bool,
    hmac_key: Optional[bytes],
    now_iso: str,
) -> tuple[int, int, int]:
    """Seed all pkl files from *sessions_dir*. Returns (imported, skipped, failed)."""
    from code_puppy.api.db.queries import session_exists

    if not sessions_dir.exists():
        logger.debug("Sessions dir not found, skipping: %s", sessions_dir)
        return 0, 0, 0

    pkl_files = sorted(sessions_dir.glob("*.pkl"))
    total = len(pkl_files)
    if total == 0:
        return 0, 0, 0

    imported = skipped = failed = 0
    width = len(str(total))

    for i, pkl_path in enumerate(pkl_files, 1):
        session_id = pkl_path.stem

        # Skip tiny files (HMAC-only stubs, empty autosaves)
        try:
            if pkl_path.stat().st_size < 50:
                skipped += 1
                continue
        except OSError:
            skipped += 1
            continue

        if await session_exists(session_id):
            skipped += 1
            continue

        try:
            raw = pkl_path.read_bytes()
        except OSError as exc:
            logger.warning(
                "[%*d/%d] %s — read error: %s", width, i, total, session_id, exc
            )
            failed += 1
            continue

        # Deserialise
        if is_ws and hmac_key is not None:
            history = _verify_and_load_ws_pickle(raw, hmac_key)
        else:
            history = _load_autosave_pickle(raw)

        if not history:
            skipped += 1
            continue

        # Load metadata
        meta_path = pkl_path.with_name(f"{session_id}_meta.json")
        meta = _load_meta(meta_path)

        try:
            n = await _import_session(session_id, history, meta, now_iso)
            logger.info(
                "[%*d/%d] %-50s  %4d msgs  — imported",
                width,
                i,
                total,
                session_id,
                n,
            )
            imported += 1
        except Exception as exc:
            logger.error(
                "[%*d/%d] %s — import error: %s",
                width,
                i,
                total,
                session_id,
                exc,
                exc_info=True,
            )
            failed += 1

    return imported, skipped, failed


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def seed_from_pkl_dirs() -> None:
    """Asynchronously seed the DB from both ws_sessions and autosaves directories.

    All database operations go through the shared aiosqlite connection so this
    must run on the event loop that owns the DB connection.  File I/O for
    reading pickle files is blocking but acceptable at startup since the seeder
    runs as a background asyncio.create_task().

    Safe to call on every startup — already-imported sessions are skipped.
    """
    # One-time migration guard: if we already migrated all pkl files, skip.
    if _SEEDER_DONE_MARKER.exists():
        logger.debug("Seeder already completed (marker found) — skipping pkl scan")
        return

    from code_puppy.config import AUTOSAVE_DIR, WS_SESSION_DIR

    now_iso = datetime.now(timezone.utc).isoformat()

    # ---- WS sessions (HMAC-signed) -----------------------------------
    ws_dir = Path(WS_SESSION_DIR)
    hmac_key: Optional[bytes] = None
    try:
        hmac_key = _get_hmac_key()
    except Exception as exc:
        logger.warning("Could not load HMAC key, WS sessions will be skipped: %s", exc)

    if hmac_key is not None:
        logger.info("Seeding WS sessions from %s ...", ws_dir)
        wi, ws, wf = await _seed_directory(
            ws_dir, is_ws=True, hmac_key=hmac_key, now_iso=now_iso
        )
        logger.info("WS sessions: %d imported, %d skipped, %d failed", wi, ws, wf)
    else:
        wi = ws = wf = 0

    # ---- Autosaves (no HMAC) -----------------------------------------
    auto_dir = Path(AUTOSAVE_DIR)
    logger.info("Seeding autosave sessions from %s ...", auto_dir)
    ai, as_, af = await _seed_directory(
        auto_dir, is_ws=False, hmac_key=None, now_iso=now_iso
    )
    logger.info("Autosave sessions: %d imported, %d skipped, %d failed", ai, as_, af)

    total_imported = wi + ai
    total_skipped = ws + as_
    total_failed = wf + af
    logger.info(
        "\u2713 Seeding complete: %d imported, %d skipped, %d failed",
        total_imported,
        total_skipped,
        total_failed,
    )

    # Write the one-time migration marker if seed succeeded with no failures.
    if total_failed == 0:
        try:
            _SEEDER_DONE_MARKER.parent.mkdir(parents=True, exist_ok=True)
            _SEEDER_DONE_MARKER.write_text(
                f"Seeder migration completed. imported={total_imported} skipped={total_skipped}\n"
            )
            logger.info("✓ Seeder migration marker written to %s", _SEEDER_DONE_MARKER)
        except Exception as exc:
            logger.warning("Could not write seeder marker: %s", exc)
