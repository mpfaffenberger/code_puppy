"""Persist ACP session history so ``session/load`` and ``session/resume``
rehydrate real turns across process restarts.

Each session's pydantic-ai message history is pickled under a dedicated
directory keyed by the ACP session id, reusing code-puppy's existing
``session_storage`` layer. We keep it separate from the user's autosaves
(``AUTOSAVE_DIR/acp``) so ACP threads never pollute the ``/resume`` picker.

Alongside the pickle we write a small ACP metadata sidecar (``*_acp.json``)
recording the session's own ``cwd`` + ``additional_directories``. This is what
lets ``list_persisted`` surface revivable sessions after a
restart *with the ``cwd`` that ACP's ``SessionInfo`` requires* -- the pickle
alone can't answer "where did this thread live?", and ``session_storage``'s
own ``_meta.json`` records the *process* cwd, which is wrong for per-session
ACP threads.

Every public entry point takes an optional ``base_dir``: production callers
omit it (it defaults to ``AUTOSAVE_DIR/acp``), while tests pass an explicit
directory so persistence is exercised end-to-end with zero shared global
state -- no monkeypatching of a module-level location.

All operations are best-effort: persistence must never break a live turn, so
failures are logged and swallowed.
"""

from __future__ import annotations

import datetime
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PersistedSession:
    """On-disk record of an ACP session, enough to re-list + revive it."""

    session_id: str
    cwd: Optional[str] = None
    additional_directories: Optional[List[str]] = None
    updated_at: Optional[str] = None


def _base_dir() -> Path:
    from code_puppy.config import AUTOSAVE_DIR

    return Path(AUTOSAVE_DIR) / "acp"


def _resolve_base(base_dir: Optional[Path]) -> Path:
    """Return the caller's ``base_dir`` or the default ``AUTOSAVE_DIR/acp``."""
    return Path(base_dir) if base_dir is not None else _base_dir()


def _safe_name(session_id: str) -> str:
    """Sanitise a session id into a filesystem-safe pickle stem."""
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in session_id)


# Sidecar suffix for ACP-specific metadata. Distinct from ``session_storage``'s
# own ``_meta.json`` so the two never collide.
_ACP_META_SUFFIX = "_acp.json"


def _acp_meta_path(base: Path, session_id: str) -> Path:
    return base / f"{_safe_name(session_id)}{_ACP_META_SUFFIX}"


def save(
    session_id: str,
    agent: Any,
    cwd: Optional[str] = None,
    additional_directories: Optional[List[str]] = None,
    base_dir: Optional[Path] = None,
) -> None:
    """Persist ``agent``'s message history under ``session_id`` (best-effort).

    Also writes an ACP metadata sidecar carrying the session's ``cwd`` +
    ``additional_directories`` so ``list_persisted`` can surface it after a
    restart.
    """
    try:
        from code_puppy.session_storage import save_session

        base = _resolve_base(base_dir)
        history = list(agent.get_message_history())
        if not history:
            return
        timestamp = datetime.datetime.now().isoformat()
        save_session(
            history=history,
            session_name=_safe_name(session_id),
            base_dir=base,
            timestamp=timestamp,
            token_estimator=getattr(agent, "estimate_tokens_for_message", lambda _m: 0),
            auto_saved=True,
        )
        _write_acp_meta(
            base,
            PersistedSession(
                session_id=session_id,
                cwd=cwd,
                additional_directories=list(additional_directories or []) or None,
                updated_at=timestamp,
            ),
        )
    except Exception:  # noqa: BLE001
        logger.debug("ACP: session persist failed", exc_info=True)


def _write_acp_meta(base: Path, record: PersistedSession) -> None:
    """Write the ACP metadata sidecar for ``record`` (best-effort, atomic)."""
    try:
        base.mkdir(parents=True, exist_ok=True)
        path = _acp_meta_path(base, record.session_id)
        payload = {
            "session_id": record.session_id,
            "cwd": record.cwd,
            "additional_directories": record.additional_directories,
            "updated_at": record.updated_at,
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(path)
    except Exception:  # noqa: BLE001
        logger.debug("ACP: session meta persist failed", exc_info=True)


def load_history(
    session_id: str, base_dir: Optional[Path] = None
) -> Optional[List[Any]]:
    """Return the persisted history for ``session_id``, or ``None`` if none."""
    try:
        from code_puppy.session_storage import load_session

        return list(load_session(_safe_name(session_id), _resolve_base(base_dir)))
    except FileNotFoundError:
        return None
    except Exception:  # noqa: BLE001
        logger.debug("ACP: session load failed", exc_info=True)
        return None


def list_persisted(base_dir: Optional[Path] = None) -> List[PersistedSession]:
    """Return every ACP session persisted on disk (newest first).

    Reads the ACP metadata sidecars so revivable sessions survive process
    restarts. A session whose pickle vanished (only the sidecar remains) is
    skipped -- there is nothing left to rehydrate.
    """
    base = _resolve_base(base_dir)
    if not base.exists():
        return []
    records: List[PersistedSession] = []
    for meta_path in base.glob(f"*{_ACP_META_SUFFIX}"):
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            session_id = data.get("session_id")
            if not session_id:
                continue
            if not (base / f"{_safe_name(session_id)}.pkl").exists():
                continue
            records.append(
                PersistedSession(
                    session_id=session_id,
                    cwd=data.get("cwd"),
                    additional_directories=data.get("additional_directories"),
                    updated_at=data.get("updated_at"),
                )
            )
        except Exception:  # noqa: BLE001
            logger.debug("ACP: skipping unreadable session meta", exc_info=True)
    records.sort(key=lambda r: r.updated_at or "", reverse=True)
    return records


def delete(session_id: str, base_dir: Optional[Path] = None) -> None:
    """Remove a persisted session's pickle + sidecars (best-effort).

    Called when a client explicitly closes a session so a deliberate close
    doesn't leave a ghost that reappears in the next ``list_sessions``.
    """
    try:
        base = _resolve_base(base_dir)
        stem = _safe_name(session_id)
        for path in (
            base / f"{stem}.pkl",
            base / f"{stem}_meta.json",
            _acp_meta_path(base, session_id),
        ):
            path.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        logger.debug("ACP: session delete failed", exc_info=True)
