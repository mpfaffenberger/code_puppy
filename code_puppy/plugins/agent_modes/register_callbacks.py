"""Register Plan/Build mode policy and UX."""

from __future__ import annotations

import sys

from prompt_toolkit.filters import Condition

from code_puppy.callbacks import register_callback
from code_puppy.command_line.set_menu_schema import Setting, SettingsCategory
from code_puppy.messaging import emit_info, emit_success, emit_warning

from .policy import guard_tool_call, mode_prompt, require_shell_approval
from .prompt_patch import install_prompt_patch
from .state import get_agent_mode, set_agent_mode, toggle_agent_mode


def _invalidate_dynamic_prompt() -> None:
    try:
        from code_puppy.agents import get_current_agent

        get_current_agent().invalidate_dynamic_prompt()
    except Exception:
        pass


def _help():
    return [("/mode [plan|build]", "Show or change the read-only agent mode")]


def _command(command: str, name: str):
    if name != "mode":
        return None
    parts = command.split()
    if len(parts) == 1:
        emit_info(f"Agent mode: {get_agent_mode().value}")
        return True
    try:
        selected = set_agent_mode(parts[1])
    except ValueError:
        emit_warning("Usage: /mode [plan|build]")
        return True
    _invalidate_dynamic_prompt()
    emit_success(f"Agent mode changed to {selected.value.upper()}")
    return True


def _register_keybindings(bindings):
    """Use Tab to toggle only when the prompt buffer is empty."""
    from prompt_toolkit.application.current import get_app

    empty_buffer = Condition(lambda: not get_app().current_buffer.text)

    @bindings.add("tab", filter=empty_buffer, eager=True)
    def _toggle(event):
        selected = toggle_agent_mode()
        _invalidate_dynamic_prompt()
        sys.stdout.write(f"[mode] {selected.value.upper()}\n")
        sys.stdout.flush()
        event.app.invalidate()


def _settings():
    return SettingsCategory(
        name="Agent Mode",
        settings=(
            Setting(
                key="agent_mode",
                display_name="Agent Mode",
                description="Plan is read-only; Build enables normal tool policies.",
                type_hint="choice",
                valid_values=("plan", "build"),
                effective_getter=lambda: get_agent_mode().value,
            ),
        ),
    )


def _startup():
    install_prompt_patch()


register_callback("pre_tool_call", guard_tool_call)
register_callback("run_shell_command", require_shell_approval)
register_callback("load_prompt", mode_prompt)
register_callback("custom_command", _command)
register_callback("custom_command_help", _help)
register_callback("register_keybindings", _register_keybindings)
register_callback("register_settings", _settings)
register_callback("startup", _startup)
