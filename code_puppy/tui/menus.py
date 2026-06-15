"""Phase 3: map menu slash-commands to Textual modal openers.

In the classic UI, commands like ``/model`` launch prompt_toolkit menus that
fight the Textual screen. Here we intercept the bare command and open a
``ModalScreen`` instead. Commands with explicit args (e.g. ``/model gpt-x``)
fall through to the normal handler so direct-set still works.

Add a menu by writing an opener ``(app) -> None`` that pushes a screen and
applies the dismissed result, then registering it in ``MENU_OPENERS``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Dict, Optional

from .screens.base import FilterableListScreen, ListChoice

if TYPE_CHECKING:
    from .app import CooperApp


def _open_judges(app: "CooperApp") -> None:
    # Imported lazily to keep menus.py's import graph light.
    from .menu_judges import open_judges

    open_judges(app)


def _open_add_model(app: "CooperApp") -> None:
    from .menu_add_model import open_add_model

    open_add_model(app)


def _open_uc(app: "CooperApp") -> None:
    from .menu_uc import open_uc

    open_uc(app)


def _open_tools(app: "CooperApp") -> None:
    """Show the available-tools catalogue in a responsive modal."""
    from .screens.tools import ToolsScreen

    app.push_screen(ToolsScreen())


def open_onboarding(app: "CooperApp") -> None:
    """Show the onboarding slide deck; mark complete + optionally pick a model."""
    from .screens.onboarding import OnboardingScreen

    def _on_done(result) -> None:
        try:
            from code_puppy.command_line.onboarding_wizard import (
                mark_onboarding_complete,
            )

            mark_onboarding_complete()
        except Exception:
            pass
        if result == "model":
            open_model_picker(app)

    app.push_screen(OnboardingScreen(), _on_done)


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
    """Open the two-panel agent switcher and apply the chosen agent on dismiss."""
    from code_puppy.agents import get_agent_descriptions
    from code_puppy.agents.agent_manager import (
        get_available_agents,
        get_current_agent_name,
        set_current_agent,
    )
    from code_puppy.messaging import emit_error, emit_success

    from .screens.agent_picker import AgentPickerScreen

    current = get_current_agent_name()
    agents = get_available_agents()  # name -> display name
    descriptions = get_agent_descriptions()
    entries = [
        (name, display, descriptions.get(name, "No description available"))
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

    app.push_screen(AgentPickerScreen(entries, current), _apply)


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

    from code_puppy.command_line.autosave_menu import _get_session_entries

    from .screens.session_picker import SessionPickerScreen

    base_dir = Path(AUTOSAVE_DIR)
    if not list_sessions(base_dir):
        emit_warning("No saved autosave sessions found.")
        return

    # (name, metadata) sorted most-recent-first, matching the classic panel.
    entries = _get_session_entries(base_dir)

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

    app.push_screen(SessionPickerScreen(entries, base_dir), _apply)


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


def open_colors_picker(app: "CooperApp") -> None:
    """Two-panel /colors: banner list + live preview (mirrors classic)."""
    from .screens.colors_picker import ColorsPickerScreen

    app.push_screen(ColorsPickerScreen())


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
    "colors": open_colors_picker,
    "judges": _open_judges,
    "add_model": _open_add_model,
    "uc": _open_uc,
    "tutorial": open_onboarding,
    "tools": _open_tools,
}


def _plugin_screen_openers() -> Dict[str, Callable[["CooperApp"], None]]:
    """Menu openers contributed by plugins via the register_screen hook."""
    openers: Dict[str, Callable[["CooperApp"], None]] = {}
    try:
        from code_puppy.callbacks import on_register_screens

        entries = on_register_screens() or []
    except Exception:
        return openers
    # on_register_screens returns one result per callback, each a list of
    # dicts -> flatten.
    for result in entries:
        result_list = result if isinstance(result, list) else [result]
        for entry in result_list:
            if not isinstance(entry, dict):
                continue
            opener = entry.get("open")
            if not callable(opener):
                continue
            names = [entry.get("command"), *entry.get("aliases", [])]
            for name in names:
                if name:
                    openers[str(name).lstrip("/").lower()] = opener
    return openers


def get_menu_opener(name: str) -> Optional[Callable[["CooperApp"], None]]:
    """Resolve a bare menu command to an opener (builtin first, then plugins)."""
    key = name.lstrip("/").lower()
    if key in MENU_OPENERS:
        return MENU_OPENERS[key]
    return _plugin_screen_openers().get(key)
