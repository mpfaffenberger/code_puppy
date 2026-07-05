"""Layout + keybinding construction for the /plugins TUI.

Split from ``plugins_menu`` the same way ``plugins_menu_render`` was: these
are pure *construction* helpers that read the menu's state and hand back
prompt_toolkit objects. No app state lives here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import (
    ConditionalContainer,
    Dimension,
    Float,
    FloatContainer,
    HSplit,
    Layout,
    VSplit,
    Window,
)
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame

if TYPE_CHECKING:  # pragma: no cover - import-cycle guard
    from code_puppy.plugins.plugin_list.plugins_menu import PluginsMenu


def build_key_bindings(menu: "PluginsMenu") -> KeyBindings:
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

    # Every list binding is gated on the trust popup being CLOSED —
    # single-letter shortcuts (j/k/g/q...) must not fire while the user
    # is typing the accept word into the popup's text field.
    no_modal = ~menu._modal_open

    # -- Selection (j = up, k = down -- inspect_history convention) ---
    @kb.add("up", filter=no_modal)
    @kb.add("c-p", filter=no_modal)
    @kb.add("j", filter=no_modal)
    def _(event):
        menu._move_selection(-1)
        menu.update_display()

    @kb.add("down", filter=no_modal)
    @kb.add("c-n", filter=no_modal)
    @kb.add("k", filter=no_modal)
    def _(event):
        menu._move_selection(+1)
        menu.update_display()

    # -- Page through the list -----------------------------------------
    @kb.add("pageup", filter=no_modal)
    def _(event):
        menu._change_page(-1)
        menu.update_display()

    @kb.add("pagedown", filter=no_modal)
    def _(event):
        menu._change_page(+1)
        menu.update_display()

    # -- Jump to first / last ------------------------------------------
    @kb.add("home", filter=no_modal)
    @kb.add("g", filter=no_modal)
    def _(event):
        menu._set_selection(0)
        menu.update_display()

    @kb.add("end", filter=no_modal)
    @kb.add("G", filter=no_modal)
    def _(event):
        menu._set_selection(len(menu.plugins) - 1)
        menu.update_display()

    # -- Detail pane scroll (h/left = up, l/right = down) --------------
    @kb.add("h", filter=no_modal)
    @kb.add("left", filter=no_modal)
    def _(event):
        menu._scroll_detail(-1)

    @kb.add("l", filter=no_modal)
    @kb.add("right", filter=no_modal)
    def _(event):
        menu._scroll_detail(+1)

    # -- Actions / exit ------------------------------------------------
    @kb.add("enter", filter=no_modal)
    def _(event):
        menu._toggle_current()
        menu.result = "changed"

    @kb.add("q", filter=no_modal)
    @kb.add("escape", filter=no_modal)
    @kb.add("c-c", filter=no_modal)
    def _(event):
        menu.result = "quit"
        event.app.exit()

    # -- Trust popup: Esc / Ctrl+C cancel (Enter is handled by the
    #    focused TextArea's accept_handler) ----------------------------
    @kb.add("escape", filter=menu._modal_open)
    @kb.add("c-c", filter=menu._modal_open)
    def _(event):
        menu._close_trust_modal()

    return kb


def build_layout(menu: "PluginsMenu") -> Layout:
    """Build the side-by-side Plugins / Details layout plus the trust float.

    Pane widths are *callables* so they track the live terminal: when the
    window is resized, ``_recompute_dimensions`` updates the cached cols
    and these closures hand prompt_toolkit the fresh numbers on the very
    next render. ``wrap_lines=False`` is critical: auto-wrap bleeds
    characters into the divider/border column and leaves stale glyphs on
    redraw. Long lines (description, path) are pre-wrapped by the renderer.
    """

    def menu_width() -> Dimension:
        return Dimension(min=20, max=menu._menu_cols, preferred=menu._menu_cols)

    def detail_width() -> Dimension:
        return Dimension(min=20, max=menu._detail_cols, preferred=menu._detail_cols)

    def pane_height() -> Dimension:
        return Dimension(min=5, max=menu._pane_rows, preferred=menu._pane_rows)

    menu_window = Window(
        content=menu.menu_control,
        wrap_lines=False,
        width=menu_width,
        height=pane_height,
    )
    detail_window = Window(
        content=menu.detail_control,
        wrap_lines=False,
        width=detail_width,
        height=pane_height,
    )
    menu.detail_window = detail_window

    menu_frame = Frame(menu_window, title="Plugins")
    detail_frame = Frame(detail_window, title="Details")

    # Trust popup: a centered float over the panes, only rendered while
    # a ceremony is in progress. The FormattedTextControl re-renders via
    # its callable, and the TextArea receives focus (and thus all
    # printable keys — the list shortcuts are filter-disabled).
    from code_puppy.plugins.plugin_list.plugins_menu_render import (
        render_trust_modal,
    )

    def modal_width() -> Dimension:
        cols = min(64, max(40, menu._menu_cols + menu._detail_cols - 8))
        return Dimension(min=40, max=cols, preferred=cols)

    modal_body = HSplit(
        [
            Window(
                content=FormattedTextControl(lambda: render_trust_modal(menu)),
                wrap_lines=False,
                dont_extend_height=True,
            ),
            menu.trust_input,
        ],
        width=modal_width,
    )
    modal_float = Float(
        content=ConditionalContainer(
            Frame(modal_body, title="Enable project plugin?"),
            filter=menu._modal_open,
        )
    )

    return Layout(
        FloatContainer(
            content=VSplit([menu_frame, detail_frame]),
            floats=[modal_float],
        )
    )
