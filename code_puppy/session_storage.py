"""Shared helpers for persisting and restoring chat sessions.

Sessions are stored as a versioned JSON envelope (``<name>.json``) with a
``<name>_meta.json`` metadata sidecar. The message payload is serialized via
pydantic-ai's ``ModelMessagesTypeAdapter`` so it survives library upgrades
(unlike the pickle format it replaced). Legacy ``<name>.pkl`` files are
lazily migrated on load via :mod:`code_puppy.session_format_migration`.
"""

from __future__ import annotations

import importlib.metadata
import json
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, List, Tuple

_LEGACY_SIGNED_HEADER = b"CPSESSION\x01"
_LEGACY_SIGNATURE_SIZE = (
    32  # legacy signature bytes, retained only for backward-compat parsing
)

# Current on-disk envelope version. Bump when the envelope shape changes.
SESSION_FORMAT_VERSION = 2

# ``messages`` encodings inside the envelope:
#   - pydantic-ai message lists, dumped/validated via ModelMessagesTypeAdapter
ENCODING_MESSAGES = "pydantic-ai-messages"
#   - plain JSON payloads stored/returned verbatim (empty histories, plugin
#     histories that are not ModelMessage lists, migrated non-message pickles)
ENCODING_JSON = "json"

# Sidecar suffixes that share the ``.json`` extension with session envelopes
# and must never be listed as sessions themselves.
_SIDECAR_STEM_SUFFIXES = ("_meta", "_acp")

SessionHistory = List[Any]
TokenEstimator = Callable[[Any], int]


@dataclass(slots=True)
class SessionPaths:
    pickle_path: Path
    metadata_path: Path
    json_path: Path


@dataclass(slots=True)
class SessionMetadata:
    session_name: str
    timestamp: str
    message_count: int
    total_tokens: int
    pickle_path: Path
    metadata_path: Path
    json_path: Path
    auto_saved: bool = False
    scope_key: str | None = None

    def as_serialisable(self) -> dict[str, Any]:
        data = {
            "session_name": self.session_name,
            "timestamp": self.timestamp,
            "message_count": self.message_count,
            "total_tokens": self.total_tokens,
            "file_path": str(self.json_path),
            "auto_saved": self.auto_saved,
        }
        if self.scope_key is not None:
            data["scope_key"] = self.scope_key
        return data


def _extract_pickle_payload(raw: bytes) -> bytes:
    """Return the pickle payload from raw session file bytes.

    New format is raw pickle bytes.
    Legacy format was: header + 32-byte signature + pickle payload.
    We no longer verify or generate signatures.
    """
    if raw.startswith(_LEGACY_SIGNED_HEADER):
        offset = len(_LEGACY_SIGNED_HEADER) + _LEGACY_SIGNATURE_SIZE
        return raw[offset:]
    return raw


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_session_paths(base_dir: Path, session_name: str) -> SessionPaths:
    return SessionPaths(
        pickle_path=base_dir / f"{session_name}.pkl",
        metadata_path=base_dir / f"{session_name}_meta.json",
        json_path=base_dir / f"{session_name}.json",
    )


def compute_scope_key(path: str | Path) -> str:
    """Return a stable scope identifier for ``path``.

    Deliberately simple: the plain absolute path, normalized for symlinks.
    No git-root detection, no branch awareness, no hashing -- an explicit
    product decision to keep this primitive dead simple.
    """
    return str(Path(path).resolve())


def _pydantic_ai_version() -> str | None:
    """Installed pydantic-ai version WITHOUT importing the package."""
    for distribution in ("pydantic-ai", "pydantic-ai-slim"):
        try:
            return importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            continue
    return None


def encode_history(history: SessionHistory) -> Tuple[str, Any]:
    """Encode ``history`` to ``(encoding, jsonable_messages)``.

    Real pydantic-ai message lists go through ``ModelMessagesTypeAdapter``;
    anything else (empty histories, plugin-provided plain payloads) is stored
    verbatim when it is already JSON-serializable. Raises ``TypeError`` when
    neither strategy applies.
    """
    history = list(history)
    if history:
        try:
            from pydantic_ai.messages import (
                ModelMessagesTypeAdapter,
                ModelRequest,
                ModelResponse,
            )

            if all(isinstance(m, (ModelRequest, ModelResponse)) for m in history):
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    return ENCODING_MESSAGES, ModelMessagesTypeAdapter.dump_python(
                        history, mode="json"
                    )
        except ImportError:  # pragma: no cover - pydantic-ai is a hard dep
            pass
    json.dumps(history)  # probe: raises TypeError when not JSON-serializable
    return ENCODING_JSON, history


