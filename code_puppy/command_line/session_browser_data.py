"""Data layer for the two-pane session browser (``/resume``).

Pure / IO-tolerant helpers: session listing, project grouping, date
bucketing, and lazy title derivation with sidecar cache-back. No
terminal code lives here so everything is unit-testable headlessly.

Legacy-session policy (deliberate, see repo notes):

* Sessions whose sidecar lacks ``scope_key`` are grouped under a single
  synthetic "(unscoped)" project pinned last -- we refuse to guess
  where they came from. New saves always stamp ``scope_key``, and a
  resumed legacy session self-heals on its next autosave, so the
  bucket drains through normal use and retention.
* Titles are derived lazily from message content and cached back into
  the metadata sidecar (``title``/``subtitle`` keys). A later save may
  rewrite the sidecar without them; they simply get re-derived.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from io import StringIO
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from code_puppy.session_storage import (
    build_session_paths,
    list_sessions,
    load_session,
)

UNSCOPED_KEY = "(unscoped)"
_TITLE_MAX = 64
# A leading user text longer than this is treated as injected context
# (harness preambles, resume summaries), not something a human typed.
_CONTEXT_LENGTH = 400


def _get_session_metadata(base_dir: Path, session_name: str) -> dict:
    try:
        with (base_dir / f"{session_name}_meta.json").open(encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return {}


def _get_session_entries(base_dir: Path) -> List[Tuple[str, dict]]:
    """List ``(name, metadata)`` pairs, newest first. Never raises."""
    try:
        sessions = list_sessions(base_dir)
    except (FileNotFoundError, PermissionError):
        return []
    entries = []
    for name in sessions:
        try:
            metadata = _get_session_metadata(base_dir, name)
        except (FileNotFoundError, PermissionError):
            metadata = {}
        entries.append((name, metadata))

    def key(entry):
        try:
            return datetime.fromisoformat(entry[1].get("timestamp", ""))
        except (TypeError, ValueError):
            return datetime.min

    return sorted(entries, key=key, reverse=True)


@dataclass(slots=True)
class SessionEntry:
    """One resumable session with display-ready fields."""

    name: str
    meta: dict
    when: Optional[datetime]
    scope_key: Optional[str]

    @classmethod
    def from_pair(cls, name: str, meta: dict) -> "SessionEntry":
        try:
            when = datetime.fromisoformat(meta.get("timestamp", ""))
        except (TypeError, ValueError):
            when = None
        scope = meta.get("scope_key")
        return cls(
            name=name,
            meta=meta,
            when=when,
            scope_key=scope if isinstance(scope, str) else None,
        )

    @property
    def title(self) -> str:
        value = self.meta.get("title")
        return value if isinstance(value, str) and value else self.name

    @property
    def subtitle(self) -> str:
        value = self.meta.get("subtitle")
        if isinstance(value, str) and value:
            return value
        return f"{self.message_count} messages"

    @property
    def tags(self) -> List[str]:
        value = self.meta.get("tags")
        if isinstance(value, list):
            return [t for t in value if isinstance(t, str) and t]
        return []

    @property
    def message_count(self) -> int:
        try:
            return int(self.meta.get("message_count", 0))
        except (TypeError, ValueError):
            return 0

    @property
    def total_tokens(self) -> int:
        try:
            return int(self.meta.get("total_tokens", 0))
        except (TypeError, ValueError):
            return 0


@dataclass(slots=True)
class Project:
    """A left-pane project bucket: sessions sharing one ``scope_key``."""

    key: str
    label: str
    sessions: List[SessionEntry] = field(default_factory=list)

    @property
    def unscoped(self) -> bool:
        return self.key == UNSCOPED_KEY


def build_entries(base_dir: Path) -> List[SessionEntry]:
    return [
        SessionEntry.from_pair(name, meta)
        for name, meta in _get_session_entries(base_dir)
    ]


def _project_labels(keys: List[str]) -> Dict[str, str]:
    """Map scope keys to short labels; disambiguate basename collisions."""
    basenames: Dict[str, int] = {}
    for key in keys:
        basenames[Path(key).name] = basenames.get(Path(key).name, 0) + 1
    labels = {}
    for key in keys:
        name = Path(key).name or key
        if basenames.get(name, 0) > 1:
            name = str(Path(*Path(key).parts[-2:]))
        labels[key] = name
    return labels


def group_by_project(entries: List[SessionEntry]) -> List[Project]:
    """Group entries into projects, most-recently-used first.

    Sessions without a ``scope_key`` land in one "(unscoped)" bucket
    pinned last regardless of recency -- explicitly unknown, not
    silently misattributed.
    """
    buckets: Dict[str, List[SessionEntry]] = {}
    for entry in entries:
        buckets.setdefault(entry.scope_key or UNSCOPED_KEY, []).append(entry)

    scoped_keys = [key for key in buckets if key != UNSCOPED_KEY]
    labels = _project_labels(scoped_keys)

    def recency(key: str) -> datetime:
        stamps = [e.when for e in buckets[key] if e.when is not None]
        return max(stamps, default=datetime.min)

    projects = [
        Project(key=key, label=labels[key], sessions=buckets[key])
        for key in sorted(scoped_keys, key=recency, reverse=True)
    ]
    if UNSCOPED_KEY in buckets:
        projects.append(
            Project(
                key=UNSCOPED_KEY,
                label=UNSCOPED_KEY,
                sessions=buckets[UNSCOPED_KEY],
            )
        )
    return projects


def date_label(when: Optional[datetime], today: Optional[date] = None) -> str:
    """Bucket label for the right pane: TODAY / YESTERDAY / AUG 21 / ..."""
    if when is None:
        return "UNDATED"
    today = today or date.today()
    day = when.date()
    if day == today:
        return "TODAY"
    if day == today - timedelta(days=1):
        return "YESTERDAY"
    month = when.strftime("%b").upper()
    if day.year == today.year:
        return f"{month} {day.day}"
    return f"{month} {day.day}, {day.year}"


def time_label(when: Optional[datetime]) -> str:
    if when is None:
        return "--:--"
    return when.strftime("%I:%M %p").lstrip("0")


def token_label(tokens: int) -> str:
    if tokens >= 1000:
        return f"{tokens // 1000}k tok"
    return f"{tokens} tok"


SORT_MODES = ("recent", "msgs", "tokens")


def sort_sessions(sessions: List[SessionEntry], mode: str) -> List[SessionEntry]:
    if mode == "msgs":
        return sorted(sessions, key=lambda e: e.message_count, reverse=True)
    if mode == "tokens":
        return sorted(sessions, key=lambda e: e.total_tokens, reverse=True)
    return sorted(sessions, key=lambda e: e.when or datetime.min, reverse=True)


# -- message display helpers ------------------------------------------------


def _extract_message_content(msg) -> Tuple[str, str]:
    """``(role, text)`` for one history message. Role: user/tool/assistant."""
    kinds = [getattr(part, "part_kind", "unknown") for part in msg.parts]
    if msg.kind == "request":
        role = "tool" if all(kind == "tool-return" for kind in kinds) else "user"
    else:
        role = "tool" if all(kind == "tool-call" for kind in kinds) else "assistant"
    content = []
    for part in msg.parts:
        kind = getattr(part, "part_kind", "unknown")
        if kind == "tool-call":
            name, args = (
                getattr(part, "tool_name", "unknown"),
                getattr(part, "args", {}),
            )
            suffix = (
                f"\n   Args: {str(args)[:100]}{'...' if len(str(args)) > 100 else ''}"
                if args
                else ""
            )
            content.append(f"Tool Call: {name}{suffix}")
        elif kind == "tool-return":
            name, result = (
                getattr(part, "tool_name", "unknown"),
                getattr(part, "content", ""),
            )
            preview = result[:200].replace("\n", " ") if isinstance(result, str) else ""
            if isinstance(result, str) and len(result) > 200:
                preview += "..."
            content.append(
                f"\U0001f4e5 Tool Result: {name}"
                + (f"\n   {preview}" if preview else "")
            )
        elif isinstance(getattr(part, "content", None), str) and part.content.strip():
            content.append(part.content)
    return role, "\n\n".join(content) if content else "[No content]"


def _markdown(text: str, width: int = 72) -> str:
    """Render markdown to plain wrapped text at ``width`` columns."""
    from rich.console import Console
    from rich.markdown import Markdown

    stream = StringIO()
    Console(file=stream, force_terminal=False, width=width).print(Markdown(text))
    return stream.getvalue().rstrip()


# -- lazy titles with sidecar cache-back ------------------------------------


def _first_line(text: str, limit: int = _TITLE_MAX) -> str:
    line = text.strip().splitlines()[0].strip() if text.strip() else ""
    return line if len(line) <= limit else line[: limit - 1].rstrip() + "\u2026"


def _user_texts(history: list) -> List[str]:
    """Title-worthy user-prompt strings from a session history, in order.

    Leading texts longer than :data:`_CONTEXT_LENGTH` are dropped (while
    shorter texts remain): harnesses inject preambles and resume
    summaries as user prompts, and titling every session with the
    preamble's first line is noise. Falls back to the raw list when
    the filter would leave nothing.
    """
    texts = _user_texts_from(history)
    trimmed = list(texts)
    while len(trimmed) > 1 and len(trimmed[0]) > _CONTEXT_LENGTH:
        trimmed.pop(0)
    return trimmed if trimmed else texts


def _user_texts_from(history: list) -> List[str]:
    texts = []
    for msg in history:
        if getattr(msg, "kind", None) != "request":
            continue
        for part in getattr(msg, "parts", ()) or ():
            if getattr(part, "part_kind", None) != "user-prompt":
                continue
            content = getattr(part, "content", None)
            if isinstance(content, str) and content.strip():
                texts.append(content)
    return texts


def derive_titles(history: list) -> Tuple[str, str]:
    """``(title, subtitle)`` from message content; empty strings on no data.

    Title is the first user prompt; subtitle the last (when distinct).
    A ``post_autosave`` plugin can overwrite both with fancier summaries
    later -- same sidecar keys, no envelope change.
    """
    texts = _user_texts(history)
    if not texts:
        return "", ""
    title = _first_line(texts[0])
    subtitle = _first_line(texts[-1]) if len(texts) > 1 else ""
    return title, subtitle if subtitle != title else ""


def delete_session(base_dir: Path, session_name: str) -> bool:
    """Remove a session's envelope, legacy pickle, and metadata sidecar.

    Mirrors the file trio ``cleanup_sessions`` removes during retention
    pruning. Returns False on OS errors instead of raising.
    """
    paths = build_session_paths(base_dir, session_name)
    try:
        paths.json_path.unlink(missing_ok=True)
        paths.pickle_path.unlink(missing_ok=True)
        paths.metadata_path.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def merge_sidecar(base_dir: Path, session_name: str, updates: dict) -> bool:
    """Atomically merge ``updates`` into a session's metadata sidecar.

    Re-reads the sidecar first so concurrent writers (autosave, title
    derivation, naming plugins) only clobber the keys they own. Returns
    False instead of raising -- sidecar enrichment is decorative.
    """
    meta_path = base_dir / f"{session_name}_meta.json"
    try:
        merged = dict(_get_session_metadata(base_dir, session_name))
        merged.update(updates)
        fd, tmp_name = tempfile.mkstemp(prefix=".meta_", dir=str(meta_path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(merged, file, indent=2)
            os.replace(tmp_name, meta_path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        return True
    except Exception:
        return False


def cache_titles_back(base_dir: Path, entry: SessionEntry) -> None:
    """Merge derived title/subtitle into the sidecar. Best-effort, atomic."""
    updates = {"title": entry.meta.get("title", "")}
    if entry.meta.get("subtitle"):
        updates["subtitle"] = entry.meta["subtitle"]
    merge_sidecar(base_dir, entry.name, updates)


def ensure_titles(base_dir: Path, entry: SessionEntry) -> bool:
    """Derive+cache titles for ``entry`` when missing. Returns True on change.

    Loads the full session, so callers should invoke this lazily (visible
    rows) or from a background thread -- never in a paint loop for the
    whole store.
    """
    if isinstance(entry.meta.get("title"), str) and entry.meta["title"]:
        return False
    try:
        history = load_session(entry.name, base_dir)
    except Exception:
        return False
    title, subtitle = derive_titles(history)
    if not title:
        return False
    entry.meta["title"] = title
    if subtitle:
        entry.meta["subtitle"] = subtitle
    cache_titles_back(base_dir, entry)
    return True


def prewarm_titles(base_dir: Path, entries: List[SessionEntry]) -> None:
    """Background-thread target: derive titles for every entry missing one."""
    for entry in entries:
        ensure_titles(base_dir, entry)
