"""Tests for ``_builder.load_mcp_servers`` and ``_autostart_bound_servers``.

These exercise the auto-start path that the main agent uses for its
bound MCP servers, and that sub-agents must also use (otherwise auto_start
bindings get silently ignored when invoked via the ``invoke_agent`` tool).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.agents import _builder
from code_puppy.mcp_.managed_server import ServerState


def _fake_config(server_id="srv-1"):
    return SimpleNamespace(id=server_id, name="srv-1")


@pytest.fixture
def mock_manager():
    manager = MagicMock()
    manager.get_server_by_name.return_value = _fake_config()
    manager.get_servers_for_agent.return_value = ["pyd-server-instance"]
    return manager


@pytest.fixture(autouse=True)
def _reset_warn_cache():
    """Clear the warn-once dedupe cache between tests so each test sees a
    fresh state. Without this, the second test that triggers a missing
    warning would silently no-op."""
    _builder._reset_missing_warning_cache()
    yield
    _builder._reset_missing_warning_cache()


class TestAutostartBoundServers:
    def test_starts_stopped_server_when_auto_start_true(self, mock_manager):
        mock_manager.get_server_status.return_value = {
            "state": ServerState.STOPPED.value
        }
        with patch(
            "code_puppy.mcp_.agent_bindings.get_bound_servers",
            return_value={"srv-1": {"auto_start": True}},
        ):
            _builder._autostart_bound_servers(mock_manager, "code-puppy")

        mock_manager.start_server_sync.assert_called_once_with("srv-1")

    def test_skips_when_already_running(self, mock_manager):
        mock_manager.get_server_status.return_value = {
            "state": ServerState.RUNNING.value
        }
        with patch(
            "code_puppy.mcp_.agent_bindings.get_bound_servers",
            return_value={"srv-1": {"auto_start": True}},
        ):
            _builder._autostart_bound_servers(mock_manager, "code-puppy")
        mock_manager.start_server_sync.assert_not_called()

    def test_skips_when_already_starting(self, mock_manager):
        mock_manager.get_server_status.return_value = {
            "state": ServerState.STARTING.value
        }
        with patch(
            "code_puppy.mcp_.agent_bindings.get_bound_servers",
            return_value={"srv-1": {"auto_start": True}},
        ):
            _builder._autostart_bound_servers(mock_manager, "code-puppy")
        mock_manager.start_server_sync.assert_not_called()

    def test_skips_when_auto_start_false(self, mock_manager):
        with patch(
            "code_puppy.mcp_.agent_bindings.get_bound_servers",
            return_value={"srv-1": {"auto_start": False}},
        ):
            _builder._autostart_bound_servers(mock_manager, "code-puppy")
        mock_manager.start_server_sync.assert_not_called()

    def test_no_bindings_is_noop(self, mock_manager):
        with patch("code_puppy.mcp_.agent_bindings.get_bound_servers", return_value={}):
            _builder._autostart_bound_servers(mock_manager, "code-puppy")
        mock_manager.start_server_sync.assert_not_called()

    def test_unknown_server_is_skipped(self, mock_manager):
        mock_manager.get_server_by_name.return_value = None
        with patch(
            "code_puppy.mcp_.agent_bindings.get_bound_servers",
            return_value={"phantom": {"auto_start": True}},
        ):
            _builder._autostart_bound_servers(mock_manager, "code-puppy")
        mock_manager.start_server_sync.assert_not_called()

    def test_start_failure_is_swallowed(self, mock_manager):
        mock_manager.get_server_status.return_value = {
            "state": ServerState.STOPPED.value
        }
        mock_manager.start_server_sync.side_effect = RuntimeError("boom")
        with patch(
            "code_puppy.mcp_.agent_bindings.get_bound_servers",
            return_value={"srv-1": {"auto_start": True}},
        ):
            # Should NOT raise — defensive logging only.
            _builder._autostart_bound_servers(mock_manager, "code-puppy")


class TestMissingServerWarning:
    """Declared-but-not-installed servers should warn (once) and skip."""

    def test_warns_when_declared_server_not_installed(self, mock_manager):
        mock_manager.get_server_by_name.return_value = None  # not installed
        with (
            patch(
                "code_puppy.mcp_.agent_bindings.get_bound_servers",
                return_value={"missing-srv": {"auto_start": True}},
            ),
            patch("code_puppy.agents._builder.emit_warning") as mock_warn,
        ):
            _builder._autostart_bound_servers(mock_manager, "code-detective")
        assert mock_warn.call_count == 1
        msg = mock_warn.call_args[0][0]
        assert "code-detective" in msg
        assert "missing-srv" in msg
        assert "/mcp install" in msg
        # And we did NOT try to start it.
        mock_manager.start_server_sync.assert_not_called()

    def test_warning_is_deduped_across_calls(self, mock_manager):
        mock_manager.get_server_by_name.return_value = None
        with (
            patch(
                "code_puppy.mcp_.agent_bindings.get_bound_servers",
                return_value={"missing-srv": {"auto_start": True}},
            ),
            patch("code_puppy.agents._builder.emit_warning") as mock_warn,
        ):
            _builder._autostart_bound_servers(mock_manager, "code-detective")
            _builder._autostart_bound_servers(mock_manager, "code-detective")
            _builder._autostart_bound_servers(mock_manager, "code-detective")
        # Same (agent, server) pair across multiple invocations — warn once.
        assert mock_warn.call_count == 1

    def test_different_agents_warn_independently(self, mock_manager):
        mock_manager.get_server_by_name.return_value = None
        with (
            patch(
                "code_puppy.mcp_.agent_bindings.get_bound_servers",
                return_value={"missing-srv": {"auto_start": True}},
            ),
            patch("code_puppy.agents._builder.emit_warning") as mock_warn,
        ):
            _builder._autostart_bound_servers(mock_manager, "agent-a")
            _builder._autostart_bound_servers(mock_manager, "agent-b")
        # Each agent gets its own warning even for the same missing server.
        assert mock_warn.call_count == 2

    def test_no_warning_when_auto_start_is_false(self, mock_manager):
        """Don't nag about missing servers the user explicitly opted out of."""
        mock_manager.get_server_by_name.return_value = None
        with (
            patch(
                "code_puppy.mcp_.agent_bindings.get_bound_servers",
                return_value={"missing-srv": {"auto_start": False}},
            ),
            patch("code_puppy.agents._builder.emit_warning") as mock_warn,
        ):
            _builder._autostart_bound_servers(mock_manager, "code-detective")
        mock_warn.assert_not_called()

    async def test_async_path_also_warns(self, mock_manager):
        from unittest.mock import AsyncMock

        mock_manager.start_server = AsyncMock(return_value=True)
        mock_manager.get_server_by_name.return_value = None
        with (
            patch(
                "code_puppy.mcp_.agent_bindings.get_bound_servers",
                return_value={"missing-srv": {"auto_start": True}},
            ),
            patch("code_puppy.agents._builder.emit_warning") as mock_warn,
        ):
            await _builder.autostart_bound_servers_async(mock_manager, "code-detective")
        assert mock_warn.call_count == 1
        mock_manager.start_server.assert_not_awaited()


