"""Precedence tests for persistent ``/set yolo_mode`` changes."""

from unittest.mock import patch

from code_puppy import config
from code_puppy.command_line.config_apply import apply_setting
from code_puppy.command_line.config_commands import handle_set_command


def setup_function():
    config.set_cli_yolo_override(None)


def teardown_function():
    config.set_cli_yolo_override(None)


def test_persistent_yolo_write_supersedes_cli_override():
    config.set_cli_yolo_override(False)

    with patch("code_puppy.config.set_config_value") as set_config:
        result = apply_setting("yolo_mode", "true", reload_agent=False)

    assert result.ok is True
    set_config.assert_called_once_with("yolo_mode", "true")
    assert config.get_cli_yolo_override() is None


def test_yolo_config_clears_cli_override_without_changing_persisted_value():
    config.set_cli_yolo_override(False)

    with (
        patch("code_puppy.config.set_config_value") as set_value,
        patch("code_puppy.config.reset_value") as reset_value,
        patch("code_puppy.agents.get_current_agent") as current_agent,
        patch("code_puppy.messaging.emit_success"),
        patch("code_puppy.messaging.emit_info"),
    ):
        assert handle_set_command("/set yolo_mode config") is True

    set_value.assert_not_called()
    reset_value.assert_not_called()
    current_agent.return_value.reload_code_generation_agent.assert_called_once()
    assert config.get_cli_yolo_override() is None
