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
from prompt_toolkit.application.current import get_app
from prompt_toolkit.filters import Condition
from prompt_toolkit.layout import Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import TextArea

from code_puppy.plugins.plugin_list.plugins_menu_layout import (
    build_key_bindings,
    build_layout,
)

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
    """Lightweight struct for a plugin row.

    ``status`` is "loaded" for imported plugins; project plugins held back
    by the trust gate carry their gate status instead ("untrusted",
    "changed", "disabled", "error") so the TUI can show them without
    pretending they're active.
    """

    __slots__ = ("name", "tier", "status")

    def __init__(self, name: str, tier: str, status: str = "loaded") -> None:
        self.name = name
        self.tier = tier
        self.status = status


class PluginsMenu:
    """Interactive TUI for enabling/disabling plugins.

    The view (``plugins_menu_render``) reads the following attributes on this
    object — keep them stable to avoid breaking the render contract:

    * ``plugins``, ``disabled``, ``selected_idx``, ``current_page``, ``page_size``
    * ``project_dir`` (posix string or None)
    * ``trust_target``, ``trust_error``, ``trust_feedback`` (popup state)
    * ``_detail_cols``, ``_pane_rows``
    * ``_changed``
    * ``_current()``

    Entries carry a ``status`` ("loaded" or a trust-gate status) — the
    renderer branches on it, so keep it stable too.
    """

    def __init__(self, focus_plugin: Optional[str] = None) -> None:
        """*focus_plugin* preselects that plugin; if it's trust-gated, the
        risk-acceptance popup opens immediately (used by ``/plugins enable``
        to bring the user straight to the ceremony)."""
        self.plugins: List[_PluginEntry] = []
        self.disabled: set[str] = set()
        self.project_dir: Optional[str] = None

        # Trust popup state. While ``trust_target`` is set, the modal is
        # visible, ALL list keybindings are filter-disabled (so typing the
        # accept word can't trigger shortcuts), and focus sits on the input.
        self.trust_target: Optional[_PluginEntry] = None
        self.trust_error: str = ""
        self.trust_feedback: str = ""
        self.trust_input: TextArea = TextArea(
            multiline=False, height=1, accept_handler=self._accept_trust
        )
        self._modal_open = Condition(lambda: self.trust_target is not None)

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

        if focus_plugin:
            for i, entry in enumerate(self.plugins):
                if entry.name == focus_plugin:
                    self.selected_idx = i
                    self.current_page = ensure_visible_page(
                        i, self.current_page, len(self.plugins), PAGE_SIZE
                    )
                    if entry.status in ("untrusted", "changed"):
                        self._open_trust_modal(entry)
                    break

    # -- data helpers ------------------------------------------------------

    def _refresh_data(self) -> None:
        from code_puppy.plugins import (
            get_loaded_plugins,
            get_project_plugin_status,
            get_project_plugins_directory,
        )
        from code_puppy.plugins.config import get_disabled_plugins

        loaded = get_loaded_plugins()
        self.disabled = get_disabled_plugins()

        project_dir = get_project_plugins_directory()
        self.project_dir = project_dir.as_posix() if project_dir else None

        entries: List[_PluginEntry] = []
        for tier in ("builtin", "user", "project"):
            for name in sorted(loaded.get(tier, [])):
                entries.append(_PluginEntry(name, tier))

        # Project plugins held back by the trust gate — shown so Enter can
        # open the ceremony popup on them.
        statuses = get_project_plugin_status()
        shown = {e.name for e in entries if e.tier == "project"}
        for name in sorted(statuses):
            if statuses[name] != "loaded" and name not in shown:
                entries.append(_PluginEntry(name, "project", statuses[name]))

        self.plugins = entries

    def _current(self) -> Optional[_PluginEntry]:
        if 0 <= self.selected_idx < len(self.plugins):
            return self.plugins[self.selected_idx]
        return None

    def _toggle_current(self) -> None:
        entry = self._current()
        if not entry:
            return
        self.trust_feedback = ""

        if entry.status in ("untrusted", "changed"):
            # Ceremony required — open the risk-acceptance popup.
            self._open_trust_modal(entry)
            return
        if entry.status in ("disabled", "error"):
            # Already trusted; just (re)activate — no ceremony needed.
            from code_puppy.plugins.plugin_list.project_trust_flow import (
                activate_project_plugin,
            )

            _ok, message = activate_project_plugin(entry.name)
            self.trust_feedback = message
            self.detail_scroll = 0
            self._refresh_data()
            self.update_display()
            return

        from code_puppy.plugins.config import set_plugin_disabled

        is_disabled = entry.name in self.disabled
        set_plugin_disabled(entry.name, not is_disabled)
        self._changed = True
        self.detail_scroll = 0
        self._refresh_data()
        self.update_display()

    # -- trust popup ---------------------------------------------------------

    def _open_trust_modal(self, entry: _PluginEntry) -> None:
        self.trust_target = entry
        self.trust_error = ""
        self.trust_input.text = ""
        try:
            get_app().layout.focus(self.trust_input)
        except Exception:
            pass  # no running app (tests) — state alone drives the logic
        self.update_display()

    def _close_trust_modal(self) -> None:
        self.trust_target = None
        self.trust_error = ""
        self.trust_input.text = ""
        try:
            get_app().layout.focus(self.menu_control)
        except Exception:
            pass
        self.update_display()

    def _accept_trust(self, buff) -> bool:
        """Accept-handler for the popup input. Returns False to clear the box."""
        entry = self.trust_target
        if entry is None:
            return False
        from code_puppy.plugins.plugin_list.project_trust_flow import (
            ACCEPT_WORD,
            grant_trust_and_load,
        )

        if buff.text.strip().lower() != ACCEPT_WORD:
            self.trust_error = (
                f"That isn't '{ACCEPT_WORD}' — type it exactly, or press Esc to cancel."
            )
            self.update_display()
            return False

        _ok, message = grant_trust_and_load(entry.name)
        self.trust_feedback = message
        self._refresh_data()
        self._close_trust_modal()
        return False

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

    def run(self) -> Optional[str]:
        self.menu_control = FormattedTextControl(text="", focusable=True)
        self.detail_control = FormattedTextControl(text="")

        self._recompute_dimensions()

        layout = build_layout(self)
        if self.trust_target is not None:
            # Popup pre-opened (focus_plugin ceremony): focus its input now
            # that the layout exists — _open_trust_modal ran before any app.
            try:
                layout.focus(self.trust_input)
            except Exception:
                pass
        kb = build_key_bindings(self)

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


def run_plugins_menu(focus_plugin: Optional[str] = None) -> Optional[str]:
    """Entry point: create and run the plugins TUI, return the result.

    *focus_plugin* preselects a plugin and, when it's trust-gated, opens
    the risk-acceptance popup straight away.
    """
    from code_puppy.messaging import emit_warning

    menu = PluginsMenu(focus_plugin=focus_plugin)
    result = menu.run()

    if menu._changed:
        emit_warning("Restart Code Puppy for plugin changes to take effect.")

    return result


# Re-export for callers that don't want to know about the render split.
__all__ = ["PluginsMenu", "Fragments", "run_plugins_menu"]