class TestAutostartBoundServersAsync:
    """Tests for the async variant used by sub-agent invocation."""

    async def test_awaits_start_for_stopped_server(self, mock_manager):
        from unittest.mock import AsyncMock

        mock_manager.start_server = AsyncMock(return_value=True)
        mock_manager.get_server_status.return_value = {
            "state": ServerState.STOPPED.value
        }
        with patch(
            "code_puppy.mcp_.agent_bindings.get_bound_servers",
            return_value={"srv-1": {"auto_start": True}},
        ):
            await _builder.autostart_bound_servers_async(mock_manager, "code-puppy")
        mock_manager.start_server.assert_awaited_once_with("srv-1")

    async def test_skips_already_running(self, mock_manager):
        from unittest.mock import AsyncMock

        mock_manager.start_server = AsyncMock(return_value=True)
        mock_manager.get_server_status.return_value = {
            "state": ServerState.RUNNING.value
        }
        with patch(
            "code_puppy.mcp_.agent_bindings.get_bound_servers",
            return_value={"srv-1": {"auto_start": True}},
        ):
            await _builder.autostart_bound_servers_async(mock_manager, "code-puppy")
        mock_manager.start_server.assert_not_awaited()

    async def test_skips_when_auto_start_false(self, mock_manager):
        from unittest.mock import AsyncMock

        mock_manager.start_server = AsyncMock(return_value=True)
        with patch(
            "code_puppy.mcp_.agent_bindings.get_bound_servers",
            return_value={"srv-1": {"auto_start": False}},
        ):
            await _builder.autostart_bound_servers_async(mock_manager, "code-puppy")
        mock_manager.start_server.assert_not_awaited()

    async def test_start_failure_is_swallowed(self, mock_manager):
        from unittest.mock import AsyncMock

        mock_manager.start_server = AsyncMock(side_effect=RuntimeError("nope"))
        mock_manager.get_server_status.return_value = {
            "state": ServerState.STOPPED.value
        }
        with patch(
            "code_puppy.mcp_.agent_bindings.get_bound_servers",
            return_value={"srv-1": {"auto_start": True}},
        ):
            # Should NOT raise.
            await _builder.autostart_bound_servers_async(mock_manager, "code-puppy")

    async def test_no_bindings_is_noop(self, mock_manager):
        from unittest.mock import AsyncMock

        mock_manager.start_server = AsyncMock(return_value=True)
        with patch("code_puppy.mcp_.agent_bindings.get_bound_servers", return_value={}):
            await _builder.autostart_bound_servers_async(mock_manager, "code-puppy")
        mock_manager.start_server.assert_not_awaited()


