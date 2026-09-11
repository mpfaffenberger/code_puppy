"""Disabled availability must not erase ownership of a materialized toolset."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic_ai.toolsets import FunctionToolset

from code_puppy.mcp_.async_lifecycle import AsyncServerLifecycleManager
from code_puppy.mcp_.managed_server import ManagedMCPServer, ServerConfig
from code_puppy.mcp_.manager import MCPManager


class RefcountedConnector(FunctionToolset):
    def __init__(self):
        super().__init__()
        self.owners = 0

    @property
    def is_running(self):
        return self.owners > 0

    async def __aenter__(self):
        self.owners += 1
        return self

    async def __aexit__(self, *args):
        self.owners -= 1


@pytest.mark.parametrize("initially_disabled", [False, True])
async def test_repeated_restart_preserves_retained_owner(
    monkeypatch, initially_disabled
):
    made = []

    def create_server(server):
        leaf = RefcountedConnector()
        server._pydantic_server = leaf.prefixed("test")
        made.append(leaf)

    monkeypatch.setattr(ManagedMCPServer, "_create_server", create_server)
    lifecycle = AsyncServerLifecycleManager()
    monkeypatch.setattr(
        "code_puppy.mcp_.manager.get_lifecycle_manager", lambda: lifecycle
    )
    config = ServerConfig(id="a", name="a", type="stdio", config={})
    old = ManagedMCPServer(config)
    old.enable()
    toolset = old.get_pydantic_server()
    manager = object.__new__(MCPManager)
    manager._managed_servers = {"a": old}
    manager.registry = SimpleNamespace(get=lambda key: config)
    manager.status_tracker = Mock()

    # A second agent keeps its own entry after the lifecycle's entry drains.
    async with toolset:
        await lifecycle.start_server("a", toolset)
        assert made[0].owners == 2
        if initially_disabled:
            old.disable()
        try:
            for _ in range(2):
                assert not await manager.restart_server("a")
                assert manager._managed_servers["a"] is old
                assert not old.is_enabled()
                assert made[0].owners == 1
                assert len(made) == 1
        finally:
            await lifecycle.stop_all()
    assert made[0].owners == 0

    try:
        assert await manager.restart_server("a")
        assert manager._managed_servers["a"] is not old
        assert len(made) == 2
        assert made[1].owners == 1
    finally:
        await lifecycle.stop_all()
    assert made[1].owners == 0
