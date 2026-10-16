"""Regression coverage for manager readiness and overlapping user requests."""

import asyncio
from unittest.mock import AsyncMock, Mock, call

import pytest

from code_puppy.mcp_.managed_server import ServerState
from code_puppy.mcp_.manager import MCPManager


@pytest.fixture
def lifecycle_setup(monkeypatch):
    manager = MCPManager.__new__(MCPManager)
    server = Mock()
    manager._managed_servers = {"server": server}
    manager.status_tracker = Mock()
    lifecycle = AsyncMock()
    lifecycle.start_server.return_value = True
    lifecycle.stop_server.return_value = True
    monkeypatch.setattr(
        "code_puppy.mcp_.manager.get_lifecycle_manager", lambda: lifecycle
    )
    return manager, server, lifecycle


@pytest.mark.parametrize("failure", [False, RuntimeError("broken")])
async def test_start_failure_never_claims_running(lifecycle_setup, failure):
    manager, server, lifecycle = lifecycle_setup
    if isinstance(failure, Exception):
        lifecycle.start_server.side_effect = failure
    else:
        lifecycle.start_server.return_value = failure
    assert await manager.start_server("server") is False
    server.enable.assert_not_called()
    server.disable.assert_called_once()
    manager.status_tracker.record_start_time.assert_not_called()
    assert manager.status_tracker.set_status.call_args_list == [
        call("server", ServerState.STARTING),
        call("server", ServerState.ERROR),
    ]


async def test_startup_is_deduplicated_and_running_waits_for_readiness(lifecycle_setup):
    manager, server, lifecycle = lifecycle_setup
    entered, release = asyncio.Event(), asyncio.Event()

    async def start(*args):
        entered.set()
        await release.wait()
        return True

    lifecycle.start_server.side_effect = start
    assert manager.start_server_sync("server")
    original = manager._pending_start_tasks["server"]
    assert manager.start_server_sync("server")
    assert manager._pending_start_tasks["server"] is original
    waiter = asyncio.create_task(manager.start_server("server"))
    await entered.wait()
    await manager.wait_for_pending_starts(timeout=0)
    assert not original.cancelled()
    manager.status_tracker.set_status.assert_called_once_with(
        "server", ServerState.STARTING
    )
    manager.status_tracker.record_start_time.assert_not_called()
    release.set()
    assert await waiter
    lifecycle.start_server.assert_awaited_once()
    server.enable.assert_called_once()
    manager.status_tracker.set_status.assert_called_with("server", ServerState.RUNNING)


@pytest.mark.parametrize("operation", ["start", "stop"])
async def test_old_task_cleanup_cannot_remove_replacement(lifecycle_setup, operation):
    manager, _, _ = lifecycle_setup
    first = manager._track_lifecycle_task(operation, "server", asyncio.sleep(0))
    release = asyncio.Event()
    replacement = manager._track_lifecycle_task(operation, "server", release.wait())
    await first
    await asyncio.sleep(0)
    assert manager._lifecycle_tasks(operation)["server"] is replacement
    release.set()
    await replacement


async def test_stop_before_start_task_runs_never_enables_server(lifecycle_setup):
    manager, server, lifecycle = lifecycle_setup
    assert manager.start_server_sync("server")
    starting = manager._pending_start_tasks["server"]
    assert manager.stop_server_sync("server")
    stopping = manager._pending_stop_tasks["server"]
    assert manager.stop_server_sync("server")
    assert manager._pending_stop_tasks["server"] is stopping
    assert not manager.start_server_sync("server")
    assert await stopping
    assert starting.cancelled()
    server.enable.assert_not_called()
    lifecycle.start_server.assert_not_awaited()
    lifecycle.stop_server.assert_awaited_once()
    manager.status_tracker.set_status.assert_called_with("server", ServerState.STOPPED)


@pytest.mark.parametrize("suppress_cancellation", [False, True])
@pytest.mark.parametrize("stop_from", ["loop", "thread"])
async def test_stop_cancels_and_drains_inflight_start(
    lifecycle_setup, suppress_cancellation, stop_from
):
    manager, server, lifecycle = lifecycle_setup
    entered, cancelled = asyncio.Event(), asyncio.Event()

    async def start(*args):
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            if not suppress_cancellation:
                raise
            return True

    async def stop(*args):
        assert cancelled.is_set()
        return True

    lifecycle.start_server.side_effect = start
    lifecycle.stop_server.side_effect = stop
    waiter = asyncio.create_task(manager.start_server("server"))
    await entered.wait()
    if stop_from == "thread":
        assert await asyncio.to_thread(manager.stop_server_sync, "server")
    else:
        assert await manager.stop_server("server")
    assert await asyncio.wait_for(waiter, timeout=1) is False
    await manager.wait_for_pending_starts()
    for stopping in list(manager._pending_stop_tasks.values()):
        await stopping
    assert cancelled.is_set()
    assert manager.is_autostart_suppressed("server")
    lifecycle.stop_server.assert_awaited_once()
    server.enable.assert_not_called()
    manager.status_tracker.set_status.assert_called_with("server", ServerState.STOPPED)
    manager.status_tracker.record_start_time.assert_not_called()


