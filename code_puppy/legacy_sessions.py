"""Code Puppy 0.0.x sessions as an import source for ``/resume``.

The runtime already imports Claude Code and Codex sessions: they are listed in
the ``/resume`` browser beside its own, and one is copied into ``sessions.db``
the moment it is picked. This module describes 0.0.x sessions to that same
machinery, so they show up there too and ``/resume puppy`` lists only them.

Nothing is converted up front and nothing on disk is modified. 0.0.x wrote one
``<name>.json`` envelope per session, holding pydantic-ai messages, with a
``<name>_meta.json`` sidecar for the title and the directory it ran in.

An imported history is cleaned of what belonged to the old harness (system
prompts, per-request instructions, a dangling final tool call) and framed with
notes telling the model that the tools it sees in it are gone.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
)
from pydantic_ai_pax.runtime.imported_history import Header, framed, title_text

from code_puppy import identity
from code_puppy.migrate.sources import read_json_object

SOURCE = "puppy"
"""What ``/resume puppy`` names, and the tag an imported session carries."""
LABEL = "Code Puppy 0.0.x"

SIDECAR_SUFFIXES = ("_meta", "_acp")
ENCODING_MESSAGES = "pydantic-ai-messages"
HARNESS_PART_KINDS = frozenset({"system-prompt", "instruction-baseline"})
"""Request parts that carried the old harness's prompt rather than conversation."""

OPENING = (
    "This conversation was imported from Code Puppy 0.0.x session {session_id}. Up to the "
    "note at its end, it ran in the previous Code Puppy harness: the tool calls in it (such "
    "as agent_run_shell_command, list_files, read_file, replace_in_file, create_file and "
    "invoke_agent) and the context it added are that harness's."
)
CLOSING = (
    "The conversation above was imported from Code Puppy 0.0.x and continues here in Code "
    "Puppy 1.0, a different harness. The tools, context and instructions above came from the "
    "previous harness and no longer apply: use the tools and instructions you have now, whose "
    "names and arguments may differ."
)


def home() -> Path:
    """Where 0.0.x autosaved its sessions."""
    return identity.cache_dir() / "autosaves"


def is_session_file(path: Path) -> bool:
    return path.suffix == ".json" and not path.stem.endswith(SIDECAR_SUFFIXES)


def files(root: Path) -> list[Path]:
    """Every session envelope in ``root``; sidecars are not sessions."""
    try:
        return [path for path in root.iterdir() if is_session_file(path)]
    except OSError:
        return []


def find(root: Path, native_id: str) -> Path | None:
    """The session 0.0.x called ``native_id``, if it is still on disk."""
    if not native_id or Path(native_id).name != native_id:
        return None
    path = root / f"{native_id}.json"
    return path if is_session_file(path) and path.is_file() else None


def titles(root: Path) -> dict[str, str]:
    """Titles live in each session's sidecar, which ``header`` reads when it is listed."""
    return {}


def _fallback_title(meta: dict[str, Any], native_id: str) -> str:
    try:
        when = datetime.fromisoformat(str(meta.get("timestamp", "")))
    except ValueError:
        return native_id
    return f"Session from {when:%Y-%m-%d %H:%M}"


def header(path: Path) -> Header | None:
    """What the browser shows, from the small sidecar rather than the transcript."""
    meta = read_json_object(path.with_name(f"{path.stem}_meta.json"))
    title = meta.get("title")
    named = isinstance(title, str) and bool(title.strip())
    scope = meta.get("scope_key")
    count = meta.get("message_count")
    return Header(
        native_id=path.stem,
        # 0.0.x's scope key is the resolved directory the session ran in.
        cwd=scope if isinstance(scope, str) and scope else str(Path.home()),
        title=title_text(title if named else _fallback_title(meta, path.stem)),
        named=named,
        # An empty session can still be imported by ID, but is not worth a row.
        listed=not (isinstance(count, int) and count == 0),
    )


def _without_harness(message: ModelMessage) -> ModelMessage | None:
    """``message`` without the old harness's prompt, or ``None`` when nothing else is left."""
    if not isinstance(message, ModelRequest):
        return message if message.parts else None
    parts = [part for part in message.parts if part.part_kind not in HARNESS_PART_KINDS]
    if not parts:
        return None
    return replace(message, parts=parts, instructions=None)


def clean(history: list[ModelMessage]) -> list[ModelMessage]:
    """The conversation itself: no old prompts, and no tool call left unanswered at the end.

    A session interrupted mid-turn ends on a response whose tool calls never
    got results. A provider rejects that once another message follows it.
    """
    kept = [
        cleaned
        for message in history
        if (cleaned := _without_harness(message)) is not None
    ]
    while (
        kept
        and isinstance(last := kept[-1], ModelResponse)
        and any(isinstance(part, ToolCallPart) for part in last.parts)
    ):
        kept.pop()
    return kept


def messages(path: Path) -> list[ModelMessage]:
    """The session's history as the runtime continues it. Blocking file IO."""
    envelope = read_json_object(path)
    if envelope.get("encoding") != ENCODING_MESSAGES:
        return []
    history = ModelMessagesTypeAdapter.validate_python(envelope.get("messages") or [])
    opening = OPENING.format(session_id=path.stem)
    return framed(clean(history), source=SOURCE, opening=opening, closing=CLOSING)


def tasks(path: Path, conversation_id: str) -> list[Any]:
    """0.0.x sub-agent transcripts are not carried over."""
    return []
