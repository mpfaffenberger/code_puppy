"""Two-pane termflow session browser used by ``/resume``.

Layout mirrors the ``PROJECTS | sessions`` mockup: a left pane of
projects (grouped by autosave ``scope_key``) and a right pane of that
project's sessions bucketed by day, two lines per session (time +
title, subtitle) with message/token counts right-aligned.

Follows the established headless-menu recipe: injectable ``output`` /
``key_source`` / ``size``, full-frame repaints, and a factory
(:func:`build_session_browser`) accepting overrides so tests drive the
widget with scripted keys. Colors come from the active termflow theme
via :func:`code_puppy.command_line.tui_style.menu_style`.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Callable, List, Optional, Tuple

from termflow.ansi.codes import BOLD_ON, DIM_ON, RESET
from termflow.ansi.color import fg_color
from termflow.ansi.utils import visible_length
from termflow.render.style import RenderStyle
from termflow.tui.keys import Key, read_key
from termflow.tui.menu import RESIZE_POLL_S, _truncate, _two_columns
from termflow.tui.terminal import alt_screen, raw_mode, terminal_size

from code_puppy.command_line.autosave_search import SessionContentIndex, entry_matches
from code_puppy.command_line.session_browser_data import (
    SORT_MODES,
    Project,
    SessionEntry,
    _extract_message_content,
    _markdown,
    build_entries,
    date_label,
    delete_session,
    ensure_titles,
    group_by_project,
    prewarm_titles,
    sort_sessions,
    time_label,
    token_label,
)
from code_puppy.command_line.tui_style import menu_style
from code_puppy.config import AUTOSAVE_DIR

CURSOR_HOME = "\x1b[H"
CLEAR_TO_EOL = "\x1b[K"
LIST_WIDTH = 30
_LAZY_TITLE_BUDGET = 6  # max title derivations per paint (keep frames snappy)


@dataclass(slots=True)
class BrowseResult:
    session: Optional[str] = None
    cancelled: bool = False


def _fit(left: str, right: str, width: int) -> str:
    """Compose ``left ... right`` in <= ``width`` columns, guaranteed.

    The responsive contract for every composed row: the left part
    truncates with an ellipsis, the right part is all-or-nothing
    (dropped entirely when it cannot fit beside a minimal left), and
    the result NEVER exceeds ``width`` -- no reliance on the terminal
    clipping mid-word at the edge.
    """
    right_width = visible_length(right)
    if not right or right_width > width - 6:
        return _truncate(left, width)
    available = width - right_width - 1
    if visible_length(left) > available:
        left = _truncate(left, available)
    pad = " " * max(1, width - visible_length(left) - right_width)
    return f"{left}{pad}{right}"


class SessionBrowser:
    """Interactive project/session picker. Build via the factory below."""

    def __init__(
        self,
        projects: List[Project],
        *,
        base_dir: Path,
        content_index: Optional[SessionContentIndex] = None,
        style: Optional[RenderStyle] = None,
        output: Optional[IO[str]] = None,
        key_source: Optional[Callable[[], str]] = None,
        size: Optional[Callable[[], Tuple[int, int]]] = None,
        use_alt_screen: bool = True,
    ) -> None:
        self._projects = projects
        self._base_dir = base_dir
        self._index = content_index or SessionContentIndex()
        self._style = style or RenderStyle.default()
        self._output = output if output is not None else sys.stdout
        self._read_key = key_source or (lambda: read_key(timeout=RESIZE_POLL_S))
        self._size = size or terminal_size
        self._use_alt_screen = use_alt_screen

        self._mode = "projects"  # projects | sessions | search | browse
        self._pcursor = 0
        self._scursor = 0
        self._sort = 0
        self._query = ""
        self._buffer = ""
        self._history: Optional[list] = None
        self._message = 0
        self._confirm_delete: Optional[SessionEntry] = None
        self._total = sum(len(p.sessions) for p in projects)

    # -- derived state ------------------------------------------------------

    @property
    def project(self) -> Optional[Project]:
        if not self._projects:
            return None
        return self._projects[min(self._pcursor, len(self._projects) - 1)]

    def visible_sessions(self) -> List[SessionEntry]:
        if self._query:
            # Active search is GLOBAL: the header advertises `/ search`
            # unconditionally, so results span every project.
            pool = [e for p in self._projects for e in p.sessions]
            ordered = sort_sessions(pool, SORT_MODES[self._sort])
            return [entry for entry in ordered if self._matches(entry)]
        project = self.project
        if project is None:
            return []
        return sort_sessions(project.sessions, SORT_MODES[self._sort])

    def _matches(self, entry: SessionEntry) -> bool:
        """Cheap title/tag match first; message-content search as fallback."""
        query = self._query
        if query in entry.title.lower():
            return True
        if any(query in tag.lower() for tag in entry.tags):
            return True
        return entry_matches(
            (entry.name, entry.meta), query, self._index, self._base_dir
        )

    @property
    def highlighted(self) -> Optional[SessionEntry]:
        sessions = self.visible_sessions()
        if not sessions:
            return None
        return sessions[min(self._scursor, len(sessions) - 1)]

    # -- painting -----------------------------------------------------------

    def _c(self, hex_color: str, text: str, bold: bool = False, dim: bool = False):
        prefix = (
            fg_color(hex_color) + (BOLD_ON if bold else "") + (DIM_ON if dim else "")
        )
        return f"{prefix}{text}{RESET}"

    def _header_line(self, width: int) -> str:
        s = self._style
        left = (
            self._c(s.bright, "CODE PUPPY", bold=True)
            + self._c(s.symbol, " > ")
            + f"{BOLD_ON}Resume Auto-Saved Session{RESET}"
        )
        if self._mode == "search":
            right = self._c(s.symbol, f"/ {self._buffer}\u2588")
        else:
            stats = f"{self._total} sessions across {len(self._projects)} projects"
            right = self._c(s.grey, stats) + "  " + self._c(s.symbol, "/ search")
            if visible_length(left) + visible_length(right) + 1 > width:
                right = self._c(s.symbol, "/ search")  # stats are droppable chrome
        return _fit(left, right, width)

    def _left_lines(self, height: int) -> List[str]:
        s = self._style
        lines = [f"{BOLD_ON}PROJECTS ({len(self._projects)}){RESET}", ""]
        focused = self._mode == "projects"
        for i, project in enumerate(self._projects):
            selected = i == self._pcursor
            pointer = "> " if selected and focused else "  "
            color = s.grey if project.unscoped else (s.head if selected else "")
            label = (
                self._c(color, project.label, bold=selected)
                if color
                else (f"{BOLD_ON}{project.label}{RESET}" if selected else project.label)
            )
            total = len(project.sessions)
            count = f"{total} session{'s' if total != 1 else ''}"
            count_col = self._c(s.head if selected else s.bright, count)
            row = f"{self._c(s.head, pointer) if selected else pointer}{label}"
            lines.append(_fit(row, count_col, self._list_width()))
        return lines[: height - 4]

    def _list_width(self) -> int:
        """Left-pane width: fixed on wide terminals, proportional on narrow."""
        width, _ = self._size()
        if width >= 3 * LIST_WIDTH:
            return LIST_WIDTH
        return max(16, width // 3)

    def _session_rows(self) -> List[Tuple[str, object]]:
        """Flat display rows: ('header', label) / ('top'|'bottom', entry)."""
        rows: List[Tuple[str, object]] = []
        last_label = None
        for entry in self.visible_sessions():
            label = date_label(entry.when)
            if label != last_label:
                rows.append(("header", label))
                last_label = label
            rows.append(("top", entry))
            rows.append(("bottom", entry))
        return rows

    def _render_session_row(
        self, kind: str, payload, width: int, highlighted: bool
    ) -> str:
        s = self._style
        if kind == "header":
            rule = "\u2500" * max(0, width - len(str(payload)) - 2)
            return self._c(s.grey, f"{payload} {rule}")
        entry: SessionEntry = payload  # type: ignore[assignment]
        focused = self._mode in ("sessions", "search")
        pointer = "> " if highlighted and focused and kind == "top" else "  "
        if kind == "top":
            time_col = self._c(s.bright, f"{time_label(entry.when):>8}")
            counts = (
                self._c(s.bright, f"{entry.message_count} msgs")
                + "  "
                + self._c(s.head, token_label(entry.total_tokens))
            )
            title = (
                self._c(s.head, entry.title, bold=True)
                if highlighted
                else f"{BOLD_ON}{entry.title}{RESET}"
            )
            left = f"{self._c(s.head, pointer) if highlighted else pointer}{time_col}  {title}"
            return _fit(left, counts, width)
        subtitle = self._c(s.grey, entry.subtitle)
        return _fit(f"  {'':>8}  {subtitle}", self._fit_tags(entry, width), width)

    def _fit_tags(self, entry: SessionEntry, width: int) -> str:
        """Tag chip string dropping WHOLE tags until they fit the row.

        Half a hashtag is noise; a missing trailing tag is not. Tags
        may use at most half the row so the subtitle keeps its lead.
        """
        room = width // 2
        tags = list(entry.tags[:4])
        while tags and len(" ".join(f"#{t}" for t in tags)) > room:
            tags.pop()
        if not tags:
            return ""
        return self._c(self._style.symbol, " ".join(f"#{t}" for t in tags))

    def _right_lines(self, width: int, height: int) -> List[str]:
        s = self._style
        sort_chunk = self._c(s.grey, "Sort: ") + self._c(
            s.symbol, SORT_MODES[self._sort]
        )
        if self._query:
            count = len(self.visible_sessions())
            head = (
                self._c(s.grey, "Search: ")
                + self._c(s.head, f"'{self._query}'")
                + self._c(s.grey, f"   {count} across all projects")
                + "   "
                + sort_chunk
            )
        else:
            project = self.project
            label = project.label if project else "-"
            head = (
                self._c(s.grey, "Project: ")
                + self._c(s.head, label)
                + "   "
                + sort_chunk
            )
        lines = [_truncate(head, width)]

        rows = self._session_rows()
        budget = _LAZY_TITLE_BUDGET
        available = max(3, height - 5 - len(lines))
        cursor_top = next(
            (
                i
                for i, (kind, payload) in enumerate(rows)
                if kind == "top" and payload is self.highlighted
            ),
            0,
        )
        start = 0
        if cursor_top + 1 >= start + available:
            start = cursor_top + 2 - available
        window = rows[start : start + available]
        hidden_after = sum(1 for kind, _ in rows[start + available :] if kind == "top")
        if hidden_after:
            window = window[:-1]

        for kind, payload in window:
            if kind == "top" and budget > 0 and isinstance(payload, SessionEntry):
                if ensure_titles(self._base_dir, payload):
                    budget -= 1
            lines.append(
                self._render_session_row(
                    kind, payload, width, payload is self.highlighted
                )
            )
        if hidden_after:
            lines.append(self._c(s.grey, f"... and {hidden_after} more sessions"))
        if not rows:
            empty = (
                f"No matches for '{self._query}'."
                if self._query
                else "No sessions in this project."
            )
            lines.append(self._c(s.grey, empty))
        return lines

    def _browse_lines(self, width: int, height: int) -> List[str]:
        s = self._style
        history = self._history or []
        entry = self.highlighted
        lines = [self._c(s.bright, "MESSAGE BROWSER", bold=True), ""]
        if not history:
            return lines + [self._c(s.error, "No messages in this session.")]
        idx = max(0, min(self._message, len(history) - 1))
        role, content = _extract_message_content(history[-1 - idx])
        rendered = content if role == "tool" else _markdown(content, width - 4)
        lines.append(
            self._c(s.grey, "Session: ")
            + self._c(s.head, entry.title if entry else "?")
        )
        lines.append(self._c(s.grey, f"Message {idx + 1} of {len(history)}"))
        lines.append(self._c(s.grey, "\u2500" * min(40, width)))
        role_color = s.symbol if role == "user" else s.head
        lines.append(self._c(role_color, role.upper(), bold=True))
        lines.extend(rendered.splitlines())
        return lines[: height - 4]

    def _footer(self, width: int) -> List[str]:
        s = self._style

        def key(k: str, label: str) -> str:
            return f"{self._c(s.head, k, bold=True)} {self._c(s.grey, label)}"

        if self._confirm_delete is not None:
            prompt = self._c(
                s.error,
                f"Delete '{self._confirm_delete.title}'?",
                bold=True,
            )
            hints = [prompt, key("y", "confirm"), key("any other key", "cancel")]
        elif self._mode == "projects":
            hints = [
                key("\u2191\u2193", "navigate"),
                key("enter", "open"),
                key("q", "quit"),
            ]
        elif self._mode == "search":
            hints = [key("enter", "apply"), key("esc", "cancel")]
        elif self._mode == "browse":
            hints = [
                key("\u2191", "older"),
                key("\u2193", "newer"),
                key("esc", "back"),
            ]
        else:
            hints = [
                key("\u2191\u2193", "navigate"),
                key("enter", "resume"),
                key("\u2192", "preview"),
                key("/", "search"),
                key("s", "sort"),
                key("d", "delete"),
                key("\u2190", "back to projects"),
                key("q", "quit"),
            ]
        return [
            self._c(s.grey, "\u2500" * width),
            _truncate("  ".join(hints), width),
        ]

    def _frame(self) -> List[str]:
        width, height = self._size()
        frame = [self._header_line(width), ""]
        list_width = self._list_width()
        body_width = max(20, width - list_width - 3)
        if self._mode == "browse":
            body = self._browse_lines(width, height)
            frame.extend(_truncate(line, width) for line in body)
        else:
            left = self._left_lines(height)
            right = self._right_lines(body_width, height)
            frame.extend(_two_columns(left, right, list_width, width))
        frame = frame[: height - 2]
        frame.extend(self._footer(width))
        return frame

    def _paint(self) -> None:
        frame = self._frame()
        payload = (
            CURSOR_HOME
            + "".join(f"{line}{CLEAR_TO_EOL}\r\n" for line in frame)
            + "\x1b[J"
        )
        try:
            self._output.write(payload)
            self._output.flush()
        except Exception:
            pass

    # -- event loop ---------------------------------------------------------

    def run(self) -> BrowseResult:
        if self._use_alt_screen:
            with raw_mode(), alt_screen(self._output):
                return self._loop()
        return self._loop()

    def _loop(self) -> BrowseResult:
        while True:
            self._paint()
            result = self._handle_key(self._wait_key())
            if result is not None:
                return result

    def _wait_key(self) -> str:
        """Block for a key, repainting whenever the terminal resizes.

        Mirrors termflow's Menu/TextInput: the default key source times
        out every RESIZE_POLL_S seconds (returning ""), letting the
        two-pane layout reflow immediately on resize -- no keypress
        needed. Scripted test sources that never yield "" are unaffected.
        """
        last_size = self._size()
        while True:
            key = self._read_key()
            if key:
                return key
            size = self._size()
            if size != last_size:
                last_size = size
                self._paint()

    def _move(self, delta: int) -> None:
        if self._mode == "projects":
            self._pcursor = max(0, min(self._pcursor + delta, len(self._projects) - 1))
            self._scursor = 0
        elif self._mode == "browse":
            limit = len(self._history or []) - 1
            self._message = max(0, min(self._message + (-delta), limit))
        else:
            count = len(self.visible_sessions())
            self._scursor = max(0, min(self._scursor + delta, count - 1))

    def _handle_key(self, key: str) -> Optional[BrowseResult]:
        if key == "ctrl-c":
            return BrowseResult(cancelled=True)
        if self._confirm_delete is not None:
            self._resolve_delete(key)
            return None
        if key in (Key.UP, "ctrl-p"):
            self._move(-1)
        elif key in (Key.DOWN, "ctrl-n"):
            self._move(1)
        elif self._mode == "projects":
            return self._handle_projects_key(key)
        elif self._mode == "search":
            return self._handle_search_key(key)
        elif self._mode == "browse":
            if key in (Key.ESCAPE, "q"):
                self._mode, self._history, self._message = "sessions", None, 0
        else:
            return self._handle_sessions_key(key)
        return None

    def _handle_projects_key(self, key: str) -> Optional[BrowseResult]:
        if key in (Key.ENTER, Key.RIGHT, Key.TAB):
            if self.visible_sessions():
                self._mode = "sessions"
        elif key == "/":
            # Search is reachable from anywhere; results land in the
            # sessions pane spanning all projects.
            self._mode, self._buffer = "search", ""
        elif key in (Key.ESCAPE, "q"):
            return BrowseResult(cancelled=True)
        return None

    def _handle_sessions_key(self, key: str) -> Optional[BrowseResult]:
        if key == Key.ENTER:
            entry = self.highlighted
            if entry is not None:
                return BrowseResult(session=entry.name)
        elif key in (Key.LEFT, Key.TAB):
            self._mode, self._query, self._scursor = "projects", "", 0
        elif key in (Key.ESCAPE, "q"):
            if self._query:
                self._query = ""
                self._scursor = 0
            else:
                self._mode = "projects"
        elif key in (Key.RIGHT, "e"):
            entry = self.highlighted
            if entry is not None:
                try:
                    from code_puppy.session_storage import load_session

                    self._history = load_session(entry.name, self._base_dir)
                    self._message, self._mode = 0, "browse"
                except Exception:
                    self._history = None
        elif key == "/":
            self._mode, self._buffer = "search", ""
        elif key == "s":
            self._sort = (self._sort + 1) % len(SORT_MODES)
            self._scursor = 0
        elif key == "d":
            self._confirm_delete = self.highlighted
        return None

    def _resolve_delete(self, key: str) -> None:
        """Second keypress of the d-then-y delete confirmation."""
        entry, self._confirm_delete = self._confirm_delete, None
        if key not in ("y", "Y") or entry is None:
            return
        if not delete_session(self._base_dir, entry.name):
            return
        # Global search results can span projects: find the owner by
        # membership rather than trusting the project cursor.
        project = next((p for p in self._projects if entry in p.sessions), None)
        if project is not None and entry in project.sessions:
            project.sessions.remove(entry)
            self._total -= 1
        self._scursor = max(0, min(self._scursor, len(self.visible_sessions()) - 1))
        if project is not None and not project.sessions:
            self._projects.remove(project)
            self._pcursor = max(0, min(self._pcursor, len(self._projects) - 1))
            self._mode, self._query = "projects", ""

    def _handle_search_key(self, key: str) -> Optional[BrowseResult]:
        if key == Key.ENTER:
            self._query, self._buffer = self._buffer.strip(), ""
            self._mode, self._scursor = "sessions", 0
        elif key == Key.ESCAPE:
            self._mode, self._buffer = "sessions", ""
        elif key == Key.BACKSPACE:
            self._buffer = self._buffer[:-1]
        elif len(key) == 1 and key.isprintable():
            self._buffer += key.lower()
        return None


def build_session_browser(
    entries: Optional[List[SessionEntry]] = None,
    base_dir: Optional[Path] = None,
    content_index: Optional[SessionContentIndex] = None,
    **overrides,
) -> SessionBrowser:
    """Build a headlessly driveable session browser.

    ``overrides`` map straight onto :class:`SessionBrowser` keyword
    arguments (``output``, ``key_source``, ``size``, ``use_alt_screen``,
    ``style``) so tests inject scripted IO -- same recipe as the other
    termflow menus.
    """
    base_dir = Path(AUTOSAVE_DIR) if base_dir is None else Path(base_dir)
    entries = build_entries(base_dir) if entries is None else list(entries)
    overrides.setdefault("style", menu_style() or RenderStyle.default())
    return SessionBrowser(
        group_by_project(entries),
        base_dir=base_dir,
        content_index=content_index,
        **overrides,
    )


def _prewarm(
    base_dir: Path, entries: List[SessionEntry], index: SessionContentIndex
) -> None:
    """Background warm of titles + the content-search cache."""
    prewarm_titles(base_dir, entries)
    for entry in entries:
        if entry.name not in index:
            index.lookup(entry.name, base_dir)
