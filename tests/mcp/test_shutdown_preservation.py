"""Narrow contracts: preserve objects, and drain registered contexts safely."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from pydantic_ai.toolsets import FunctionToolset

from code_puppy import callbacks
from code_puppy.mcp_ import async_lifecycle as lifecycle
from code_puppy.mcp_.manager import MCPManager
from code_puppy.mcp_.managed_server import ServerConfig, ServerState


class Connector(FunctionToolset):
    def __init__(self, release=None, failure=None):
        super().__init__()
        self.is_running = False
        self.release, self.failure = release, failure
        self.cleaning = asyncio.Event()
        self.closed = 0

    async def __aenter__(self):
        self.is_running = True
        return self

    async def __aexit__(self, *args):
        self.cleaning.set()
        if self.release:
            await self.release.wait()
        if self.failure:
            raise self.failure
        self.is_running = False
        self.closed += 1


async def test_healthy_stop_does_not_wait_on_its_own_lock():
    manager = lifecycle.AsyncServerLifecycleManager()
    connector = Connector()
    assert await manager.start_server("a", connector.prefixed("a"))
    assert await asyncio.wait_for(manager.stop_server("a"), 0.5)
    assert connector.closed == 1 and "a" not in manager._servers


async def test_deadline_retains_owner_and_does_not_double_cancel(monkeypatch):
    monkeypatch.setattr(lifecycle, "SERVER_STOP_TIMEOUT", 0.02)
    release = asyncio.Event()
    connector = Connector(release)
    manager = lifecycle.AsyncServerLifecycleManager()
    assert await manager.start_server("a", connector)
    task = manager._servers["a"].task
    try:
        assert not await manager.stop_server("a")
        assert not await manager.stop_server("a")
        assert "a" in manager._servers
        assert not task.done()
        # A stale restart must not replace cleanup still in progress.
        assert not await manager.start_server("a", Connector())
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
    assert connector.closed == 1
    assert "a" not in manager._servers


async def test_cancelled_caller_preserves_original_cleanup():
    release = asyncio.Event()
    connector = Connector(release)
    manager = lifecycle.AsyncServerLifecycleManager()
    await manager.start_server("a", connector)
    task = manager._servers["a"].task
    stop = asyncio.create_task(manager.stop_server("a"))
    await connector.cleaning.wait()
    try:
        stop.cancel()
        with pytest.raises(asyncio.CancelledError):
            await stop
        assert not task.done()
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
    assert connector.closed == 1


@pytest.mark.parametrize("grouped", [False, True])
async def test_failed_cleanup_returns_false_and_shutdown_reports_it(grouped, caplog):
    caplog.set_level("DEBUG", logger="code_puppy.mcp_.async_lifecycle")
    error = RuntimeError("cleanup failed")
    if grouped:
        error = BaseExceptionGroup("cleanup", [error, asyncio.CancelledError()])
    manager = lifecycle.AsyncServerLifecycleManager()
    await manager.start_server("a", Connector(failure=error))
    assert not await manager.stop_server("a")
    assert manager._servers["a"].cleanup_failed
    assert not manager.is_running("a")
    assert any(
        record.exc_info and record.exc_info[1] is error for record in caplog.records
    )
    await manager.stop_all()
    assert "shutdown incomplete" in caplog.text


async def test_stop_all_drains_other_servers_while_one_is_stuck(monkeypatch):
    monkeypatch.setattr(lifecycle, "SERVER_STOP_TIMEOUT", 0.02)
    release = asyncio.Event()
    manager = lifecycle.AsyncServerLifecycleManager()
    slow, good = Connector(release), Connector()
    await manager.start_server("slow", slow)
    await manager.start_server("good", good)
    task = manager._servers["slow"].task
    try:
        await asyncio.wait_for(manager.stop_all(), 0.5)
        assert good.closed == 1
        assert "slow" in manager._servers and "good" not in manager._servers
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


def test_reinit_preserves_objects_and_status_while_adding_new_servers(monkeypatch):
    configs = [
        ServerConfig(id=x, name=x, type="stdio", config={}) for x in ("old", "new")
    ]
    registry = Mock()
    registry.list_all.return_value = configs[:1]
    monkeypatch.setattr("code_puppy.mcp_.manager.ServerRegistry", lambda: registry)
    monkeypatch.setattr(MCPManager, "sync_from_config", lambda self: None)
    monkeypatch.setattr(
        "code_puppy.mcp_.manager.ManagedMCPServer", lambda c: SimpleNamespace(config=c)
    )
    manager = MCPManager()
    old = manager._managed_servers["old"]
    tracker = manager.status_tracker
    tracker.set_status("old", ServerState.RUNNING)
    # Refresh the existing manager after configuration discovery, not __init__.
    registry.list_all.return_value = configs
    manager.sync_from_config()
    manager._initialize_servers()
    assert manager._managed_servers["old"] is old
    assert manager._managed_servers["new"].config is configs[1]
    assert manager.status_tracker is tracker
    assert tracker.get_status("old") == ServerState.RUNNING
    assert tracker.get_status("new") == ServerState.STOPPED


async def test_real_stdio_stop_closes_transport(tmp_path):
    import sys
    from fastmcp import Client
    from fastmcp.client.transports import StdioTransport
    from pydantic_ai.mcp import MCPToolset

    script = tmp_path / "connector.py"
    script.write_text(
        "import json,sys\n"
        "for line in sys.stdin:\n"
        " r=json.loads(line)\n"
        " if 'id' not in r: continue\n"
        " result={'protocolVersion':r.get('params',{}).get('protocolVersion','2025-03-26'),'capabilities':{},'serverInfo':{'name':'local','version':'1'}} if r['method']=='initialize' else {}\n"
        " print(json.dumps({'jsonrpc':'2.0','id':r['id'],'result':result}),flush=True)\n"
    )
    client = Client(
        StdioTransport(
            sys.executable,
            [str(script)],
            keep_alive=False,
            env={"HOME": str(tmp_path)},
            log_file=tmp_path / "stderr.log",
        ),
        timeout=3,
    )
    leaf = MCPToolset(client, id="local")
    manager = lifecycle.AsyncServerLifecycleManager()
    try:
        assert await asyncio.wait_for(
            manager.start_server("a", leaf.prefixed("local")), 5
        )
        assert client.is_connected()
        assert await asyncio.wait_for(manager.stop_server("a"), 5)
        assert not client.is_connected() and leaf._running_count == 0
        assert "a" not in manager._servers
    finally:
        await manager.stop_all()
        if client.is_connected():
            await client.close()


def test_one_shutdown_hook_for_multiple_managers():
    from code_puppy.mcp_.manager import _shutdown_mcp

    with (
        patch.object(MCPManager, "sync_from_config"),
        patch.object(MCPManager, "_initialize_servers"),
    ):
        MCPManager()
        MCPManager()
    assert callbacks._callbacks["shutdown"].count(_shutdown_mcp) == 1
