from unittest.mock import MagicMock, patch

import pytest
from prompt_toolkit.key_binding import KeyBindings

from code_puppy.plugins.agent_modes.policy import (
    MUTATING_TOOLS,
    guard_tool_call,
    mode_prompt,
    require_shell_approval,
)
from code_puppy.plugins.agent_modes.register_callbacks import (
    _command,
    _register_keybindings,
    _settings,
)
from code_puppy.plugins.agent_modes.state import (
    AgentMode,
    get_agent_mode,
    set_agent_mode,
    toggle_agent_mode,
)


def test_mode_state_defaults_and_validates():
    with patch("code_puppy.plugins.agent_modes.state.get_value", return_value=None):
        assert get_agent_mode() is AgentMode.BUILD
    with patch(
        "code_puppy.plugins.agent_modes.state.get_value", return_value="invalid"
    ):
        assert get_agent_mode() is AgentMode.BUILD


def test_set_and_toggle_mode_persist_values():
    with patch("code_puppy.plugins.agent_modes.state.set_value") as save:
        assert set_agent_mode("plan") is AgentMode.PLAN
        save.assert_called_once_with("agent_mode", "plan")
    with (
        patch(
            "code_puppy.plugins.agent_modes.state.get_agent_mode",
            return_value=AgentMode.PLAN,
        ),
        patch("code_puppy.plugins.agent_modes.state.set_agent_mode") as save_mode,
    ):
        save_mode.return_value = AgentMode.BUILD
        assert toggle_agent_mode() is AgentMode.BUILD
        save_mode.assert_called_once_with(AgentMode.BUILD)
    with pytest.raises(ValueError):
        set_agent_mode("unknown")


def test_plan_blocks_mutations_but_not_reads():
    with patch(
        "code_puppy.plugins.agent_modes.policy.get_agent_mode",
        return_value=AgentMode.PLAN,
    ):
        for tool_name in MUTATING_TOOLS:
            result = guard_tool_call(tool_name, {})
            assert result and result["blocked"] is True
            assert "Plan mode" in result["reason"]
        assert guard_tool_call("read_file", {}) is None


def test_build_does_not_change_tool_or_shell_policy():
    with patch(
        "code_puppy.plugins.agent_modes.policy.get_agent_mode",
        return_value=AgentMode.BUILD,
    ):
        assert guard_tool_call("create_file", {}) is None
        assert require_shell_approval(None, "git status") is None
        assert "BUILD" in mode_prompt()


def test_plan_requires_shell_approval_and_updates_prompt():
    with patch(
        "code_puppy.plugins.agent_modes.policy.get_agent_mode",
        return_value=AgentMode.PLAN,
    ):
        result = require_shell_approval(None, "git status")
        assert result and result["requires_approval"] is True
        assert "PLAN" in mode_prompt()


def test_mode_command_changes_mode_and_handles_invalid_input():
    with (
        patch(
            "code_puppy.plugins.agent_modes.register_callbacks.set_agent_mode",
            return_value=AgentMode.PLAN,
        ) as set_mode,
        patch(
            "code_puppy.plugins.agent_modes.register_callbacks._invalidate_dynamic_prompt"
        ) as invalidate,
        patch("code_puppy.plugins.agent_modes.register_callbacks.emit_success"),
    ):
        assert _command("/mode plan", "mode") is True
        set_mode.assert_called_once_with("plan")
        invalidate.assert_called_once()

    with (
        patch(
            "code_puppy.plugins.agent_modes.register_callbacks.set_agent_mode",
            side_effect=ValueError,
        ),
        patch("code_puppy.plugins.agent_modes.register_callbacks.emit_warning") as warn,
    ):
        assert _command("/mode invalid", "mode") is True
        warn.assert_called_once()
    assert _command("/mode plan", "other") is None


def test_mode_setting_is_curated_choice():
    category = _settings()
    setting = category.settings[0]
    assert setting.key == "agent_mode"
    assert setting.valid_values == ("plan", "build")


def test_empty_prompt_tab_binding_toggles_mode():
    bindings = KeyBindings()
    _register_keybindings(bindings)
    binding = next(
        binding
        for binding in bindings.bindings
        if any(getattr(key, "value", str(key)) == "c-i" for key in binding.keys)
    )
    event = MagicMock()
    with (
        patch(
            "code_puppy.plugins.agent_modes.register_callbacks.toggle_agent_mode",
            return_value=AgentMode.PLAN,
        ),
        patch(
            "code_puppy.plugins.agent_modes.register_callbacks._invalidate_dynamic_prompt"
        ),
        patch("sys.stdout"),
    ):
        binding.handler(event)
    event.app.invalidate.assert_called_once()