def build_envelope(history: SessionHistory) -> dict[str, Any]:
    """Wrap ``history`` in the versioned session envelope."""
    encoding, messages = encode_history(history)
    return build_envelope_from_messages(messages, encoding=encoding)


def build_envelope_from_messages(
    messages: Any, *, encoding: str = ENCODING_MESSAGES
) -> dict[str, Any]:
    """Envelope for already-jsonable ``messages`` (used by the migrator)."""
    import code_puppy

    return {
        "format": SESSION_FORMAT_VERSION,
        "code_puppy": code_puppy.__version__,
        "pydantic_ai": _pydantic_ai_version(),
        "encoding": encoding,
        "messages": messages,
    }


def write_envelope_file(json_path: Path, envelope: dict[str, Any]) -> None:
    """Atomically write an envelope: temp file in-place then ``replace``."""
    tmp_path = json_path.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as json_file:
        json.dump(envelope, json_file, indent=2)
    tmp_path.replace(json_path)


def read_envelope_file(json_path: Path) -> dict[str, Any]:
    """Read + shape-check a session envelope. Raises ``ValueError`` if bad."""
    with json_path.open("r", encoding="utf-8") as json_file:
        envelope = json.load(json_file)
    if not isinstance(envelope, dict):
        raise ValueError(f"Session file {json_path} is not a JSON object")
    format_version = envelope.get("format")
    if not isinstance(format_version, int) or format_version > SESSION_FORMAT_VERSION:
        raise ValueError(
            f"Session file {json_path} has unsupported format {format_version!r}"
        )
    if not isinstance(envelope.get("messages"), list):
        raise ValueError(f"Session file {json_path} is missing its messages list")
    return envelope


def validate_messages_jsonable(messages: Any) -> SessionHistory:
    """Round-trip jsonable messages into real pydantic-ai message objects."""
    from pydantic_ai.messages import ModelMessagesTypeAdapter

    return list(ModelMessagesTypeAdapter.validate_python(messages))


def decode_envelope(envelope: dict[str, Any]) -> SessionHistory:
    """Turn an envelope back into a message history."""
    messages = envelope["messages"]
    if envelope.get("encoding", ENCODING_MESSAGES) == ENCODING_JSON:
        return list(messages)
    return validate_messages_jsonable(messages)


def save_session(
    *,
    history: SessionHistory,
    session_name: str,
    base_dir: Path,
    timestamp: str,
    token_estimator: TokenEstimator,
    auto_saved: bool = False,
    scope_key: str | None = None,
) -> SessionMetadata:
    ensure_directory(base_dir)
    paths = build_session_paths(base_dir, session_name)

    # Encode before touching disk so a bad history can't half-write a session.
    envelope = build_envelope(history)
    write_envelope_file(paths.json_path, envelope)

    total_tokens = sum(token_estimator(message) for message in history)
    metadata = SessionMetadata(
        session_name=session_name,
        timestamp=timestamp,
        message_count=len(history),
        total_tokens=total_tokens,
        pickle_path=paths.pickle_path,
        metadata_path=paths.metadata_path,
        json_path=paths.json_path,
        auto_saved=auto_saved,
        scope_key=scope_key,
    )

    tmp_metadata = paths.metadata_path.with_suffix(".tmp")
    with tmp_metadata.open("w", encoding="utf-8") as metadata_file:
        json.dump(metadata.as_serialisable(), metadata_file, indent=2)
    tmp_metadata.replace(paths.metadata_path)

    return metadata


def load_session(session_name: str, base_dir: Path) -> SessionHistory:
    paths = build_session_paths(base_dir, session_name)
    if paths.json_path.exists():
        return decode_envelope(read_envelope_file(paths.json_path))

    if paths.pickle_path.exists():
        # Lazy fallback for ``.pkl`` files that appear after the startup sweep
        # (e.g. file sync). Migrate in place, then load the JSON.
        from code_puppy.session_format_migration import (
            archive_legacy_pickle,
            migrate_pickle_file,
        )

        result = migrate_pickle_file(paths.pickle_path)
        if not result.success:
            raise ValueError(
                f"Could not migrate legacy session {paths.pickle_path}: {result.error}"
            )
        archive_legacy_pickle(paths.pickle_path)
        return decode_envelope(read_envelope_file(paths.json_path))

    raise FileNotFoundError(paths.json_path)