class TestLoadMcpServersWiring:
    """Confirm that ``load_mcp_servers`` triggers autostart when given an agent name."""

    def test_autostart_called_when_agent_name_given(self, mock_manager):
        with (
            patch(
                "code_puppy.agents._builder.get_mcp_manager", return_value=mock_manager
            ),
            patch(
                "code_puppy.agents._builder._autostart_bound_servers"
            ) as mock_autostart,
            patch("code_puppy.agents._builder.get_value", return_value=None),
        ):
            _builder.load_mcp_servers(agent_name="code-puppy")
        mock_autostart.assert_called_once_with(mock_manager, "code-puppy")

    def test_autostart_skipped_when_agent_name_none(self, mock_manager):
        with (
            patch(
                "code_puppy.agents._builder.get_mcp_manager", return_value=mock_manager
            ),
            patch(
                "code_puppy.agents._builder._autostart_bound_servers"
            ) as mock_autostart,
            patch("code_puppy.agents._builder.get_value", return_value=None),
        ):
            _builder.load_mcp_servers(agent_name=None)
        mock_autostart.assert_not_called()

    def test_returns_empty_when_disabled(self, mock_manager):
        with (
            patch(
                "code_puppy.agents._builder.get_mcp_manager", return_value=mock_manager
            ),
            patch(
                "code_puppy.agents._builder._autostart_bound_servers"
            ) as mock_autostart,
            patch("code_puppy.agents._builder.get_value", return_value="true"),
        ):
            result = _builder.load_mcp_servers(agent_name="code-puppy")
        assert result == []
        mock_autostart.assert_not_called()


class TestSubagentInvocationUsesAsyncAutostart:
    """Lock in: ``invoke_agent`` must use the *async* autostart helper.

    ``temp_agent.run(...)`` is wrapped in ``asyncio.create_task``, so
    pydantic-ai opens MCP toolset cancel scopes in that task. The fire-
    and-forget ``_autostart_bound_servers`` (sync) returns before the
    lifecycle task has entered the MCP singleton's context, which races
    pydantic-ai's re-entry and produces a cross-task cancel-scope crash.
    ``autostart_bound_servers_async`` awaits readiness so re-entry hits
    the refcount no-op path.

    These structural assertions catch the regression at import-time.
    """

    @staticmethod
    def _code_without_comments() -> str:
        import re
        from pathlib import Path

        source = Path("code_puppy/tools/agent_tools.py").read_text(encoding="utf-8")
        return "\n".join(re.sub(r"#.*$", "", line) for line in source.splitlines())

    def test_agent_tools_calls_async_autostart(self):
        code = self._code_without_comments()
        assert "autostart_bound_servers_async" in code, (
            "invoke_agent must call autostart_bound_servers_async (awaits "
            "readiness) so bound MCP servers are warm and pydantic-ai's "
            "toolset entry is a refcount no-op."
        )
        assert "await autostart_bound_servers_async" in code, (
            "autostart_bound_servers_async must be awaited — fire-and-forget "
            "defeats the entire reason it exists."
        )

    def test_agent_tools_uses_manager_directly_for_filtering(self):
        code = self._code_without_comments()
        assert "manager.get_servers_for_agent" in code, (
            "invoke_agent should fetch bound servers via "
            "manager.get_servers_for_agent for filtering."
        )

    def test_agent_tools_does_not_call_sync_autostart(self):
        code = self._code_without_comments()
        # ``load_mcp_servers`` invokes the sync autostart — forbidden here.
        assert "load_mcp_servers" not in code, (
            "invoke_agent must NOT call load_mcp_servers — it triggers the "
            "fire-and-forget sync autostart which races pydantic-ai's "
            "toolset entry inside asyncio.create_task(temp_agent.run(...))."
        )
        assert "_autostart_bound_servers" not in code, (
            "invoke_agent must NOT call the sync _autostart_bound_servers — "
            "use the async variant."
        )


