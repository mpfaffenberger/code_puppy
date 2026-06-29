"""Interactive TUI for managing plugins.

Launch with ``/plugins`` to browse and toggle plugins on/off.
Built with prompt_toolkit, following the same pattern as the skills menu.

This module is the *controller*: terminal sizing, key bindings, app lifecycle,
and plugin state mutation. All rendering (fragment construction, padding,
emoji stripping) lives in :mod:`plugins_menu_render` so each module has one
reason to change.
"""

from __future__ import annotations

import shutil
import sys
import time
from typing import List, Optional, Tuple

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Dimension, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame

from code_puppy.command_line.pagination import (
    ensure_visible_page,
    get_total_pages,
)
from code_puppy.plugins.plugin_list.plugin_text_utils import (
    Fragments,
    count_lines,
    drop_leading_lines,
)
from code_puppy.plugins.plugin_list.plugins_menu_render import (
    fill_pane,
    render_detail,
    render_list,
)
from code_puppy.tools.command_runner import set_awaiting_user_input

PAGE_SIZE = 20


class _PluginEntry:
    """Lightweight struct for a loaded plugin."""

    __slots__ = ("name", "tier")

    def __init__(self, name: str, tier: str) -> None:
        self.name = name
        self.tier = tier


class PluginsMenu:
    """Interactive TUI for enabling/disabling plugins.

    The view (``plugins_menu_render``) reads the following attributes on this
    object — keep them stable to avoid breaking the render contract:

    * ``plugins``, ``disabled``, ``selected_idx``, ``current_page``, ``page_size``
    * ``_detail_cols``, ``_pane_rows``
    * ``_changed``
    * ``_current()``
    """

    def __init__(self) -> None:
        self.plugins: List[_PluginEntry] = []
        self.disabled: set[str] = set()

        self.selected_idx = 0
        self.current_page = 0
        # Mirrors PAGE_SIZE so the renderer's pagination math and the
        # keybindings (which use the module constant) can't drift apart.
        self.page_size = PAGE_SIZE
        self.result: Optional[str] = None
        self._changed = False

        self.detail_scroll = 0

        # Pane height is tracked so we can pad short content with blank rows —
        # prompt_toolkit's cell-diff leaves "empty" area below content alone,
        # which strands stale glyphs from previous renders.
        self._menu_cols = 30
        self._detail_cols = 60
        self._pane_rows = 20
        self._last_size: Tuple[int, int] = (0, 0)

        self.menu_control: Optional[FormattedTextControl] = None
        self.detail_control: Optional[FormattedTextControl] = None
        self.detail_window: Optional[Window] = None

        self._refresh_data()

    # -- data helpers ------------------------------------------------------

    def _refresh_data(self) -> None:
        from code_puppy.plugins import get_loaded_plugins
        from code_puppy.plugins.config import get_disabled_plugins

        loaded = get_loaded_plugins()
        self.disabled = get_disabled_plugins()

        entries: List[_PluginEntry] = []
        for tier in ("builtin", "user", "project"):
            for name in sorted(loaded.get(tier, [])):
                entries.append(_PluginEntry(name, tier))
        self.plugins = entries

    def _current(self) -> Optional[_PluginEntry]:
        if 0 <= self.selected_idx < len(self.plugins):
            return self.plugins[self.selected_idx]
        return None

    def _toggle_current(self) -> None:
        entry = self._current()
        if not entry:
            return
        from code_puppy.plugins.config import set_plugin_disabled

        is_disabled = entry.name in self.disabled
        set_plugin_disabled(entry.name, not is_disabled)
        self._changed = True
        self.detail_scroll = 0
        self._refresh_data()
        self.update_display()

    # -- display update ----------------------------------------------------

    def update_display(self) -> None:
        # fill_pane writes every cell of every row — see its docstring for
        # the stale-glyph rationale.
        if self.menu_control:
            self.menu_control.text = fill_pane(
                render_list(self), self._menu_cols, self._pane_rows
            )
        if self.detail_control:
            sliced = drop_leading_lines(render_detail(self), self.detail_scroll)
            self.detail_control.text = fill_pane(
                sliced, self._detail_cols, self._pane_rows
            )

    def _max_detail_scroll(self) -> int:
        """Topmost line we may scroll to, keeping a screenful visible."""
        total = count_lines(render_detail(self))
        visible = 1
        if self.detail_window is not None and self.detail_window.render_info:
            visible = max(1, self.detail_window.render_info.window_height)
        return max(0, total - visible)

    def _scroll_detail(self, delta: int) -> None:
        new = max(0, min(self.detail_scroll + delta, self._max_detail_scroll()))
        if new != self.detail_scroll:
            self.detail_scroll = new
            self.update_display()

    # -- application -------------------------------------------------------

    def _measure_terminal(self) -> Tuple[int, int]:
        """Return (cols, rows) of the current terminal, with sane fallbacks."""
        try:
            size = shutil.get_terminal_size(fallback=(120, 40))
            return max(60, size.columns), max(15, size.lines)
        except Exception:
            return 120, 40

    def _recompute_dimensions(self) -> bool:
        """Re-measure the terminal and recompute pane widths.

        Returns True when the size actually changed. The width-callable
        closures in ``run`` read ``self._menu_cols`` / ``self._detail_cols``
        on every render, so updating these here automatically reflows the
        layout on terminal resize.
        """
        cols, rows = self._measure_terminal()
        if self._last_size == (cols, rows):
            return False
        self._last_size = (cols, rows)
        # Two side-by-side Frames cost 4 columns of border (1 per side, per
        # frame). Anything more leaves dead space on the right edge.
        usable_cols = max(40, cols - 4)
        # 35% / 65% split, with a minimum so the menu pane is always usable.
        self._menu_cols = max(20, min(40, int(usable_cols * 0.35)))
        self._detail_cols = max(20, usable_cols - self._menu_cols)
        # Reserve 2 rows for the Frame's top + bottom borders.
        self._pane_rows = max(5, rows - 2)
        return True

    def _set_selection(self, new_idx: int) -> None:
        """Move selection to *new_idx* (clamped), resetting detail scroll.

        Single chokepoint for every selection mutation -- ``_move_selection``,
        the jump-to-first/last actions, and the page jumps all funnel through
        here so the "reset detail scroll + keep selection's page visible"
        contract can't drift between callers.
        """
        if not self.plugins:
            return
        new_idx = max(0, min(new_idx, len(self.plugins) - 1))
        if new_idx == self.selected_idx:
            return
        self.selected_idx = new_idx
        self.detail_scroll = 0
        self.current_page = ensure_visible_page(
            self.selected_idx,
            self.current_page,
            len(self.plugins),
            PAGE_SIZE,
        )

    def _move_selection(self, delta: int) -> None:
        """Shift the selection by *delta*, clamped, and keep the page in view."""
        self._set_selection(self.selected_idx + delta)

    def _change_page(self, delta: int) -> None:
        """Move the page by *delta* (clamped) and jump selection to its head."""
        total_pages = get_total_pages(len(self.plugins), PAGE_SIZE)
        new_page = max(0, min(self.current_page + delta, total_pages - 1))
        if new_page == self.current_page:
            return
        self.current_page = new_page
        self._set_selection(self.current_page * PAGE_SIZE)

    def _build_key_bindings(self) -> KeyBindings:
        """Wire keys to match the ``inspect_history`` plugin's mental model.

        Both plugins share the same split-pane shape (list + scrollable
        detail). Keeping the bindings aligned means muscle memory carries
        over. The mental model (lifted from inspect_history):

        * Left-hand keys (``h``, ``j``) move things UP.
        * Right-hand keys (``k``, ``l``) move things DOWN.
        * ``h``/``l`` (and ``left``/``right``) scroll the *detail* pane.
        * ``j``/``k`` (and ``up``/``down``, ``c-p``/``c-n``) move the
          *selection* in the list.
        * ``pageup``/``pagedown`` page through the list.
        * ``g``/``home`` and ``G``/``end`` jump to first/last.
        """
        kb = KeyBindings()

        # -- Selection (j = up, k = down -- inspect_history convention) ---
        @kb.add("up")
        @kb.add("c-p")
        @kb.add("j")
        def _(event):
            self._move_selection(-1)
            self.update_display()

        @kb.add("down")
        @kb.add("c-n")
        @kb.add("k")
        def _(event):
            self._move_selection(+1)
            self.update_display()

        # -- Page through the list -----------------------------------------
        @kb.add("pageup")
        def _(event):
            self._change_page(-1)
            self.update_display()

        @kb.add("pagedown")
        def _(event):
            self._change_page(+1)
            self.update_display()

        # -- Jump to first / last ------------------------------------------
        @kb.add("home")
        @kb.add("g")
        def _(event):
            self._set_selection(0)
            self.update_display()

        @kb.add("end")
        @kb.add("G")
        def _(event):
            self._set_selection(len(self.plugins) - 1)
            self.update_display()

        # -- Detail pane scroll (h/left = up, l/right = down) --------------
        @kb.add("h")
        @kb.add("left")
        def _(event):
            self._scroll_detail(-1)

        @kb.add("l")
        @kb.add("right")
        def _(event):
            self._scroll_detail(+1)

        # -- Actions / exit ------------------------------------------------
        @kb.add("enter")
        def _(event):
            self._toggle_current()
            self.result = "changed"

        @kb.add("q")
        @kb.add("escape")
        @kb.add("c-c")
        def _(event):
            self.result = "quit"
            event.app.exit()

        return kb

    def _build_layout(self) -> Layout:
        """Build the side-by-side Plugins / Details layout.

        Pane widths are *callables* so they track the live terminal: when the
        window is resized, ``_recompute_dimensions`` updates the cached cols
        and these closures hand prompt_toolkit the fresh numbers on the very
        next render. ``wrap_lines=False`` is critical: auto-wrap bleeds
        characters into the divider/border column and leaves stale glyphs on
        redraw. Long lines (description, path) are pre-wrapped by the renderer.
        """

        def menu_width() -> Dimension:
            return Dimension(min=20, max=self._menu_cols, preferred=self._menu_cols)

        def detail_width() -> Dimension:
            return Dimension(min=20, max=self._detail_cols, preferred=self._detail_cols)

        def pane_height() -> Dimension:
            return Dimension(min=5, max=self._pane_rows, preferred=self._pane_rows)

        menu_window = Window(
            content=self.menu_control,
            wrap_lines=False,
            width=menu_width,
            height=pane_height,
        )
        detail_window = Window(
            content=self.detail_control,
            wrap_lines=False,
            width=detail_width,
            height=pane_height,
        )
        self.detail_window = detail_window

        menu_frame = Frame(menu_window, title="Plugins")
        detail_frame = Frame(detail_window, title="Details")

        return Layout(VSplit([menu_frame, detail_frame]))

    def run(self) -> Optional[str]:
        self.menu_control = FormattedTextControl(text="")
        self.detail_control = FormattedTextControl(text="")

        self._recompute_dimensions()

        layout = self._build_layout()
        kb = self._build_key_bindings()

        app = Application(
            layout=layout,
            key_bindings=kb,
            full_screen=False,
            mouse_support=False,
        )

        # Live resize: prompt_toolkit re-renders on SIGWINCH automatically, but
        # our pre-wrapped detail text is laid out to a fixed width and won't
        # reflow on its own. ``before_render`` fires ahead of layout sizing, so
        # recomputing dimensions here lets the width callables AND the next
        # render's pre-wrap both see the fresh geometry in the same frame.
        # ``_recompute_dimensions`` is a no-op when the size hasn't changed, so
        # there's no per-frame waste.
        def _on_before_render(_app: Application) -> None:
            if self._recompute_dimensions():
                self.update_display()

        app.before_render += _on_before_render

        set_awaiting_user_input(True)

        sys.stdout.write("\033[?1049h")  # Enter alternate buffer
        sys.stdout.write("\033[2J\033[H")  # Clear and home
        sys.stdout.flush()
        time.sleep(0.05)

        try:
            self.update_display()

            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()

            app.run(in_thread=True)

        finally:
            sys.stdout.write("\033[?1049l")  # Exit alternate buffer
            sys.stdout.flush()

            try:
                import termios

                termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
            except Exception:
                pass

            time.sleep(0.1)
            set_awaiting_user_input(False)

        return self.result


def run_plugins_menu() -> Optional[str]:
    """Entry point: create and run the plugins TUI, return the result."""
    from code_puppy.messaging import emit_warning

    menu = PluginsMenu()
    result = menu.run()

    if menu._changed:
        emit_warning("Restart Code Puppy for plugin changes to take effect.")

    return result


# Re-export for callers that don't want to know about the render split.
__all__ = ["PluginsMenu", "Fragments", "run_plugins_menu"]