async def test_worker_stop_survives_loop_closing_during_dispatch(
    lifecycle_setup, monkeypatch, caplog
):
    manager, server, lifecycle = lifecycle_setup
    loop = asyncio.new_event_loop()
    starting = Mock()
    starting.get_loop.return_value = loop
    manager._pending_start_tasks = {"server": starting}
    dispatch = loop.call_soon_threadsafe

    def close_before_dispatch(*args):
        loop.close()
        return dispatch(*args)

    monkeypatch.setattr(loop, "call_soon_threadsafe", close_before_dispatch)
    try:
        assert await asyncio.to_thread(manager.stop_server_sync, "server")
        assert loop.is_closed()
        server.disable.assert_called_once()
        assert manager.is_autostart_suppressed("server")
        manager.status_tracker.set_status.assert_called_once_with(
            "server", ServerState.STOPPED
        )
        lifecycle.stop_server.assert_not_awaited()
        assert "MCP stop cleanup dispatch failed for server" in caplog.text
        assert "Event loop is closed" in caplog.text
    finally:
        if not loop.is_closed():
            loop.close()


async def test_worker_stop_propagates_dispatch_error_while_loop_remains_open(
    lifecycle_setup, monkeypatch, caplog
):
    manager, server, lifecycle = lifecycle_setup
    owner_loop = Mock()
    owner_loop.is_closed.return_value = False
    failure = RuntimeError("dispatch tripwire")
    owner_loop.call_soon_threadsafe.side_effect = failure
    starting = Mock()
    starting.get_loop.return_value = owner_loop
    manager._pending_start_tasks = {"server": starting}

    with pytest.raises(RuntimeError, match="dispatch tripwire") as caught:
        await asyncio.to_thread(manager.stop_server_sync, "server")

    assert caught.value is failure
    assert not owner_loop.is_closed()
    owner_loop.call_soon_threadsafe.assert_called_once_with(
        manager._request_stop, "server"
    )
    server.disable.assert_called_once()
    assert manager.is_autostart_suppressed("server")
    lifecycle.stop_server.assert_not_awaited()
    assert "MCP stop cleanup dispatch failed" not in caplog.text


async def test_stop_exception_is_not_reported_as_success(lifecycle_setup):
    manager, _, lifecycle = lifecycle_setup
    lifecycle.stop_server.side_effect = RuntimeError("cannot stop")
    assert await manager.stop_server("server") is False
    manager.status_tracker.set_status.assert_called_with("server", ServerState.ERROR)
    manager.status_tracker.record_stop_time.assert_not_called()


async def test_unknown_servers_do_not_schedule_tasks(lifecycle_setup):
    manager, _, lifecycle = lifecycle_setup
    assert not manager.start_server_sync("missing")
    assert not manager.stop_server_sync("missing")
    assert not await manager.start_server("missing")
    assert not await manager.stop_server("missing")
    lifecycle.start_server.assert_not_awaited()
    lifecycle.stop_server.assert_not_awaited()


def test_sync_start_without_loop_does_not_invent_readiness(lifecycle_setup):
    manager, server, lifecycle = lifecycle_setup
    assert not manager.start_server_sync("server")
    server.enable.assert_not_called()
    lifecycle.start_server.assert_not_called()
    manager.status_tracker.set_status.assert_not_called()


async def test_cancelled_waiter_does_not_cancel_shared_start(lifecycle_setup):
    manager, _, lifecycle = lifecycle_setup
    entered, release = asyncio.Event(), asyncio.Event()

    async def start(*args):
        entered.set()
        await release.wait()
        return True

    lifecycle.start_server.side_effect = start
    waiter = asyncio.create_task(manager.start_server("server"))
    await entered.wait()
    startup = manager._pending_start_tasks["server"]
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert not startup.done()
    release.set()
    assert await manager.start_server("server")
    lifecycle.start_server.assert_awaited_once()


@pytest.mark.parametrize("entrypoint", ["sync", "async"])
async def test_config_disable_blocks_implicit_not_manual_start(
    lifecycle_setup, entrypoint
):
    manager, server, lifecycle = lifecycle_setup
    server.config.enabled = False
    if entrypoint == "sync":
        assert not manager.start_server_sync("server", auto_start=True)
    else:
        assert not await manager.start_server("server", auto_start=True)
    lifecycle.start_server.assert_not_called()
    server.enable.assert_not_called()
    manager.status_tracker.set_status.assert_not_called()

    if entrypoint == "sync":
        assert manager.start_server_sync("server")
        assert await manager._pending_start_tasks["server"]
    else:
        assert await manager.start_server("server")
    server.enable.assert_called_once()
    lifecycle.start_server.assert_awaited_once()
    assert server.config.enabled is False


