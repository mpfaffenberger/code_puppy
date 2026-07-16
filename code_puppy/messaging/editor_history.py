"""History support for the persistent raw editor (Phase B, feature 1).

Shares the SAME history file (``COMMAND_HISTORY_FILE``) and format as the
classic prompt_toolkit path, so both prompts see one another's entries:

    # <timestamp comment>
    +<line 1 of entry>
    +<line 2 of entry>      (multiline entries = consecutive '+' lines)
    <blank line between entries>

We reuse ``SafeFileHistory`` (command_line — sanctioned import-only reuse)
when available; a tiny format-compatible fallback covers exotic import
failures.
"""

from __future__ import annotations

import datetime
import logging
import os
import threading
from typing import List, Optional

logger = logging.getLogger(__name__)


class HistoryStore:
    """Read/append the shared prompt_toolkit-format history file."""

    def __init__(self, path: Optional[str] = None) -> None:
        if path is None:
            from code_puppy.config import COMMAND_HISTORY_FILE

            path = COMMAND_HISTORY_FILE
        self._path = path
        self._lock = threading.Lock()

    def load(self) -> List[str]:
        """Return entries oldest → newest. Never raises."""
        with self._lock:
            try:
                history = self._safe_file_history()
                if history is not None:
                    # load_history_strings() yields newest-first.
                    return list(reversed(list(history.load_history_strings())))
                return self._load_fallback()
            except Exception:
                logger.debug("history load failed", exc_info=True)
                return []

    def append(self, text: str) -> None:
        """Append one submission (never raises)."""
        if not text.strip():
            return
        with self._lock:
            try:
                history = self._safe_file_history()
                if history is not None:
                    history.store_string(text)
                    return
                self._append_fallback(text)
            except Exception:
                logger.debug("history append failed", exc_info=True)

    # ------------------------------------------------------------------
    # Backends
    # ------------------------------------------------------------------

    def _safe_file_history(self):
        """The classic path's SafeFileHistory (exact format + encoding fixes)."""
        try:
            from code_puppy.command_line.prompt_toolkit_completion import (
                SafeFileHistory,
            )

            return SafeFileHistory(self._path)
        except ImportError:
            return None

    def _load_fallback(self) -> List[str]:
        """Minimal FileHistory-format reader (mirror of prompt_toolkit's)."""
        if not os.path.exists(self._path):
            return []
        entries: List[str] = []
        lines: List[str] = []
        with open(self._path, "rb") as f:
            for raw in f:
                line = raw.decode("utf-8", errors="replace")
                if line.startswith("+"):
                    lines.append(line[1:].rstrip("\n"))
                elif lines:
                    entries.append("\n".join(lines))
                    lines = []
        if lines:
            entries.append("\n".join(lines))
        return entries

    def _append_fallback(self, text: str) -> None:
        """Minimal FileHistory-format writer (mirror of prompt_toolkit's)."""
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        with open(self._path, "ab") as f:
            f.write(f"\n# {datetime.datetime.now()}\n".encode("utf-8"))
            for line in text.split("\n"):
                f.write(f"+{line}\n".encode("utf-8"))


class HistoryNavigator:
    """Up/Down history navigation with working-entry preservation.

    The entries snapshot loads lazily on first Up. ``index == len(entries)``
    means "the working entry" (whatever the user had typed before starting
    to browse); arrowing back Down past the newest entry restores it.
    Any submission or explicit reset drops the browsing state.
    """

    def __init__(self, store: Optional[HistoryStore] = None) -> None:
        self._store = store or HistoryStore()
        self._entries: Optional[List[str]] = None
        self._index: int = 0
        self._working: str = ""

    @property
    def browsing(self) -> bool:
        return self._entries is not None and self._index < len(self._entries)

    def up(self, current_text: str) -> Optional[str]:
        """Move to the previous (older) entry; None if nothing to show."""
        if self._entries is None:
            self._entries = self._store.load()
            self._index = len(self._entries)
            self._working = current_text
        if self._index == 0:
            return None  # already at the oldest entry
        self._index -= 1
        return self._entries[self._index]

    def down(self, current_text: str) -> Optional[str]:
        """Move to the next (newer) entry, or back to the working entry."""
        if self._entries is None or self._index >= len(self._entries):
            return None  # not browsing
        self._index += 1
        if self._index == len(self._entries):
            return self._working
        return self._entries[self._index]

    def record_submit(self, text: str) -> None:
        """Persist a submission and reset browsing state."""
        self._store.append(text)
        self.reset()

    def reset(self) -> None:
        self._entries = None
        self._index = 0
        self._working = ""


