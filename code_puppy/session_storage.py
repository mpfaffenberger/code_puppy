"""Shared helpers for persisting and restoring JSON chat sessions.

All session export/autosave helpers now use JSON files. Pickle compatibility
and legacy path shims have been removed from active runtime code.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List


SessionHistory = List[Any]


@dataclass(slots=True)
class SessionMetadata:
    """Metadata returned after saving a session export/autosave."""

    message_count: int
    total_tokens: int
    session_file_path: Path


def get_session_file_path(base_dir: Path, session_name: str) -> Path:
    """Return the canonical JSON session file path for *session_name*."""
    return base_dir / f"{session_name}.json"


def generate_heuristic_title(history: SessionHistory, max_length: int = 50) -> str:
    """Generate a short title from the first user message in the history."""

    def extract_user_content(msg: Any) -> str | None:
        if isinstance(msg, dict) and "msg" in msg:
            msg = msg["msg"]

        if hasattr(msg, "kind") and msg.kind == "request":
            for part in getattr(msg, "parts", []):
                if hasattr(part, "content") and isinstance(part.content, str):
                    content = part.content.strip()
                    if content:
                        return content

        if isinstance(msg, dict):
            if msg.get("role") == "user" and isinstance(msg.get("content"), str):
                content = msg["content"].strip()
                if content:
                    return content

        return None

    def content_to_title(content: str) -> str:
        first_line = content.split("\n")[0][:max_length]
        title = first_line.lower()
        title = re.sub(r"[^a-z0-9\s-]", "", title)
        title = re.sub(r"\s+", "-", title)
        title = re.sub(r"-+", "-", title)
        title = title.strip("-")[:max_length]
        return title

    for msg in history:
        content = extract_user_content(msg)
        if content:
            title = content_to_title(content)
            return title if title else "untitled-session"

    return "untitled-session"


def save_session(
    history: SessionHistory,
    session_name: str,
    base_dir: Path,
    timestamp: str | None = None,
    token_estimator: Any | None = None,
    **kwargs: Any,
) -> SessionMetadata:
    """Save session history to a JSON file."""
    del timestamp, kwargs

    base_dir.mkdir(parents=True, exist_ok=True)
    file_path = get_session_file_path(base_dir, session_name)

    try:
        from pydantic_ai.messages import ModelMessagesTypeAdapter

        if history and all(hasattr(item, "parts") for item in history):
            json_bytes = ModelMessagesTypeAdapter.dump_json(history, indent=2)
        else:
            history_data = []
            for item in history:
                if isinstance(item, dict) and "msg" in item:
                    inner = item["msg"]
                    wrapper_meta = {k: v for k, v in item.items() if k != "msg"}
                    if hasattr(inner, "parts"):
                        try:
                            serialized = ModelMessagesTypeAdapter.dump_python(
                                [inner], mode="json"
                            )[0]
                            serialized["_wrapper"] = wrapper_meta
                            history_data.append(serialized)
                        except Exception:
                            history_data.append(item)
                    else:
                        history_data.append(item)
                elif hasattr(item, "parts"):
                    try:
                        serialized = ModelMessagesTypeAdapter.dump_python(
                            [item], mode="json"
                        )[0]
                        history_data.append(serialized)
                    except Exception:
                        history_data.append({"_raw": str(item)})
                else:
                    history_data.append(item)

            json_bytes = json.dumps(history_data, indent=2, default=str).encode("utf-8")
    except Exception:
        json_bytes = json.dumps(history, default=str, indent=2).encode("utf-8")

    file_path.write_bytes(json_bytes)

    total_tokens = 0
    if token_estimator:
        for msg in history:
            try:
                total_tokens += token_estimator(msg)
            except Exception:
                pass

    return SessionMetadata(
        message_count=len(history),
        total_tokens=total_tokens,
        session_file_path=file_path,
    )


def load_session(session_name: str, base_dir: Path) -> SessionHistory:
    """Load session history from a JSON file."""
    file_path = get_session_file_path(base_dir, session_name)
    if not file_path.exists():
        raise FileNotFoundError(f"Session file not found: {file_path}")

    json_data = file_path.read_bytes()

    try:
        from pydantic_ai.messages import ModelMessagesTypeAdapter

        return ModelMessagesTypeAdapter.validate_json(json_data)
    except Exception:
        raw = json.loads(json_data)

    if not isinstance(raw, list):
        return raw

    try:
        from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart
        from pydantic_ai.usage import RequestUsage

        restored: list[Any] = []
        for item in raw:
            wrapper = None
            if isinstance(item, dict):
                wrapper = item.pop("_wrapper", None)

            if isinstance(item, dict) and item.get("kind") in {"request", "response"}:
                parts = []
                for part in item.get("parts", []):
                    if isinstance(part, dict) and part.get("part_kind") == "text":
                        parts.append(
                            TextPart(
                                content=part.get("content", ""),
                                id=part.get("id"),
                                provider_details=part.get("provider_details"),
                            )
                        )
                    else:
                        parts.append(part)

                if item.get("kind") == "request":
                    msg = ModelRequest(
                        parts=parts,
                        instructions=item.get("instructions"),
                        run_id=item.get("run_id"),
                        metadata=item.get("metadata"),
                    )
                else:
                    usage_data = item.get("usage") or {}
                    timestamp = item.get("timestamp")
                    if isinstance(timestamp, str):
                        timestamp = datetime.fromisoformat(
                            timestamp.replace("Z", "+00:00")
                        )
                    msg = ModelResponse(
                        parts=parts,
                        usage=RequestUsage(**usage_data),
                        model_name=item.get("model_name"),
                        timestamp=timestamp or datetime.now().astimezone(),
                        provider_name=item.get("provider_name"),
                        provider_details=item.get("provider_details"),
                        provider_response_id=item.get("provider_response_id"),
                        finish_reason=item.get("finish_reason"),
                        run_id=item.get("run_id"),
                        metadata=item.get("metadata"),
                    )

                restored.append(
                    {**wrapper, "msg": msg} if isinstance(wrapper, dict) else msg
                )
            else:
                restored.append(item)

        return restored
    except Exception:
        return raw


def list_sessions(base_dir: Path) -> List[str]:
    """List available JSON sessions."""
    if not base_dir.exists():
        return []
    return sorted(path.stem for path in base_dir.glob("*.json"))


def cleanup_sessions(base_dir: Path, max_sessions: int) -> List[str]:
    """Cleanup old sessions if count exceeds *max_sessions*."""
    if not base_dir.exists() or max_sessions <= 0:
        return []

    sessions = sorted(base_dir.glob("*.json"), key=lambda path: path.stat().st_mtime)
    removed: list[str] = []
    if len(sessions) > max_sessions:
        for path in sessions[: len(sessions) - max_sessions]:
            try:
                path.unlink()
                removed.append(path.stem)
            except Exception:
                pass
    return removed


async def restore_autosave_interactively(base_dir: Path) -> None:
    """Deprecated compatibility shim retained as a no-op."""
    del base_dir