async def test_explicit_start_after_stop_can_restart(lifecycle_setup):
    manager, server, lifecycle = lifecycle_setup
    assert await manager.start_server("server")
    assert await manager.stop_server("server")
    assert await manager.start_server("server")
    assert lifecycle.start_server.await_count == 2
    assert server.enable.call_count == 2
    manager.status_tracker.set_status.assert_called_with("server", ServerState.RUNNING)


@pytest.fixture
def cache_invalidations(monkeypatch, lifecycle_setup):
    manager, _, _ = lifecycle_setup
    observations = []
    monkeypatch.setattr(
        "code_puppy.mcp_.agent_bindings.invalidate_agent_mcp_cache",
        lambda: observations.append(manager.is_autostart_suppressed("server")),
    )
    return observations


@pytest.mark.parametrize("failure", [False, RuntimeError("broken")])
async def test_failed_start_disables_without_suppressing_autostart(
    lifecycle_setup, cache_invalidations, failure
):
    manager, server, lifecycle = lifecycle_setup
    assert manager.is_autostart_suppressed("server") is False
    assert manager.is_autostart_suppressed("missing") is False
    if isinstance(failure, Exception):
        lifecycle.start_server.side_effect = failure
    else:
        lifecycle.start_server.return_value = failure

    assert not await manager.start_server("server")
    server.disable.assert_called_once()
    assert manager.is_autostart_suppressed("server") is False
    assert cache_invalidations == [False]


async def test_stop_suppresses_immediately_and_explicit_restart_clears(
    lifecycle_setup, cache_invalidations
):
    manager, _, _ = lifecycle_setup
    assert manager.stop_server_sync("server")
    assert manager.is_autostart_suppressed("server") is True
    assert cache_invalidations == [True]
    # Rejected starts must not clear suppression while stopping.
    assert not manager.start_server_sync("server")
    assert manager.is_autostart_suppressed("server") is True
    assert await manager._pending_stop_tasks["server"]
    assert manager.start_server_sync("server")
    assert manager.is_autostart_suppressed("server") is False
    assert await manager._pending_start_tasks["server"]
    assert cache_invalidations == [True, False]


@pytest.mark.parametrize("operation", ["stop", "start"])
def test_no_loop_only_stop_suppresses_autostart(
    lifecycle_setup, cache_invalidations, operation
):
    manager, _, _ = lifecycle_setup
    result = getattr(manager, f"{operation}_server_sync")("server")
    assert result is (operation == "stop")
    assert manager.is_autostart_suppressed("server") is (operation == "stop")
    assert cache_invalidations == [operation == "stop"]


def test_no_loop_start_cannot_clear_explicit_stop(lifecycle_setup):
    manager, _, _ = lifecycle_setup
    assert manager.stop_server_sync("server")
    assert not manager.start_server_sync("server")
    assert manager.is_autostart_suppressed("server") is True


async def test_start_failure_after_stop_preserves_suppression(lifecycle_setup):
    manager, _, lifecycle = lifecycle_setup
    entered, cancelled = asyncio.Event(), asyncio.Event()

    async def fail_on_cancel(*args):
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise RuntimeError("startup cleanup failed")

    lifecycle.start_server.side_effect = fail_on_cancel
    waiter = asyncio.create_task(manager.start_server("server"))
    await entered.wait()
    assert await manager.stop_server("server")
    assert not await waiter
    assert cancelled.is_set()
    assert manager.is_autostart_suppressed("server") is True
    manager.status_tracker.set_status.assert_called_with("server", ServerState.STOPPED)


async def test_successful_start_invalidates_real_cached_toolsets(
    lifecycle_setup, monkeypatch
):
    from code_puppy.agents import agent_manager

    manager, server, _ = lifecycle_setup
    agent = Mock()
    agent._mcp_servers = [server]
    monkeypatch.setattr(agent_manager, "_CURRENT_AGENT", agent)
    assert await manager.start_server("server")
    assert agent._code_generation_agent is None
    assert agent.pydantic_agent is None
    assert agent._mcp_servers == []


async def test_stop_invalidates_real_cached_toolsets(lifecycle_setup, monkeypatch):
    from code_puppy.agents import agent_manager

    manager, server, _ = lifecycle_setup
    agent = Mock()
    agent._mcp_servers = [server]
    monkeypatch.setattr(agent_manager, "_CURRENT_AGENT", agent)
    assert manager.stop_server_sync("server")
    assert agent._code_generation_agent is None
    assert agent.pydantic_agent is None
    assert agent._mcp_servers == []
    assert await manager._pending_stop_tasks["server"]
