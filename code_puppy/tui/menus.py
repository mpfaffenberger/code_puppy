"""Phase 3: map menu slash-commands to Textual modal openers.

In the classic UI, commands like ``/model`` launch prompt_toolkit menus that
fight the Textual screen. Here we intercept the bare command and open a
``ModalScreen`` instead. Commands with explicit args (e.g. ``/model gpt-x``)
fall through to the normal handler so direct-set still works.

Add a menu by writing an opener ``(app) -> None`` that pushes a screen and
applies the dismissed result, then registering it in ``MENU_OPENERS``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Dict

from .screens.base import FilterableListScreen, ListChoice

if TYPE_CHECKING:
    from .app import CooperApp


def open_model_picker(app: "CooperApp") -> None:
    """Open the model picker and apply the chosen model on dismiss."""
    from code_puppy.command_line.model_picker_completion import (
        get_active_model,
        load_model_names,
    )
    from code_puppy.messaging import emit_info
    from code_puppy.model_switching import set_model_and_reload_agent

    active = get_active_model()
    choices = [
        ListChoice(id=name, label=name, active=(name == active))
        for name in sorted(load_model_names())
    ]

    def _apply(model_id) -> None:
        if not model_id or model_id == active:
            return
        set_model_and_reload_agent(model_id)
        emit_info(f"Model set to: {model_id}")

    app.push_screen(
        FilterableListScreen(f"Select a model (current: {active})", choices),
        _apply,
    )


# command name (without leading slash) -> opener
MENU_OPENERS: Dict[str, Callable[["CooperApp"], None]] = {
    "model": open_model_picker,
}