def _iter_session_stems(base_dir: Path) -> set[str]:
    stems = {path.stem for path in base_dir.glob("*.pkl")}
    stems.update(
        path.stem
        for path in base_dir.glob("*.json")
        if not path.stem.endswith(_SIDECAR_STEM_SUFFIXES)
    )
    return stems


def _sidecar_scope_key(base_dir: Path, stem: str) -> str | None:
    """Best-effort read of a session's sidecar ``scope_key``.

    Never raises: a missing file, unreadable JSON, or absent field all
    resolve to ``None`` so callers can silently exclude the candidate.
    """
    meta_path = base_dir / f"{stem}_meta.json"
    try:
        with meta_path.open("r", encoding="utf-8") as meta_file:
            data = json.load(meta_file)
        value = data.get("scope_key")
        return value if isinstance(value, str) else None
    except Exception:
        return None


def list_sessions(base_dir: Path, scope_key: str | None = None) -> List[str]:
    if not base_dir.exists():
        return []
    stems = sorted(_iter_session_stems(base_dir))
    if scope_key is None:
        return stems
    return [stem for stem in stems if _sidecar_scope_key(base_dir, stem) == scope_key]


def cleanup_sessions(base_dir: Path, max_sessions: int) -> List[str]:
    if max_sessions <= 0:
        return []

    if not base_dir.exists():
        return []

    stems = _iter_session_stems(base_dir)
    if len(stems) <= max_sessions:
        return []

    def newest_mtime(stem: str) -> float:
        paths = build_session_paths(base_dir, stem)
        mtimes = [
            path.stat().st_mtime
            for path in (paths.json_path, paths.pickle_path)
            if path.exists()
        ]
        return max(mtimes, default=0.0)

    sorted_stems = sorted(stems, key=newest_mtime)
    stale_stems = sorted_stems[: len(stems) - max_sessions]
    removed_sessions: List[str] = []
    for stem in stale_stems:
        paths = build_session_paths(base_dir, stem)
        try:
            paths.json_path.unlink(missing_ok=True)
            paths.pickle_path.unlink(missing_ok=True)
            paths.metadata_path.unlink(missing_ok=True)
            removed_sessions.append(stem)
        except OSError:
            continue

    return removed_sessions


