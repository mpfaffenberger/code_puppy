"""Interactive TUI for /prune — multi-select history pruner.

Renders conversation history as a checkable tree:

    [ ]   001  asst   ✎   "I've updated the auth module..."
            └─ [ ]  ✎   create_file  file_path=auth.py
            └─ [ ]  ⚡   agent_run_shell_command  command=pytest
    [ ]   002  user        "now make it idempotent"
    [ ]   003  asst        "Let me think through..."

Selection rules:
    * Selecting a message implicitly selects all its child tool calls
      (greyed checkbox shown for the children).
    * Selecting a tool call only removes that ToolCallPart and its
      matching ToolReturnPart from history.
    * Tool returns (ModelRequest with ToolReturnPart) are not directly
      selectable — they tag along with the tool call that owns them.

Returns a PruneSelection describing which messages and which individual
tool calls to remove. The caller owns the actual mutation.
"""

from __future__ import annotations

import shutil
import sys
import time
from typing import List, Optional, Set, Tuple

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Dimension, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame

from code_puppy.plugins.prune.prune_model import (
    SIDE_EFFECT_ICONS,
    ContextBudget,
    MessageEntry,
    PruneSelection,
    Row,
)
from code_puppy.plugins.prune.prune_render import render_detail, render_list


class PruneMenu:
    """prompt_toolkit split-panel TUI for /prune."""

    def __init__(
        self,
        entries: List[MessageEntry],
        *,
        preview_only: bool,
        budget: Optional[ContextBudget] = None,
    ) -> None:
        if not entries:
            raise ValueError("PruneMenu requires at least one entry")

        self.entries = entries
        self.preview_only = preview_only
        self.budget = budget or ContextBudget()

        # Build the visible row list NEWEST-FIRST. Pure tool-return
        # messages are hidden from the top level — they're represented
        # by their parent's tool call rows. Tool calls within a message
        # keep their original chronological order (that's semantic — the
        # sequence the model invoked them in).
        self.rows: List[Row] = []
        for msg_idx in range(len(entries) - 1, -1, -1):
            entry = entries[msg_idx]
            if entry.is_pure_tool_return:
                continue
            self.rows.append(Row(kind="message", message_idx=msg_idx))
            for tc in entry.tool_calls:
                self.rows.append(
                    Row(
                        kind="tool_call",
                        message_idx=msg_idx,
                        tool_call_id=tc.tool_call_id,
                    )
                )

        if not self.rows:
            raise ValueError("PruneMenu has no visible rows")

        self.cursor: int = 0
        self.selected_messages: Set[int] = set()  # message_idx values
        self.selected_tool_calls: Set[Tuple[int, str]] = set()

        # Viewport state — set for real in run() once we know the terminal
        # size, but seed with sensible defaults so the menu can be unit-tested
        # without a live TTY.
        self.viewport_top: int = 0
        self._visible_rows: int = 20

        # Detail pane scroll. Reset to 0 whenever the cursor lands on a new
        # row so each row's detail starts at the top.
        self.detail_scroll: int = 0
        self._last_cursor_for_detail: int = -1

        self.list_control: Optional[FormattedTextControl] = None
        self.detail_control: Optional[FormattedTextControl] = None
        self.detail_window: Optional[Window] = None

        self._result: Optional[PruneSelection] = None

    # ── selection logic ───────────────────────────────────────────────────

    def _toggle_current(self) -> None:
        row = self.rows[self.cursor]
        # System rows (history[0]'s system+user bundle) are non-toggleable —
        # pruning them would nuke the agent's identity. The defensive
        # index-0 check in _perform_prune is belt; this is the suspenders.
        if self.entries[row.message_idx].role == "system":
            return
        if row.kind == "message":
            if row.message_idx in self.selected_messages:
                self.selected_messages.discard(row.message_idx)
            else:
                self.selected_messages.add(row.message_idx)
                # Clear individual tool-call selections under this message —
                # they're now implied by the message-level selection.
                self.selected_tool_calls = {
                    (m, tc)
                    for (m, tc) in self.selected_tool_calls
                    if m != row.message_idx
                }
        else:
            # Toggling a tool call when its parent message is selected does
            # nothing — the parent already implies removal.
            if row.message_idx in self.selected_messages:
                return
            key = (row.message_idx, row.tool_call_id or "")
            if key in self.selected_tool_calls:
                self.selected_tool_calls.discard(key)
            else:
                self.selected_tool_calls.add(key)

    def _select_all(self) -> None:
        for msg_idx, entry in enumerate(self.entries):
            if entry.is_pure_tool_return or entry.role == "system":
                continue
            self.selected_messages.add(msg_idx)
        self.selected_tool_calls.clear()

    def _clear_all(self) -> None:
        self.selected_messages.clear()
        self.selected_tool_calls.clear()

    def _row_is_checked(self, row: Row) -> Tuple[bool, bool]:
        """Return (is_checked, is_implied)."""
        if row.kind == "message":
            return (row.message_idx in self.selected_messages, False)
        if row.message_idx in self.selected_messages:
            return (True, True)
        return (
            (row.message_idx, row.tool_call_id or "") in self.selected_tool_calls,
            False,
        )

    # ── viewport / pagination ──────────────────────────────────────────────────

    def _page_size(self) -> int:
        """Number of row lines that fit in the list pane right now."""
        # Always keep the page size at least 1 so we never divide by zero.
        return max(1, self._visible_rows)

    def _scroll_into_view(self) -> None:
        """Adjust viewport_top so cursor stays visible. Idempotent."""
        page = self._page_size()
        if self.cursor < self.viewport_top:
            self.viewport_top = self.cursor
        elif self.cursor >= self.viewport_top + page:
            self.viewport_top = self.cursor - page + 1
        # Clamp so we don't show empty space past the end
        max_top = max(0, len(self.rows) - page)
        if self.viewport_top > max_top:
            self.viewport_top = max_top
        if self.viewport_top < 0:
            self.viewport_top = 0

    # ── rendering (delegated to prune_render) ───────────────────────────────

    def _selection_has_side_effects(self) -> bool:
        for msg_idx in self.selected_messages:
            for tc in self.entries[msg_idx].tool_calls:
                if tc.icon in SIDE_EFFECT_ICONS:
                    return True
        for msg_idx, tc_id in self.selected_tool_calls:
            for tc in self.entries[msg_idx].tool_calls:
                if tc.tool_call_id == tc_id and tc.icon in SIDE_EFFECT_ICONS:
                    return True
        return False

    def _update_display(self) -> None:
        self._scroll_into_view()
        # Reset detail-pane scroll whenever the cursor lands on a new row.
        if self.cursor != self._last_cursor_for_detail:
            self.detail_scroll = 0
            self._last_cursor_for_detail = self.cursor
        if self.list_control:
            self.list_control.text = render_list(self)
        if self.detail_control:
            self.detail_control.text = render_detail(self)
        if self.detail_window is not None:
            # Clamp non-negative; prompt_toolkit clamps the upper bound
            # automatically against actual rendered line count.
            self.detail_window.vertical_scroll = max(0, self.detail_scroll)

    # ── main entry ────────────────────────────────────────────────────────

    def _build_selection(self) -> PruneSelection:
        sel = PruneSelection()
        for msg_idx in self.selected_messages:
            sel.history_indices_to_drop.add(self.entries[msg_idx].history_index)
        for _msg_idx, tc_id in self.selected_tool_calls:
            sel.tool_call_ids_to_drop.add(tc_id)
        return sel

    def _build_keybindings(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("up")
        @kb.add("c-p")
        @kb.add("k")
        def _up(event):
            if self.cursor > 0:
                self.cursor -= 1
                self._update_display()

        @kb.add("down")
        @kb.add("c-n")
        @kb.add("j")
        def _down(event):
            if self.cursor < len(self.rows) - 1:
                self.cursor += 1
                self._update_display()

        @kb.add("pageup")
        def _pageup(event):
            self.cursor = max(0, self.cursor - self._page_size())
            self._update_display()

        @kb.add("pagedown")
        def _pagedown(event):
            self.cursor = min(len(self.rows) - 1, self.cursor + self._page_size())
            self._update_display()

        @kb.add("home")
        def _home(event):
            self.cursor = 0
            self._update_display()

        @kb.add("end")
        def _end(event):
            self.cursor = len(self.rows) - 1
            self._update_display()

        @kb.add("space")
        def _toggle(event):
            self._toggle_current()
            self._update_display()

        @kb.add("a")
        def _all(event):
            self._select_all()
            self._update_display()

        @kb.add("c")
        def _clear(event):
            self._clear_all()
            self._update_display()

        # ── detail-pane scroll bindings ──────────────────────────────────────
        # shift+arrows for line-by-line, < / > for page jumps, also K / J
        # as alternates for terminals that swallow shift modifiers.

        def _detail_step(delta: int) -> None:
            self.detail_scroll = max(0, self.detail_scroll + delta)
            if self.detail_window is not None:
                self.detail_window.vertical_scroll = self.detail_scroll

        @kb.add("s-up")
        @kb.add("K")
        def _detail_up(event):
            _detail_step(-1)

        @kb.add("s-down")
        @kb.add("J")
        def _detail_down(event):
            _detail_step(1)

        @kb.add("<")
        def _detail_pageup(event):
            _detail_step(-max(1, self._page_size() - 2))

        @kb.add(">")
        def _detail_pagedown(event):
            _detail_step(max(1, self._page_size() - 2))

        @kb.add("g")
        def _detail_home(event):
            self.detail_scroll = 0
            if self.detail_window is not None:
                self.detail_window.vertical_scroll = 0

        @kb.add("enter")
        def _confirm(event):
            self._result = self._build_selection()
            event.app.exit()

        @kb.add("q")
        @kb.add("escape")
        @kb.add("c-c")
        def _quit(event):
            self._result = None
            event.app.exit()

        return kb

    def _measure_terminal(self) -> Tuple[int, int]:
        """Return (cols, rows) of the current terminal, with sane fallbacks."""
        try:
            size = shutil.get_terminal_size(fallback=(120, 40))
            return max(60, size.columns), max(15, size.lines)
        except Exception:
            return 120, 40

    def run(self) -> Optional[PruneSelection]:
        self.list_control = FormattedTextControl(text="")
        self.detail_control = FormattedTextControl(text="")

        # Lock pane widths to absolute halves of the terminal. Using weights
        # alone lets prompt_toolkit re-negotiate based on content, which makes
        # the divider visibly jitter as the user scrolls. We cap the upper
        # bound (max == preferred) so widths stay stable, but allow shrinking
        # down to a small min so prompt_toolkit can survive tight terminals
        # (Frame borders + padding chrome eat a few cols on each side).
        cols, rows = self._measure_terminal()
        # Be generous with the chrome budget: each Frame can eat ~3 cols on
        # each side once you count border + padding. Underestimating triggers
        # "Window too small" errors.
        usable_cols = max(40, cols - 8)
        left_cols = usable_cols // 2
        right_cols = usable_cols - left_cols
        # Reserve lines for: title (1) + budget (1) + optional overflow (1) +
        # legend (1) + blank (1) + top indicator (1) + bottom indicator (1) +
        # blank (1) + footer (1) + cursor counter (1) + frame top/bottom (2).
        # Floor at 5 so tiny terminals still work.
        self._visible_rows = max(5, rows - 12)

        list_width = Dimension(min=20, max=left_cols, preferred=left_cols)
        detail_width = Dimension(min=20, max=right_cols, preferred=right_cols)

        list_window = Window(
            content=self.list_control, wrap_lines=False, width=list_width
        )
        detail_window = Window(
            content=self.detail_control, wrap_lines=True, width=detail_width
        )
        self.detail_window = detail_window

        list_frame = Frame(list_window, title="history")
        detail_frame = Frame(detail_window, title="detail")
        root = VSplit([list_frame, detail_frame])

        layout = Layout(root)
        app = Application(
            layout=layout,
            key_bindings=self._build_keybindings(),
            full_screen=False,
            mouse_support=False,
        )

        try:
            from code_puppy.tools.command_runner import set_awaiting_user_input

            set_awaiting_user_input(True)
        except Exception:
            pass

        sys.stdout.write("\033[?1049h")
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()
        time.sleep(0.05)

        try:
            self._update_display()
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()
            app.run(in_thread=True)
        finally:
            sys.stdout.write("\033[?1049l")
            sys.stdout.flush()
            try:
                import termios

                termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
            except Exception:
                pass
            time.sleep(0.1)
            try:
                from code_puppy.tools.command_runner import set_awaiting_user_input

                set_awaiting_user_input(False)
            except Exception:
                pass

        return self._result


__all__ = ["PruneMenu"]
