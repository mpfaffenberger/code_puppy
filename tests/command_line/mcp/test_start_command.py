"""Tests for MCP start command."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def start_cmd():
    with patch("code_puppy.command_line.mcp.base.get_mcp_manager") as mock_mgr:
        mock_mgr.return_value = MagicMock()
        from code_puppy.command_line.mcp.start_command import StartCommand

        return StartCommand()


class TestStartCommand:
    def test_no_args_shows_usage(self, start_cmd):
        with patch("code_puppy.command_line.mcp.start_command.emit_info") as mock_emit:
            start_cmd.execute([], group_id="g1")
            assert mock_emit.called

    def test_generates_group_id(self, start_cmd):
        with patch("code_puppy.command_line.mcp.start_command.emit_info"):
            start_cmd.execute([])

    def test_server_not_found(self, start_cmd):
        with (
            patch(
                "code_puppy.command_line.mcp.start_command.find_server_id_by_name",
                return_value=None,
            ),
            patch("code_puppy.command_line.mcp.start_command.suggest_similar_servers"),
            patch("code_puppy.command_line.mcp.start_command.emit_error") as mock_err,
        ):
            start_cmd.execute(["missing"], group_id="g1")
            assert "not found" in str(mock_err.call_args)

    def test_start_stdio_success(self, start_cmd):
        mock_server_config = MagicMock()
        mock_server_config.type = "stdio"
        start_cmd.manager.get_server_by_name.return_value = mock_server_config

        with (
            patch(
                "code_puppy.command_line.mcp.start_command.find_server_id_by_name",
                return_value="id1",
            ),
            patch("code_puppy.command_line.mcp.start_command.emit_info"),
            patch(
                "code_puppy.command_line.mcp.start_command.emit_success"
            ) as mock_succ,
            patch("code_puppy.command_line.mcp.start_command.get_current_agent"),
        ):
            start_cmd.manager.start_server_sync.return_value = True
            start_cmd.execute(["myserver"], group_id="g1")
            assert any("Starting" in str(c) for c in mock_succ.call_args_list)

    def test_start_sse_success(self, start_cmd):
        mock_server_config = MagicMock()
        mock_server_config.type = "sse"
        start_cmd.manager.get_server_by_name.return_value = mock_server_config

        with (
            patch(
                "code_puppy.command_line.mcp.start_command.find_server_id_by_name",
                return_value="id1",
            ),
            patch("code_puppy.command_line.mcp.start_command.emit_info"),
            patch(
                "code_puppy.command_line.mcp.start_command.emit_success"
            ) as mock_succ,
            patch("code_puppy.command_line.mcp.start_command.get_current_agent"),
        ):
            start_cmd.manager.start_server_sync.return_value = True
            start_cmd.execute(["myserver"], group_id="g1")
            assert any("Enabled" in str(c) for c in mock_succ.call_args_list)

    def test_start_failure(self, start_cmd):
        with (
            patch(
                "code_puppy.command_line.mcp.start_command.find_server_id_by_name",
                return_value="id1",
            ),
            patch("code_puppy.command_line.mcp.start_command.emit_error") as mock_err,
        ):
            start_cmd.manager.start_server_sync.return_value = False
            start_cmd.execute(["myserver"], group_id="g1")
            assert any("Failed" in str(c) for c in mock_err.call_args_list)

    def test_agent_reload_fails(self, start_cmd):
        with (
            patch(
                "code_puppy.command_line.mcp.start_command.find_server_id_by_name",
                return_value="id1",
            ),
            patch("code_puppy.command_line.mcp.start_command.emit_info"),
            patch("code_puppy.command_line.mcp.start_command.emit_success"),
            patch(
                "code_puppy.command_line.mcp.start_command.get_current_agent",
                side_effect=Exception("no agent"),
            ),
        ):
            start_cmd.manager.start_server_sync.return_value = True
            start_cmd.execute(["myserver"], group_id="g1")

    def test_outer_exception(self, start_cmd):
        with (
            patch(
                "code_puppy.command_line.mcp.start_command.find_server_id_by_name",
                side_effect=Exception("boom"),
            ),
            patch("code_puppy.command_line.mcp.start_command.emit_error") as mock_err,
        ):
            start_cmd.execute(["myserver"], group_id="g1")
            mock_err.assert_called_once()

    def test_get_server_by_name_not_available(self, start_cmd):
        """Test when manager doesn't have get_server_by_name."""
        del start_cmd.manager.get_server_by_name  # remove the attr

        with (
            patch(
                "code_puppy.command_line.mcp.start_command.find_server_id_by_name",
                return_value="id1",
            ),
            patch("code_puppy.command_line.mcp.start_command.emit_info"),
            patch("code_puppy.command_line.mcp.start_command.emit_success"),
            patch("code_puppy.command_line.mcp.start_command.get_current_agent"),
        ):
            start_cmd.manager.start_server_sync.return_value = True
            start_cmd.execute(["myserver"], group_id="g1")

    def test_get_server_by_name_raises(self, start_cmd):
        start_cmd.manager.get_server_by_name.side_effect = Exception("err")

        with (
            patch(
                "code_puppy.command_line.mcp.start_command.find_server_id_by_name",
                return_value="id1",
            ),
            patch("code_puppy.command_line.mcp.start_command.emit_info"),
            patch("code_puppy.command_line.mcp.start_command.emit_success"),
            patch("code_puppy.command_line.mcp.start_command.get_current_agent"),
        ):
            start_cmd.manager.start_server_sync.return_value = True
            start_cmd.execute(["myserver"], group_id="g1")

    # ---- Auto-bind behaviour (CPUP-ne1) -------------------------------

    def _make_agent(self, name="code-puppy"):
        agent = MagicMock()
        agent.name = name
        return agent

    def test_auto_binds_when_unbound(self, start_cmd):
        """`/mcp start` on an unbound server creates the binding."""
        agent = self._make_agent()
        with (
            patch(
                "code_puppy.command_line.mcp.start_command.find_server_id_by_name",
                return_value="id1",
            ),
            patch("code_puppy.command_line.mcp.start_command.emit_info"),
            patch("code_puppy.command_line.mcp.start_command.emit_success"),
            patch(
                "code_puppy.command_line.mcp.start_command.get_current_agent",
                return_value=agent,
            ),
            patch(
                "code_puppy.mcp_.agent_bindings.is_bound", return_value=False
            ) as mock_is_bound,
            patch("code_puppy.mcp_.agent_bindings.set_binding") as mock_set_binding,
        ):
            start_cmd.manager.start_server_sync.return_value = True
            start_cmd.execute(["myserver"], group_id="g1")

            mock_is_bound.assert_called_once_with("code-puppy", "myserver")
            mock_set_binding.assert_called_once_with(
                "code-puppy", "myserver", auto_start=True
            )
            agent.reload_code_generation_agent.assert_called_once()

    def test_no_rebind_when_already_bound(self, start_cmd):
        """Already-bound server triggers no set_binding call (idempotent)."""
        agent = self._make_agent()
        with (
            patch(
                "code_puppy.command_line.mcp.start_command.find_server_id_by_name",
                return_value="id1",
            ),
            patch("code_puppy.command_line.mcp.start_command.emit_info"),
            patch("code_puppy.command_line.mcp.start_command.emit_success"),
            patch(
                "code_puppy.command_line.mcp.start_command.get_current_agent",
                return_value=agent,
            ),
            patch("code_puppy.mcp_.agent_bindings.is_bound", return_value=True),
            patch("code_puppy.mcp_.agent_bindings.set_binding") as mock_set_binding,
        ):
            start_cmd.manager.start_server_sync.return_value = True
            start_cmd.execute(["myserver"], group_id="g1")

            mock_set_binding.assert_not_called()
            agent.reload_code_generation_agent.assert_called_once()

    def test_auto_bind_failure_does_not_break_start(self, start_cmd):
        """A binding-layer exception is swallowed; reload still happens."""
        agent = self._make_agent()
        with (
            patch(
                "code_puppy.command_line.mcp.start_command.find_server_id_by_name",
                return_value="id1",
            ),
            patch("code_puppy.command_line.mcp.start_command.emit_info"),
            patch("code_puppy.command_line.mcp.start_command.emit_success"),
            patch(
                "code_puppy.command_line.mcp.start_command.get_current_agent",
                return_value=agent,
            ),
            patch(
                "code_puppy.mcp_.agent_bindings.is_bound",
                side_effect=RuntimeError("bindings file corrupted"),
            ),
        ):
            start_cmd.manager.start_server_sync.return_value = True
            start_cmd.execute(["myserver"], group_id="g1")

            # Reload still happened even though bind blew up.
            agent.reload_code_generation_agent.assert_called_once()

    def test_bind_runs_before_reload(self, start_cmd):
        """set_binding must be called BEFORE reload, or reload sees stale state."""
        agent = self._make_agent()
        call_order: list[str] = []
        agent.reload_code_generation_agent.side_effect = lambda: call_order.append(
            "reload"
        )

        def fake_set(*_a, **_kw):
            call_order.append("bind")

        with (
            patch(
                "code_puppy.command_line.mcp.start_command.find_server_id_by_name",
                return_value="id1",
            ),
            patch("code_puppy.command_line.mcp.start_command.emit_info"),
            patch("code_puppy.command_line.mcp.start_command.emit_success"),
            patch(
                "code_puppy.command_line.mcp.start_command.get_current_agent",
                return_value=agent,
            ),
            patch("code_puppy.mcp_.agent_bindings.is_bound", return_value=False),
            patch("code_puppy.mcp_.agent_bindings.set_binding", side_effect=fake_set),
        ):
            start_cmd.manager.start_server_sync.return_value = True
            start_cmd.execute(["myserver"], group_id="g1")

            assert call_order == ["bind", "reload"], (
                "binding must be persisted before agent reload so the rebuilt "
                "toolset actually picks up the new server"
            )