class ReverseSearch:
    """Minimal Ctrl+R incremental reverse search.

    Prompt row shows ``(reverse-i-search)`query': match`` while active.
    Enter accepts the match, Esc / Ctrl+C cancels, Ctrl+R again finds the
    next OLDER match. Any printable char extends the query; backspace
    shrinks it.
    """

    def __init__(self, store: Optional[HistoryStore] = None) -> None:
        self._store = store or HistoryStore()
        self._entries: List[str] = []
        self.active = False
        self.query = ""
        self._pos: int = 0  # search anchor (exclusive upper bound)

    def start(self) -> None:
        self._entries = self._store.load()
        self.active = True
        self.query = ""
        self._pos = len(self._entries)

    def cancel(self) -> None:
        self.active = False
        self.query = ""

    def feed_char(self, ch: str) -> None:
        if not self.active:
            return
        self.query += ch
        self._pos = len(self._entries)  # re-anchor: newest match for new query
        self._find_older()

    def backspace(self) -> None:
        if not self.active:
            return
        self.query = self.query[:-1]
        self._pos = len(self._entries)
        self._find_older()

    def next_older(self) -> None:
        """Ctrl+R again: continue searching past the current match."""
        if not self.active:
            return
        self._find_older()

    def current_match(self) -> Optional[str]:
        if not self.active or not self.query:
            return None
        if 0 <= self._pos < len(self._entries):
            return self._entries[self._pos]
        return None

    def prompt_text(self) -> str:
        match = self.current_match() or ""
        return f"(reverse-i-search)`{self.query}': {match}"

    def _find_older(self) -> None:
        """Scan backwards from the anchor for the next entry containing query."""
        if not self.query:
            self._pos = len(self._entries)
            return
        for i in range(min(self._pos, len(self._entries)) - 1, -1, -1):
            if self.query in self._entries[i]:
                self._pos = i
                return
        self._pos = -1  # no match


def feed_reverse_search(ed, ch: str) -> None:
    """Handle one keystroke while reverse-i-search is active.

    Editor glue moved here from ``line_editor`` (600-line cap): runs
    under the editor's lock via ``_feed_rsearch``.
    """
    rs = ed._rsearch
    if ch == "\x12":  # Ctrl+R: next older match
        rs.next_older()
    elif ch == "\r":  # Enter: accept into the buffer WITHOUT submitting
        match = rs.current_match()
        rs.cancel()
        ed._set_completion_suppressed(False)
        if match is not None:
            ed._buffer = match
            ed._cursor = len(match)
            ed._history.reset()
    elif ch in ("\x7f", "\x08"):
        rs.backspace()
    elif ch.isprintable():
        rs.feed_char(ch)
    ed._repaint()


class _NullNavigator:
    """Inert fallback when the real history can't initialize."""

    def up(self, _text):
        return None

    def down(self, _text):
        return None

    def reset(self):
        pass

    def record_submit(self, _text):
        pass


class _NullReverseSearch:
    active = False

    def cancel(self):
        pass


def safe_navigator() -> HistoryNavigator:
    """HistoryNavigator, degrading to a null object in exotic embeds."""
    try:
        return HistoryNavigator()
    except Exception:
        logger.debug("history navigator init failed", exc_info=True)
        return _NullNavigator()  # type: ignore[return-value]


def safe_reverse_search() -> ReverseSearch:
    try:
        return ReverseSearch()
    except Exception:
        logger.debug("reverse search init failed", exc_info=True)
        return _NullReverseSearch()  # type: ignore[return-value]


__all__ = [
    "HistoryNavigator",
    "HistoryStore",
    "ReverseSearch",
    "feed_reverse_search",
    "safe_navigator",
    "safe_reverse_search",
]