class TestPreMcpAutostartHook:
    """The ``pre_mcp_autostart`` callback fires once per autostart batch,
    before any ``manager.start_server`` call, with the agent name and the
    list of server names that are about to start. Plugins use this to
    refresh tokens / mint creds without monkey-patching ``start_server``.
    """

    def test_sync_fires_hook_with_agent_and_server_names(self, mock_manager):
        mock_manager.get_server_status.return_value = {
            "state": ServerState.STOPPED.value
        }
        with (
            patch(
                "code_puppy.mcp_.agent_bindings.get_bound_servers",
                return_value={"srv-1": {"auto_start": True}},
            ),
            patch("code_puppy.agents._builder.on_pre_mcp_autostart_sync") as mock_hook,
        ):
            _builder._autostart_bound_servers(mock_manager, "code-puppy")
        mock_hook.assert_called_once_with("code-puppy", ["srv-1"])

    @pytest.mark.asyncio
    async def test_async_fires_hook_with_agent_and_server_names(self, mock_manager):
        mock_manager.get_server_status.return_value = {
            "state": ServerState.STOPPED.value
        }

        async def _ok(_id):
            return None

        mock_manager.start_server.side_effect = _ok

        with (
            patch(
                "code_puppy.mcp_.agent_bindings.get_bound_servers",
                return_value={"srv-1": {"auto_start": True}},
            ),
            patch(
                "code_puppy.agents._builder.on_pre_mcp_autostart",
            ) as mock_hook,
        ):

            async def _async_ok(*_a, **_kw):
                return []

            mock_hook.side_effect = _async_ok
            await _builder.autostart_bound_servers_async(mock_manager, "code-puppy")
        mock_hook.assert_called_once_with("code-puppy", ["srv-1"])

    def test_hook_fires_before_start_server(self, mock_manager):
        """Order matters: hook must fire BEFORE any start_server call so
        plugins can refresh credentials in time."""
        mock_manager.get_server_status.return_value = {
            "state": ServerState.STOPPED.value
        }
        order: list[str] = []

        def _hook(_agent, _names):
            order.append("hook")

        mock_manager.start_server_sync.side_effect = lambda _id: order.append("start")

        from code_puppy.callbacks import (
            register_callback,
            unregister_callback,
        )

        register_callback("pre_mcp_autostart", _hook)
        try:
            with patch(
                "code_puppy.mcp_.agent_bindings.get_bound_servers",
                return_value={"srv-1": {"auto_start": True}},
            ):
                _builder._autostart_bound_servers(mock_manager, "code-puppy")
        finally:
            unregister_callback("pre_mcp_autostart", _hook)

        assert order == ["hook", "start"]

    def test_hook_not_fired_when_no_targets(self, mock_manager):
        """If nothing's going to autostart, don't bother plugins."""
        with (
            patch(
                "code_puppy.mcp_.agent_bindings.get_bound_servers",
                return_value={"srv-1": {"auto_start": False}},
            ),
            patch("code_puppy.agents._builder.on_pre_mcp_autostart_sync") as mock_hook,
        ):
            _builder._autostart_bound_servers(mock_manager, "code-puppy")
        mock_hook.assert_not_called()

    def test_hook_exception_does_not_abort_autostart(self, mock_manager):
        """A misbehaving plugin must not block servers from starting."""
        mock_manager.get_server_status.return_value = {
            "state": ServerState.STOPPED.value
        }

        def _bad_hook(_agent, _names):
            raise RuntimeError("plugin broke")

        from code_puppy.callbacks import (
            register_callback,
            unregister_callback,
        )

        register_callback("pre_mcp_autostart", _bad_hook)
        try:
            with patch(
                "code_puppy.mcp_.agent_bindings.get_bound_servers",
                return_value={"srv-1": {"auto_start": True}},
            ):
                _builder._autostart_bound_servers(mock_manager, "code-puppy")
        finally:
            unregister_callback("pre_mcp_autostart", _bad_hook)

        # Server still starts even though hook raised.
        mock_manager.start_server_sync.assert_called_once_with("srv-1")

    def test_hook_receives_only_autostart_servers(self, mock_manager):
        """Servers with ``auto_start=False`` must not appear in the hook's
        server_names list — plugins decide work based on this."""
        mock_manager.get_server_status.return_value = {
            "state": ServerState.STOPPED.value
        }
        with (
            patch(
                "code_puppy.mcp_.agent_bindings.get_bound_servers",
                return_value={
                    "srv-yes": {"auto_start": True},
                    "srv-no": {"auto_start": False},
                },
            ),
            patch("code_puppy.agents._builder.on_pre_mcp_autostart_sync") as mock_hook,
        ):
            _builder._autostart_bound_servers(mock_manager, "code-puppy")
        mock_hook.assert_called_once()
        agent_arg, names_arg = mock_hook.call_args.args
        assert agent_arg == "code-puppy"
        assert names_arg == ["srv-yes"]


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
