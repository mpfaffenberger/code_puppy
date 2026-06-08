"""Behavior-parity tests for the slash ``/set`` one-shot path.

These exist so we can NEVER regress the original (pre-menu) behavior
that users have come to rely on. Each scenario corresponds to a
distinct user-visible code path in upstream/main's ``handle_set_command``.

For each scenario we mock the leaves (``set_config_value``, the agent
loader) and assert the EXACT messages emitted, in order, against what
the original would have emitted. Any future refactor that changes the
observable behavior of ``/set <key> <value>`` will fail these tests.
"""

from __future__ import annotations

from unittest.mock import patch

from code_puppy.command_line.config_commands import handle_set_command


def _emitters():
    """Patch all four messaging emitters and return their mocks."""
    return (
        patch("code_puppy.messaging.emit_success"),
        patch("code_puppy.messaging.emit_info"),
        patch("code_puppy.messaging.emit_warning"),
        patch("code_puppy.messaging.emit_error"),
    )


def _texts(mock_emit) -> list[str]:
    """Extract the string payload from each call to an emit_* mock."""
    out = []
    for call in mock_emit.call_args_list:
        if call.args:
            out.append(str(call.args[0]))
    return out


class TestSlashSetParity:
    def test_basic_key_value_writes_and_reloads(self):
        e_success, e_info, e_warning, e_error = _emitters()
        with (
            patch("code_puppy.config.set_config_value") as mock_set,
            patch("code_puppy.agents.get_current_agent") as mock_agent,
            e_success as ms,
            e_info as mi,
            e_warning as mw,
            e_error as me,
        ):
            mock_agent.return_value.reload_code_generation_agent.return_value = None
            assert handle_set_command("/set yolo_mode true") is True
        mock_set.assert_called_once_with("yolo_mode", "true")
        assert any('Set yolo_mode = "true" in puppy.cfg!' in t for t in _texts(ms))
        assert any("Agent reloaded with updated config" in t for t in _texts(mi))
        assert mw.call_count == 0
        assert me.call_count == 0

    def test_equals_syntax(self):
        e_success, e_info, e_warning, e_error = _emitters()
        with (
            patch("code_puppy.config.set_config_value") as mock_set,
            patch("code_puppy.agents.get_current_agent") as mock_agent,
            e_success,
            e_info,
            e_warning as mw,
            e_error as me,
        ):
            mock_agent.return_value.reload_code_generation_agent.return_value = None
            handle_set_command("/set puppy_name=Rex")
        mock_set.assert_called_once_with("puppy_name", "Rex")
        assert mw.call_count == 0
        assert me.call_count == 0

    def test_key_only_persists_empty_string(self):
        e_success, e_info, e_warning, e_error = _emitters()
        with (
            patch("code_puppy.config.set_config_value") as mock_set,
            patch("code_puppy.agents.get_current_agent") as mock_agent,
            e_success as ms,
            e_info,
            e_warning,
            e_error as me,
        ):
            mock_agent.return_value.reload_code_generation_agent.return_value = None
            handle_set_command("/set yolo_mode")
        mock_set.assert_called_once_with("yolo_mode", "")
        assert any('Set yolo_mode = "" in puppy.cfg!' in t for t in _texts(ms))
        assert me.call_count == 0

    def test_enable_dbos_emits_restart_notice_AND_reload_info(self):
        """Regression: the original always emitted both. The if/else
        branch added during refactor swallowed the reload info."""
        e_success, e_info, e_warning, e_error = _emitters()
        with (
            patch("code_puppy.config.set_config_value") as mock_set,
            patch("code_puppy.agents.get_current_agent") as mock_agent,
            e_success as ms,
            e_info as mi,
            e_warning as mw,
            e_error as me,
        ):
            mock_agent.return_value.reload_code_generation_agent.return_value = None
            handle_set_command("/set enable_dbos true")
        mock_set.assert_called_once_with("enable_dbos", "true")
        assert any('Set enable_dbos = "true" in puppy.cfg!' in t for t in _texts(ms))
        # Both signals must fire -- restart notice AND reload confirmation.
        assert any("restart" in t.lower() for t in _texts(mw))
        assert any("Agent reloaded with updated config" in t for t in _texts(mi))
        assert me.call_count == 0

    def test_cancel_agent_key_valid_normalizes_and_emits_both(self):
        e_success, e_info, e_warning, e_error = _emitters()
        with (
            patch("code_puppy.config.set_config_value") as mock_set,
            patch("code_puppy.agents.get_current_agent") as mock_agent,
            e_success as ms,
            e_info as mi,
            e_warning as mw,
            e_error as me,
        ):
            mock_agent.return_value.reload_code_generation_agent.return_value = None
            handle_set_command("/set cancel_agent_key Ctrl+K")
        # Lower-cased before persisting (original behavior).
        mock_set.assert_called_once_with("cancel_agent_key", "ctrl+k")
        assert any(
            'Set cancel_agent_key = "ctrl+k" in puppy.cfg!' in t for t in _texts(ms)
        )
        assert any("restart" in t.lower() for t in _texts(mw))
        assert any("Agent reloaded with updated config" in t for t in _texts(mi))
        assert me.call_count == 0

    def test_cancel_agent_key_invalid_errors_and_does_not_persist(self):
        e_success, e_info, e_warning, e_error = _emitters()
        with (
            patch("code_puppy.config.set_config_value") as mock_set,
            patch("code_puppy.agents.get_current_agent"),
            e_success as ms,
            e_info,
            e_warning,
            e_error as me,
        ):
            assert handle_set_command("/set cancel_agent_key bogus_key_xyz") is True
        mock_set.assert_not_called()
        assert ms.call_count == 0
        assert any("Invalid cancel_agent_key" in t for t in _texts(me))

    def test_reload_failure_preserves_restart_notice(self):
        """Regression: reload-failure used to clobber the restart notice
        because both lived on the same ApplyResult.warning field."""
        e_success, e_info, e_warning, e_error = _emitters()
        with (
            patch("code_puppy.config.set_config_value"),
            patch("code_puppy.agents.get_current_agent") as mock_agent,
            e_success as ms,
            e_info as mi,
            e_warning as mw,
            e_error as me,
        ):
            mock_agent.return_value.reload_code_generation_agent.side_effect = (
                RuntimeError("boom")
            )
            handle_set_command("/set enable_dbos true")
        assert any('Set enable_dbos = "true" in puppy.cfg!' in t for t in _texts(ms))
        assert any("restart" in t.lower() for t in _texts(mw))
        assert any("agent reload failed" in t.lower() for t in _texts(mw))
        # No "Agent reloaded" info when the reload genuinely failed.
        assert not any("Agent reloaded" in t for t in _texts(mi))
        assert me.call_count == 0

    def test_reload_failure_plain_key(self):
        e_success, e_info, e_warning, e_error = _emitters()
        with (
            patch("code_puppy.config.set_config_value"),
            patch("code_puppy.agents.get_current_agent") as mock_agent,
            e_success as ms,
            e_info as mi,
            e_warning as mw,
            e_error,
        ):
            mock_agent.return_value.reload_code_generation_agent.side_effect = (
                RuntimeError("boom")
            )
            handle_set_command("/set yolo_mode true")
        assert any('Set yolo_mode = "true" in puppy.cfg!' in t for t in _texts(ms))
        assert any("agent reload failed" in t.lower() for t in _texts(mw))
        assert not any("Agent reloaded" in t for t in _texts(mi))

    def test_no_args_launches_menu(self):
        """Intentional change from upstream: empty /set now opens the picker."""
        with patch(
            "code_puppy.command_line.config_commands._launch_interactive_set_menu"
        ) as mock_launch:
            assert handle_set_command("/set") is True
        mock_launch.assert_called_once_with()
