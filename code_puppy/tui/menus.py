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


def open_agent_picker(app: "CooperApp") -> None:
    """Open the agent switcher and apply the chosen agent on dismiss."""
    from code_puppy.agents.agent_manager import (
        get_available_agents,
        get_current_agent_name,
        set_current_agent,
    )
    from code_puppy.messaging import emit_error, emit_success

    current = get_current_agent_name()
    agents = get_available_agents()  # name -> display name
    choices = [
        ListChoice(
            id=name,
            label=display,
            search=f"{name} {display}",
            active=(name == current),
        )
        for name, display in sorted(agents.items(), key=lambda kv: kv[1].lower())
    ]

    def _apply(agent_id) -> None:
        if not agent_id or agent_id == current:
            return
        try:
            set_current_agent(agent_id)
            emit_success(f"Switched to agent: {agent_id}")
        except Exception as exc:
            emit_error(f"Failed to switch agent: {exc}")

    app.push_screen(
        FilterableListScreen(f"Select an agent (current: {current})", choices),
        _apply,
    )


def open_autosave_picker(app: "CooperApp") -> None:
    """Open a picker over saved autosave sessions; load the chosen one.

    Replaces the classic ``__AUTOSAVE_LOAD__`` interactive picker (which used
    prompt_toolkit). The post-load history preview is skipped because the
    classic ``display_resumed_history`` prints to its own console, which would
    corrupt the Textual screen.
    """
    from pathlib import Path

    from code_puppy.agents import get_current_agent
    from code_puppy.config import (
        AUTOSAVE_DIR,
        set_current_autosave_from_session_name,
    )
    from code_puppy.messaging import emit_error, emit_success, emit_warning
    from code_puppy.session_storage import list_sessions, load_session

    base_dir = Path(AUTOSAVE_DIR)
    sessions = list_sessions(base_dir)
    if not sessions:
        emit_warning("No saved autosave sessions found.")
        return

    choices = [ListChoice(id=name, label=name) for name in sessions]

    def _apply(session_id) -> None:
        if not session_id:
            emit_warning("Autosave load cancelled")
            return
        try:
            history = load_session(session_id, base_dir)
            get_current_agent().set_message_history(history)
            set_current_autosave_from_session_name(session_id)
            emit_success(f"Autosave loaded: {session_id} ({len(history)} messages)")
        except Exception as exc:
            emit_error(f"Failed to load autosave: {exc}")

    app.push_screen(FilterableListScreen("Load autosave session", choices), _apply)


def open_set_picker(app: "CooperApp") -> None:
    """Two-step /set: pick a config key, then edit its value.

    Applies through the validated ``apply_setting`` path (same as
    ``/set key value``), not a raw config write.
    """
    from code_puppy.config import get_config_keys, get_value
    from code_puppy.messaging import UserInputRequest

    from .screens.interactive import TextInputModal

    keys = sorted(get_config_keys())
    choices = [
        ListChoice(
            id=key,
            label=f"{key} = {get_value(key) if get_value(key) is not None else '(unset)'}",
            search=key,
        )
        for key in keys
    ]

    def _on_key(key) -> None:
        if not key:
            return
        current = get_value(key) or ""
        request = UserInputRequest(
            prompt_id="__set__",
            prompt_text=f"Set {key}:",
            default_value=current,
        )

        def _on_value(value) -> None:
            if value is None:  # cancelled
                return
            from code_puppy.command_line.config_apply import apply_setting
            from code_puppy.messaging import emit_error, emit_success

            result = apply_setting(key, value, reload_agent=True)
            if result.ok:
                emit_success(f"Set {key} = {value}")
            else:
                emit_error(result.error or "Failed to apply setting.")

        app.push_screen(TextInputModal(request, prefill=True), _on_value)

    app.push_screen(FilterableListScreen("Settings (/set)", choices), _on_key)


def open_diff_picker(app: "CooperApp") -> None:
    """Two-step /diff: pick the addition color, then the deletion color.

    Rows render the actual color as a swatch. Skips the classic live-preview
    pane but applies through the real setters (values normalize to hex).
    """
    from code_puppy.command_line.diff_menu import ADDITION_COLORS, DELETION_COLORS
    from code_puppy.config import (
        get_diff_addition_color,
        get_diff_deletion_color,
        set_diff_addition_color,
        set_diff_deletion_color,
    )
    from code_puppy.messaging import emit_success

    cur_add = get_diff_addition_color()
    add_choices = [
        ListChoice(
            id=hex_value,
            label=name,
            search=name,
            style=f"on {hex_value}",
            active=(hex_value.lower() == cur_add.lower()),
        )
        for name, hex_value in ADDITION_COLORS.items()
    ]

    def _on_add(add_hex) -> None:
        if add_hex:
            set_diff_addition_color(add_hex)
        cur_del = get_diff_deletion_color()
        del_choices = [
            ListChoice(
                id=hex_value,
                label=name,
                search=name,
                style=f"on {hex_value}",
                active=(hex_value.lower() == cur_del.lower()),
            )
            for name, hex_value in DELETION_COLORS.items()
        ]

        def _on_del(del_hex) -> None:
            if del_hex:
                set_diff_deletion_color(del_hex)
            emit_success("Diff colors updated.")

        app.push_screen(
            FilterableListScreen("Diff deletion color", del_choices), _on_del
        )

    app.push_screen(FilterableListScreen("Diff addition color", add_choices), _on_add)


# command name (without leading slash) -> opener.
# Aliases that mirror the classic command registry are included so the bare
# alias also opens the modal (e.g. /a == /agent).
MENU_OPENERS: Dict[str, Callable[["CooperApp"], None]] = {
    "model": open_model_picker,
    "agent": open_agent_picker,
    "a": open_agent_picker,
    "agents": open_agent_picker,
    "set": open_set_picker,
    "diff": open_diff_picker,
}
