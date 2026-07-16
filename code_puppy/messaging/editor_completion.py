"""Completions for the persistent raw editor (Phase B, feature 2).

Drives the EXISTING prompt_toolkit ``Completer`` objects as pure logic:
build a ``prompt_toolkit.document.Document`` and call ``get_completions``
— no prompt_toolkit UI. The popup renders on the bottom bar's reserved
rows (``set_popup_lines``), taking precedence over the sub-agent panel
while open.

Responsiveness contract: completer calls (file path scans!) never run on
the key-listener thread. Edits schedule a debounced (~50ms) query onto
the captured event loop, the completer runs in the default executor, and
stale results (buffer changed since the query was captured) are
discarded.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass
from typing import Callable, List

logger = logging.getLogger(__name__)

#: Popup shows at most this many rows (bottom bar enforces its own cap too).
MAX_POPUP_ROWS = 6

#: Debounce window for while-typing queries.
DEBOUNCE_S = 0.05


def build_completer():
    """The classic prompt's completer stack, as pure logic.

    NOTE: this list REPLICATES the inline construction in
    ``command_line.prompt_toolkit_completion.get_input_with_combined_completion``
    (the source of truth) — it's built inline there, so it can't be
    imported without refactoring command_line/, which is off-limits.
    Keep the two in sync when completers are added.
    """
    from prompt_toolkit.completion import merge_completers

    from code_puppy.command_line.file_path_completion import FilePathCompleter
    from code_puppy.command_line.load_context_completion import LoadContextCompleter
    from code_puppy.command_line.mcp_completion import MCPCompleter
    from code_puppy.command_line.model_picker_completion import ModelNameCompleter
    from code_puppy.command_line.pin_command_completion import (
        PinCompleter,
        UnpinCompleter,
    )
    from code_puppy.command_line.prompt_toolkit_completion import (
        AgentCompleter,
        CDCompleter,
        SetCompleter,
        SlashCompleter,
    )
    from code_puppy.command_line.skills_completion import SkillsCompleter
    from code_puppy.plugins.ollama_setup.completer import OllamaSetupCompleter

    return merge_completers(
        [
            FilePathCompleter(symbol="@"),
            ModelNameCompleter(trigger="/model"),
            ModelNameCompleter(trigger="/m"),
            CDCompleter(trigger="/cd"),
            SetCompleter(trigger="/set"),
            LoadContextCompleter(trigger="/load_context"),
            PinCompleter(trigger="/pin_model"),
            UnpinCompleter(trigger="/unpin"),
            AgentCompleter(trigger="/agent"),
            AgentCompleter(trigger="/a"),
            AgentCompleter(trigger="/switch-agent"),
            AgentCompleter(trigger="/sa"),
            AgentCompleter(trigger="/fork", prefix="@"),
            MCPCompleter(trigger="/mcp"),
            SkillsCompleter(trigger="/skills"),
            OllamaSetupCompleter(),
            SlashCompleter(),
        ]
    )


def query_completions(completer, text: str, cursor: int) -> List["Item"]:
    """Synchronously run the completer stack against (text, cursor)."""
    from prompt_toolkit.completion import CompleteEvent
    from prompt_toolkit.document import Document

    document = Document(text=text, cursor_position=cursor)
    items: List[Item] = []
    for c in completer.get_completions(document, CompleteEvent()):
        display = _to_plain(c.display) or c.text
        meta = _to_plain(c.display_meta)
        items.append(
            Item(
                text=c.text, start_position=c.start_position, display=display, meta=meta
            )
        )
        if len(items) >= 200:  # sanity cap; popup shows a window anyway
            break
    return items


def _to_plain(formatted) -> str:
    """Flatten prompt_toolkit FormattedText / str to plain text."""
    if formatted is None:
        return ""
    if isinstance(formatted, str):
        return formatted
    try:
        return "".join(text for _style, text in formatted)
    except Exception:
        return str(formatted)


def should_autotrigger(text: str, cursor: int) -> bool:
    """Complete-while-typing heuristic (Tab always force-opens).

    Triggers: leading "/" (slash commands + their argument completers,
    e.g. "/model "), or an "@" anywhere in the word being typed (file
    paths). The completers themselves return nothing when inapplicable,
    so this only gates *when we bother asking*.
    """
    if text.lstrip().startswith("/"):
        return True
    word = text[:cursor].split()[-1] if text[:cursor].split() else ""
    return "@" in word


@dataclass
class Item:
    text: str
    start_position: int  # negative offset from the QUERY cursor (pt convention)
    display: str
    meta: str = ""


class CompletionEngine:
    """Debounced, loop-scheduled completion driver + menu state.

    Thread model: ``on_edit``/``on_tab``/navigation run on the
    key-listener thread; queries run on the loop (completer itself in the
    default executor); menu state is lock-guarded.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        apply_edit: Callable[[int, int, str], None],
        repaint: Callable[[], None],
        completer_factory: Callable = build_completer,
    ) -> None:
        self._loop = loop
        self._apply_edit = apply_edit  # (start, end, replacement) -> None (absolute)
        self._repaint = repaint  # repaints popup + prompt
        self._completer_factory = completer_factory
        self._completer = None
        self._lock = threading.Lock()
        self._items: List[Item] = []
        self._anchor = -1  # buffer cursor at query time (start_position base)
        self._selected = -1
        self._open = False
        self._seq = 0  # stale-result discard token
        self._debounce_handle = None
        self._suppressed = False  # reverse-i-search suppresses completion

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def is_open(self) -> bool:
        with self._lock:
            return self._open and bool(self._items)

    def set_suppressed(self, suppressed: bool) -> None:
        with self._lock:
            self._suppressed = suppressed
        if suppressed:
            self.close()

    def close(self) -> None:
        with self._lock:
            self._open = False
            self._items = []
            self._anchor = -1
            self._selected = -1
            self._seq += 1  # invalidate in-flight queries
        self._repaint()

    # ------------------------------------------------------------------
    # Triggers (key-listener thread)
    # ------------------------------------------------------------------

    def on_edit(self, text: str, cursor: int) -> None:
        """Every buffer edit: re-query while typing (debounced)."""
        with self._lock:
            if self._suppressed:
                return
            was_open = self._open
        if was_open or should_autotrigger(text, cursor):
            self._schedule_query(text, cursor, open_menu=was_open or True)
        elif self.is_open():
            self.close()

    def on_tab(self, text: str, cursor: int) -> bool:
        """Tab: cycle the selection when open, else force-open.

        Cycle-on-Tab matches shell menu-complete: Tab walks forward
        through the candidates (wrapping), Shift-Tab/Up walk backward,
        and Enter accepts the highlighted item.
        """
        if self.is_open():
            self.move(1)
            return True
        self._schedule_query(text, cursor, open_menu=True, debounce=False)
        return True

    def move(self, delta: int) -> None:
        with self._lock:
            if not self._items:
                return
            self._selected = (self._selected + delta) % len(self._items)
        self._repaint()

    def accept(self) -> bool:
        """Apply the selected completion. Returns True if one was applied.

        The replace range is anchored to the cursor captured WHEN THE
        QUERY RAN, not the live cursor — the user may have arrowed away
        since (menu stays open on movement), and applying a stale
        relative offset against the new cursor would splice garbage
        into the buffer.
        """
        with self._lock:
            if not (self._open and self._items):
                return False
            index = max(0, self._selected)
            item = self._items[index]
            anchor = self._anchor
            self._open = False
            self._items = []
            self._anchor = -1
            self._selected = -1
            self._seq += 1
        try:
            start = max(0, anchor + item.start_position)
            self._apply_edit(start, anchor, item.text)
        except Exception:
            logger.debug("completion apply failed", exc_info=True)
        self._repaint()
        return True

    # ------------------------------------------------------------------
    # Popup rendering
    # ------------------------------------------------------------------

    def popup_rows(self) -> tuple:
        """(lines, selected_row) window for the bottom-bar popup."""
        with self._lock:
            if not (self._open and self._items):
                return [], -1
            selected = max(0, self._selected)
            start = 0
            if selected >= MAX_POPUP_ROWS:
                start = selected - MAX_POPUP_ROWS + 1
            window = self._items[start : start + MAX_POPUP_ROWS]
            lines = []
            for item in window:
                meta = f"  {item.meta}" if item.meta else ""
                lines.append(f" {item.display}{meta}")
            return lines, selected - start

    # ------------------------------------------------------------------
    # Query pipeline (loop side)
    # ------------------------------------------------------------------

    def _schedule_query(
        self, text: str, cursor: int, open_menu: bool, debounce: bool = True
    ) -> None:
        with self._lock:
            self._seq += 1
            seq = self._seq
        delay = DEBOUNCE_S if debounce else 0.0
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            loop.call_soon_threadsafe(
                lambda: loop.create_task(self._query_task(seq, text, cursor, delay))
            )
        except RuntimeError:
            pass

    async def _query_task(self, seq: int, text: str, cursor: int, delay: float) -> None:
        if delay:
            await asyncio.sleep(delay)
        with self._lock:
            if seq != self._seq:
                return  # superseded before it even ran
        if self._completer is None:
            try:
                self._completer = self._completer_factory()
            except Exception:
                logger.debug("completer construction failed", exc_info=True)
                return
        try:
            items = await asyncio.get_running_loop().run_in_executor(
                None, query_completions, self._completer, text, cursor
            )
        except Exception:
            logger.debug("completion query failed", exc_info=True)
            return
        with self._lock:
            if seq != self._seq:
                return  # buffer changed while we were querying — stale
            self._items = items
            self._anchor = cursor if items else -1
            self._open = bool(items)
            self._selected = 0 if items else -1
        self._repaint()


__all__ = [
    "MAX_POPUP_ROWS",
    "CompletionEngine",
    "Item",
    "build_completer",
    "query_completions",
    "should_autotrigger",
]
