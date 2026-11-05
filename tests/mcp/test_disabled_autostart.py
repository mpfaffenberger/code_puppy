"""Configured-disabled bindings must not churn agent caches or startup hooks."""

import asyncio
from dataclasses import replace
from unittest.mock import Mock

import pytest
from test_autostart_retry import bound_server as bound_server
from test_autostart_retry import offline_runtime as offline_runtime
from test_autostart_retry import offline_subagent as offline_subagent

from code_puppy.agents import _builder, _mcp
from code_puppy.agents.json_agent import JSONAgent
from code_puppy.mcp_ import agent_bindings
from code_puppy.mcp_.managed_server import ManagedMCPServer, ServerState


@pytest.mark.parametrize(
    "entrypoint",
    ["main", "subagent", "sync", "direct_sync", "direct_async", "no_loop"],
)
async def test_disabled_autostart_has_no_repeated_side_effects(
    bound_server, offline_runtime, offline_subagent, monkeypatch, entrypoint
):
    case = bound_server
    config = replace(case.managed.config, enabled=False)
    case.manager.registry.get_by_name.return_value = config
    case.managed = ManagedMCPServer(config)
    case.manager._managed_servers["retry"] = case.managed
    if entrypoint in ("main", "subagent"):
        cached_main = case.agent
        if entrypoint == "subagent":
            cached_main = JSONAgent(case.agent.json_path)
            cached_main._config["name"] = "unrelated-main"
            get_bindings = agent_bindings.get_bound_servers
            monkeypatch.setattr(
                agent_bindings,
                "get_bound_servers",
                lambda name: {} if name == cached_main.name else get_bindings(name),
            )
        monkeypatch.setattr(
            "code_puppy.agents.agent_manager._CURRENT_AGENT", cached_main
        )
        _builder.build_pydantic_agent(cached_main)
        cached = cached_main._code_generation_agent
        assert cached is not None
        _mcp.on_pre_mcp_autostart.reset_mock()
        _mcp.on_pre_mcp_autostart_sync.reset_mock()
    invalidate = Mock(wraps=agent_bindings.invalidate_agent_mcp_cache)
    monkeypatch.setattr(agent_bindings, "invalidate_agent_mcp_cache", invalidate)

    for _ in range(3):
        if entrypoint == "main":
            case.agent.clear_message_history()
            await case.agent.run_with_mcp("Ping")
        elif entrypoint == "subagent":
            await offline_subagent()
        elif entrypoint == "sync":
            await asyncio.to_thread(
                _mcp._autostart_bound_servers, case.manager, case.agent_name
            )
        elif entrypoint == "direct_sync":
            assert not case.manager.start_server_sync("retry", auto_start=True)
        elif entrypoint == "direct_async":
            assert not await case.manager.start_server("retry", auto_start=True)
        else:
            assert not await asyncio.to_thread(
                case.manager.start_server_sync, "retry", auto_start=True
            )

    observations = (
        _mcp.on_pre_mcp_autostart.call_count,
        _mcp.on_pre_mcp_autostart_sync.call_count,
        invalidate.call_count,
        case.lifecycle.start_server.await_count,
    )
    assert observations == (0, 0, 0, 0)
    assert not case.managed.is_enabled()
    assert not case.manager.is_autostart_suppressed("retry")
    if entrypoint in ("main", "subagent"):
        assert offline_runtime == [set(), set(), set()]
        assert cached_main._code_generation_agent is cached
        assert cached_main.pydantic_agent is cached
        assert cached_main._mcp_servers == []


@pytest.mark.parametrize(
    "entrypoint", ["sync", "async", "direct_sync", "direct_async", "no_loop"]
)
async def test_config_disabled_still_disables_previously_enabled_unready_server(
    bound_server, monkeypatch, entrypoint
):
    case = bound_server
    config = replace(case.managed.config, enabled=False)
    case.manager.registry.get_by_name.return_value = config
    case.managed = ManagedMCPServer(config)
    case.manager._managed_servers["retry"] = case.managed
    case.ready.touch()
    assert await case.manager.start_server("retry")
    assert case.managed.is_enabled()
    # A manually started server can become unready without losing availability.
    case.managed._state = ServerState.ERROR
    invalidate = Mock()
    monkeypatch.setattr(agent_bindings, "invalidate_agent_mcp_cache", invalidate)

    for _ in range(3):
        if entrypoint == "sync":
            _mcp._autostart_bound_servers(case.manager, case.agent_name)
        elif entrypoint == "async":
            await _mcp.autostart_bound_servers_async(case.manager, case.agent_name)
        elif entrypoint == "direct_sync":
            assert not case.manager.start_server_sync("retry", auto_start=True)
        elif entrypoint == "direct_async":
            assert not await case.manager.start_server("retry", auto_start=True)
        else:
            assert not await asyncio.to_thread(
                case.manager.start_server_sync, "retry", auto_start=True
            )

    assert not case.managed.is_enabled()
    invalidate.assert_called_once_with()
    case.lifecycle.start_server.assert_awaited_once()
    assert not case.manager.is_autostart_suppressed("retry")
