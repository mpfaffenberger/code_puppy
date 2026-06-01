"""Shared helpers for persisting and restoring chat sessions.

MIGRATION NOTE: Pickle-based storage has been removed. All sessions are now
persisted exclusively to SQLite via code_puppy.api.db.queries.
This module retains only stateless helpers (title generation) and stubs for
removed functionality to maintain import compatibility during the transition.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List

from pydantic import TypeAdapter
from pydantic_ai.messages import ModelMessage

SessionHistory = List[Any]


@dataclass
class SessionMetadata:
    """Metadata returned after saving a session."""

    message_count: int
    total_tokens: int
    pickle_path: Path  # Kept for compatibility, points to .json file
    metadata_path: Path  # Points to .json file (same as above)


def generate_heuristic_title(history: SessionHistory, max_length: int = 50) -> str:
    """Generate a short title from the first user message in the history.

    Extracts the first user message, takes the first ~50 chars, and converts
    to a filename-safe format (lowercase, spaces to hyphens, remove special chars).

    Handles multiple message formats:
    1. Pydantic-ai format: msg.kind == 'request' with msg.parts[].content
    2. Enhanced/wrapped format: {'msg': <pydantic-ai message>, 'agent': str, ...}
    3. Simple dict format: {'role': 'user', 'content': str}
    """

    def extract_user_content(msg: Any) -> str | None:
        """Extract user message content from various message formats."""
        # Handle wrapped/enhanced format: {'msg': <actual message>, 'agent': ...}
        if isinstance(msg, dict) and "msg" in msg:
            msg = msg["msg"]

        # Handle pydantic-ai format: msg.kind == 'request'
        if hasattr(msg, "kind") and msg.kind == "request":
            for part in getattr(msg, "parts", []):
                if hasattr(part, "content") and isinstance(part.content, str):
                    content = part.content.strip()
                    if content:
                        return content

        # Handle simple dict format: {'role': 'user', 'content': str}
        if isinstance(msg, dict):
            if msg.get("role") == "user" and isinstance(msg.get("content"), str):
                content = msg["content"].strip()
                if content:
                    return content

        return None

    def content_to_title(content: str) -> str:
        """Convert content to a filename-safe kebab-case title."""
        # Take first line or first max_length chars
        first_line = content.split("\n")[0][:max_length]
        # Convert to kebab-case filename-safe format
        title = first_line.lower()
        title = re.sub(r"[^a-z0-9\s-]", "", title)  # Remove special chars
        title = re.sub(r"\s+", "-", title)  # Spaces to hyphens
        title = re.sub(r"-+", "-", title)  # Collapse multiple hyphens
        title = title.strip("-")[:max_length]
        return title

    # Find first user message
    for msg in history:
        content = extract_user_content(msg)
        if content:
            title = content_to_title(content)
            return title if title else "untitled-session"

    return "untitled-session"


# ---------------------------------------------------------------------------
# Deprecated / Removed Pickle Functionality -> Replaced with JSON for Export
# ---------------------------------------------------------------------------


def save_session(
    history: SessionHistory,
    session_name: str,
    base_dir: Path,
    timestamp: str | None = None,
    token_estimator: Any | None = None,
    **kwargs: Any,
) -> SessionMetadata:
    """Save session history to a JSON file (replacing legacy pickle).

    This is used for 'pinning' or exporting sessions via /dump_context.
    """
    base_dir.mkdir(parents=True, exist_ok=True)
    file_path = base_dir / f"{session_name}.json"

    # Try to serialize the history, handling mixed types:
    # - ModelMessage objects: serialize via Pydantic
    # - System dicts: serialize as plain dicts
    try:
        from pydantic_ai.messages import ModelMessagesTypeAdapter

        history_data = []
        for item in history:
            # Unwrap from {msg: ..., agent: ..., ts: ...} wrapper if present
            if isinstance(item, dict) and "msg" in item:
                inner = item["msg"]
                wrapper_meta = {k: v for k, v in item.items() if k != "msg"}

                # Check if inner is a ModelMessage (has 'parts' attribute)
                if hasattr(inner, "parts"):
                    # Serialize ModelMessage, then add wrapper metadata
                    try:
                        serialized = ModelMessagesTypeAdapter.dump_python(
                            [inner], mode="json"
                        )[0]
                        serialized["_wrapper"] = wrapper_meta
                        history_data.append(serialized)
                    except Exception:
                        # Fallback: keep as-is
                        history_data.append(item)
                else:
                    # It's a system dict like {msg: 'system', ...} - keep as-is
                    history_data.append(item)
            elif hasattr(item, "parts"):
                # Direct ModelMessage without wrapper
                try:
                    serialized = ModelMessagesTypeAdapter.dump_python(
                        [item], mode="json"
                    )[0]
                    history_data.append(serialized)
                except Exception:
                    history_data.append({"_raw": str(item)})
            else:
                # Unknown type - keep as-is
                history_data.append(item)

        json_bytes = json.dumps(history_data, indent=2, default=str).encode("utf-8")
    except Exception:
        # Fallback: generic JSON dump
        json_bytes = json.dumps(history, default=str, indent=2).encode("utf-8")

    file_path.write_bytes(json_bytes)

    # Calculate tokens if estimator provided
    total_tokens = 0
    if token_estimator:
        for msg in history:
            try:
                # estimator might expect the original object or dict
                total_tokens += token_estimator(msg)
            except Exception:
                pass

    return SessionMetadata(
        message_count=len(history),
        total_tokens=total_tokens,
        pickle_path=file_path,
        metadata_path=file_path,
    )


def load_session(
    session_name: str, base_dir: Path, *, allow_legacy: bool = False
) -> SessionHistory:
    """Load session history from a JSON file."""
    file_path = base_dir / f"{session_name}.json"
    if not file_path.exists():
        # Fallback check for legacy .pkl if explicitly requested?
        legacy_path = base_dir / f"{session_name}.pkl"
        if allow_legacy and legacy_path.exists():
            raise NotImplementedError(
                f"Found legacy pickle at {legacy_path} but pickle loading is removed."
            )
        raise FileNotFoundError(f"Session file not found: {file_path}")

    json_data = file_path.read_bytes()

    # Try to load as ModelMessage objects
    try:
        adapter = TypeAdapter(List[ModelMessage])
        return adapter.validate_json(json_data)
    except Exception:
        # Fallback: return as list of dicts
        return json.loads(json_data)


def list_sessions(base_dir: Path) -> List[str]:
    """List available JSON sessions."""
    if not base_dir.exists():
        return []
    return sorted([p.stem for p in base_dir.glob("*.json")])


def cleanup_sessions(base_dir: Path, max_sessions: int) -> List[str]:
    """Cleanup old sessions if count exceeds max_sessions.

    Returns list of removed session names.
    """
    if not base_dir.exists() or max_sessions <= 0:
        return []

    sessions = sorted(base_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)

    removed = []
    if len(sessions) > max_sessions:
        to_remove = sessions[: len(sessions) - max_sessions]
        for p in to_remove:
            try:
                p.unlink()
                removed.append(p.stem)
            except Exception:
                pass

    return removed


async def restore_autosave_interactively(base_dir: Path) -> None:
    """Deprecated: No-op."""
    pass


def build_session_paths(base_dir: Path, session_name: str) -> Any:
    """Deprecated: Returns None or raises."""
    raise NotImplementedError("Session paths are no longer used.")