async def restore_autosave_interactively(base_dir: Path) -> None:
    """Prompt the user to load an autosave session from base_dir, if any exist.

    This helper is deliberately placed in session_storage to keep autosave
    restoration close to the persistence layer. It uses the same public APIs
    (list_sessions, load_session) and mirrors the interactive behaviours from
    the command handler.

    Typing ``here`` (or ``--here``) at the selection prompt toggles an
    opt-in filter down to sessions scoped to the current working directory
    (via ``scope_key``). Off by default -- the unfiltered listing stays
    byte-for-byte identical to before this toggle existed. Sessions with
    no ``scope_key`` sidecar (pre-dating this feature) are excluded only
    while the toggle is active, never shown as a false match.
    """
    sessions = list_sessions(base_dir)
    if not sessions:
        return

    # Import locally to avoid pulling the messaging layer into storage modules
    from datetime import datetime

    from prompt_toolkit.formatted_text import FormattedText

    from code_puppy.agents.agent_manager import get_current_agent
    from code_puppy.command_line.prompt_toolkit_completion import (
        get_input_with_combined_completion,
    )
    from code_puppy.messaging import emit_success, emit_system_message, emit_warning

    def _load_entries(names):
        """Read timestamp/message_count metadata for ``names``, newest first."""
        loaded = []
        for name in names:
            meta_path = base_dir / f"{name}_meta.json"
            try:
                with meta_path.open("r", encoding="utf-8") as meta_file:
                    data = json.load(meta_file)
                timestamp = data.get("timestamp")
                message_count = data.get("message_count")
            except Exception:
                timestamp = None
                message_count = None
            loaded.append((name, timestamp, message_count))

        def sort_key(entry):
            _, timestamp, _ = entry
            if timestamp:
                try:
                    return datetime.fromisoformat(timestamp)
                except ValueError:
                    return datetime.min
            return datetime.min

        loaded.sort(key=sort_key, reverse=True)
        return loaded

    entries = _load_entries(sessions)

    # Opt-in "here" toggle -- see docstring. Off by default so the
    # unfiltered listing never changes.
    here_scope_key = compute_scope_key(Path.cwd())
    here_active = False

    PAGE_SIZE = 5
    total = len(entries)
    page = 0

    def render_page() -> None:
        start = page * PAGE_SIZE
        end = min(start + PAGE_SIZE, total)
        page_entries = entries[start:end]
        emit_system_message("Autosave Sessions Available:")
        if here_active:
            emit_system_message("  (filtered to this folder)")
        for idx, (name, timestamp, message_count) in enumerate(page_entries, start=1):
            timestamp_display = timestamp or "unknown time"
            message_display = (
                f"{message_count} messages"
                if message_count is not None
                else "unknown size"
            )
            emit_system_message(
                f"  [{idx}] {name} ({message_display}, saved at {timestamp_display})"
            )
        # If there are more pages, offer next-page; show 'Return to first page' on last page
        if total > PAGE_SIZE:
            page_count = (total + PAGE_SIZE - 1) // PAGE_SIZE
            is_last_page = (page + 1) >= page_count
            remaining = total - (page * PAGE_SIZE + len(page_entries))
            summary = (
                f" and {remaining} more" if (remaining > 0 and not is_last_page) else ""
            )
            next_label = (
                "Return to first page" if is_last_page else f"Next page{summary}"
            )
            emit_system_message(f"  [6] {next_label}")
        emit_system_message(
            "  [Enter] Skip loading autosave  --  type 'here' to toggle "
            "this-folder filter"
        )

    chosen_name: str | None = None

    while True:
        render_page()
        try:
            selection = await get_input_with_combined_completion(
                FormattedText(
                    [
                        (
                            "class:prompt",
                            "Pick 1-5 to load, 6 for next, or name/Enter: ",
                        )
                    ]
                )
            )
        except (KeyboardInterrupt, EOFError):
            emit_warning("Autosave selection cancelled")
            return

        selection = (selection or "").strip()
        if not selection:
            return

        # Opt-in toggle: re-list sessions scoped to the current directory.
        # A missing scope_key sidecar is excluded, never a false match.
        if selection.lower() in ("here", "--here"):
            here_active = not here_active
            scope_key = here_scope_key if here_active else None
            sessions = list_sessions(base_dir, scope_key=scope_key)
            entries = _load_entries(sessions)
            total = len(entries)
            page = 0
            continue

        # Numeric choice: 1-5 select within current page; 6 advances page
        if selection.isdigit():
            num = int(selection)
            if num == 6 and total > PAGE_SIZE:
                page = (page + 1) % ((total + PAGE_SIZE - 1) // PAGE_SIZE)
                # loop and re-render next page
                continue
            if 1 <= num <= 5:
                start = page * PAGE_SIZE
                idx = start + (num - 1)
                if 0 <= idx < total:
                    chosen_name = entries[idx][0]
                    break
                else:
                    emit_warning("Invalid selection for this page")
                    continue
            emit_warning("Invalid selection; choose 1-5 or 6 for next")
            continue

        # Allow direct typing by exact session name
        for name, _ts, _mc in entries:
            if name == selection:
                chosen_name = name
                break
        if chosen_name:
            break
        emit_warning("No autosave loaded (invalid selection)")
        # keep looping and allow another try

    if not chosen_name:
        return

    try:
        history = load_session(chosen_name, base_dir)
    except FileNotFoundError:
        emit_warning(f"Autosave '{chosen_name}' could not be found")
        return
    except Exception as exc:
        emit_warning(f"Failed to load autosave '{chosen_name}': {exc}")
        return

    agent = get_current_agent()
    agent.set_message_history(history)

    # Set current autosave session id so subsequent autosaves overwrite this session
    try:
        from code_puppy.config import pin_current_session_name

        pin_current_session_name(chosen_name)
    except Exception:
        pass

    total_tokens = sum(agent.estimate_tokens_for_message(msg) for msg in history)

    session_paths = build_session_paths(base_dir, chosen_name)
    session_path = (
        session_paths.json_path
        if session_paths.json_path.exists()
        else session_paths.pickle_path
    )
    emit_success(
        f"✅ Autosave loaded: {len(history)} messages ({total_tokens} tokens)\n"
        f"📁 From: {session_path}"
    )

    # Display recent message history for context
    try:
        from code_puppy.command_line.autosave_menu import display_resumed_history

        display_resumed_history(history)
    except Exception:
        pass  # Don't fail if display doesn't work in non-TTY environment
