"""One restart workflow: stop, replace, start, then rebind the requesting agent."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic_ai.toolsets import FunctionToolset

from code_puppy.command_line.mcp.restart_command import RestartCommand
from code_puppy.mcp_ import async_lifecycle
from code_puppy.mcp_.manager import MCPManager
from code_puppy.mcp_.managed_server import ServerConfig


class Connector(FunctionToolset):
    def __init__(self, events, release=None, fail_start=False):
        super().__init__()
        self.events, self.release, self.fail_start = events, release, fail_start
        self.is_running = False

    async def __aenter__(self):
        if self.fail_start:
            raise RuntimeError("entry failed")
        self.events.append("enter")
        self.is_running = True
        return self

    async def __aexit__(self, *args):
        if self.release:
            await self.release.wait()
        self.events.append("exit")
        self.is_running = False


@pytest.fixture
def setup_restart(monkeypatch):
    events = []
    life = async_lifecycle.AsyncServerLifecycleManager()
    monkeypatch.setattr("code_puppy.mcp_.manager.get_lifecycle_manager", lambda: life)
    manager = object.__new__(MCPManager)
    manager.status_tracker = Mock()
    manager.registry = Mock()
    config = ServerConfig(id="a", name="a", type="stdio", config={})
    manager.registry.get.return_value = config
    made = []

    def construct(cfg):
        events.append("construct")
        leaf = Connector(events)
        wrapper = leaf.prefixed("test")
        available = [True]
        item = SimpleNamespace(
            config=cfg,
            leaf=leaf,
            enable=lambda: available.__setitem__(0, True),
            disable=lambda: available.__setitem__(0, False),
            is_enabled=lambda: available[0],
            has_running_toolset=lambda: leaf.is_running,
            get_pydantic_server=lambda: wrapper,
            get_status=lambda: {"state": "stopped"},
        )
        made.append(item)
        return item

    monkeypatch.setattr("code_puppy.mcp_.manager.ManagedMCPServer", construct)
    manager._managed_servers = {"a": construct(config)}
    agent = Mock()
    agent.reload_code_generation_agent.side_effect = lambda: events.append("rebind")
    monkeypatch.setattr("code_puppy.agents.get_current_agent", lambda: agent)
    monkeypatch.setattr(
        "code_puppy.command_line.mcp.base.get_mcp_manager", lambda: manager
    )
    monkeypatch.setattr(
        "code_puppy.command_line.mcp.restart_command.find_server_id_by_name",
        lambda *a: "a",
    )
    output = Mock()
    monkeypatch.setattr("code_puppy.command_line.mcp.restart_command.emit_info", output)
    return manager, life, made, events, agent, output


async def test_real_command_waits_then_rebinds_and_reports(setup_restart):
    manager, life, made, events, agent, output = setup_restart
    await life.start_server("a", made[0].get_pydantic_server())
    events.clear()
    command = RestartCommand()
    try:
        command.execute(["a"], "group")
        assert events == []
        assert "Restarted server" not in str(output.call_args_list)
        command.execute(["a"], "group")  # duplicate request must not race
        await manager._pending_restart_tasks["a"]
        assert events == ["exit", "construct", "enter", "rebind"]
        assert "Restarted server" in str(output.call_args_list)
        assert len(made) == 2
    finally:
        await life.stop_all()


@pytest.mark.parametrize("failure", ["stop", "construct", "invalid", "start"])
async def test_failed_restart_invalidates_without_rebuilding(
    monkeypatch, setup_restart, failure
):
    manager, life, made, events, agent, output = setup_restart
    release = asyncio.Event()
    if failure == "stop":
        made[0].leaf.release = release
        monkeypatch.setattr(async_lifecycle, "SERVER_STOP_TIMEOUT", 0.02)
    await life.start_server("a", made[0].get_pydantic_server())
    old_task = life._servers["a"].task
    if failure == "construct":
        monkeypatch.setattr(
            "code_puppy.mcp_.manager.ManagedMCPServer",
            Mock(side_effect=ValueError("invalid config")),
        )
    if failure == "invalid":
        monkeypatch.setattr(
            "code_puppy.mcp_.manager.ManagedMCPServer",
            lambda cfg: SimpleNamespace(get_status=lambda: {"state": "error"}),
        )
    if failure == "start":
        monkeypatch.setattr(life, "start_server", AsyncMock(return_value=False))
    try:
        RestartCommand().execute(["a"], "group")
        await manager._pending_restart_tasks["a"]
        assert "Restarted server" not in str(output.call_args_list)
        assert "Restart failed" in str(output.call_args_list)
        assert agent._code_generation_agent is None
        agent.reload_code_generation_agent.assert_not_called()
        if failure != "start":
            assert manager._managed_servers["a"] is made[0]
    finally:
        release.set()
        await asyncio.gather(old_task, return_exceptions=True)
        await life.stop_all()


async def test_rebind_failure_is_reported_as_partial_success(setup_restart):
    manager, life, made, _, agent, output = setup_restart
    await life.start_server("a", made[0].get_pydantic_server())
    agent.reload_code_generation_agent.side_effect = RuntimeError("model missing")
    try:
        RestartCommand().execute(["a"], "group")
        await manager._pending_restart_tasks["a"]
        assert life.is_running("a")
        assert "rebuilding the agent failed" in str(output.call_args_list)
        assert agent._code_generation_agent is None
    finally:
        await life.stop_all()


async def test_cancelled_restart_invalidates_without_replacing(
    monkeypatch, setup_restart
):
    manager, life, made, _, agent, _ = setup_restart
    release = asyncio.Event()
    made[0].leaf.release = release
    await life.start_server("a", made[0].get_pydantic_server())
    lifecycle_task = life._servers["a"].task
    try:
        RestartCommand().execute(["a"], "group")
        task = manager._pending_restart_tasks["a"]
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert manager._managed_servers["a"] is made[0]
        assert agent._code_generation_agent is None
        agent.reload_code_generation_agent.assert_not_called()
    finally:
        release.set()
        await asyncio.gather(lifecycle_task, return_exceptions=True)


async def test_direct_restart_callers_serialize(setup_restart):
    manager, life, made, events, _, _ = setup_restart
    await life.start_server("a", made[0].get_pydantic_server())
    events.clear()
    try:
        assert all(
            await asyncio.gather(
                manager.restart_server("a"), manager.restart_server("a")
            )
        )
        assert events == ["exit", "construct", "enter"] * 2
    finally:
        await life.stop_all()


async def test_pending_operation_refuses_restart(setup_restart):
    manager, life, made, events, _, _ = setup_restart
    pending = asyncio.create_task(asyncio.Event().wait())
    manager._pending_start_tasks = {"a": pending}
    events.clear()
    try:
        assert not await manager.restart_server("a")
        assert not events
    finally:
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
