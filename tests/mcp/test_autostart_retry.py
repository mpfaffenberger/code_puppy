"""Bound-agent retries against a real stdio MCP process, without an LLM."""

import asyncio
import json
import sys
import threading
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from code_puppy.agents import _builder, _key_listeners, _mcp, _runtime
from code_puppy.agents.json_agent import JSONAgent
from code_puppy.mcp_ import agent_bindings
from code_puppy.mcp_.async_lifecycle import AsyncServerLifecycleManager
from code_puppy.mcp_.managed_server import ManagedMCPServer, ServerConfig, ServerState
from code_puppy.mcp_.manager import MCPManager
from code_puppy.mcp_.status_tracker import ServerStatusTracker


@pytest.fixture
async def bound_server(tmp_path, monkeypatch):
    script = tmp_path / "server.py"
    ready = tmp_path / "ready"
    script.write_text(
        "import pathlib, sys\n"
        "if not pathlib.Path(sys.argv[1]).exists():\n"
        "    raise SystemExit(1)\n"
        "from mcp.server.fastmcp import FastMCP\n"
        "mcp = FastMCP('retry')\n"
        "@mcp.tool()\n"
        "def ping() -> str:\n"
        "    return 'pong'\n"
        "mcp.run()\n"
    )
    agent_path = tmp_path / "agent.json"
    agent_path.write_text(
        json.dumps(
            {
                "name": "retry-agent",
                "description": "Local retry test",
                "system_prompt": "Use the ping tool.",
                "tools": [],
                "mcp_servers": ["retry"],
            }
        )
    )
    agent = JSONAgent(agent_path)
    monkeypatch.setattr(
        agent_bindings, "BINDINGS_FILE", str(tmp_path / "bindings.json")
    )
    monkeypatch.setattr(agent_bindings, "_session_bindings", {})
    monkeypatch.setattr(
        "code_puppy.agents.agent_manager.load_agent", lambda name: agent
    )
    config = ServerConfig(
        id="retry",
        name="retry",
        type="stdio",
        config={"command": sys.executable, "args": [str(script), str(ready)]},
    )
    managed = ManagedMCPServer(config)
    manager = MCPManager.__new__(MCPManager)
    manager._managed_servers = {config.id: managed}
    manager.registry = Mock()
    manager.registry.get_by_name.return_value = config
    manager.status_tracker = ServerStatusTracker()
    manager.status_tracker.set_status(config.id, ServerState.STOPPED)
    lifecycle = AsyncServerLifecycleManager()
    monkeypatch.setattr(
        lifecycle, "start_server", AsyncMock(wraps=lifecycle.start_server)
    )
    monkeypatch.setattr(
        "code_puppy.mcp_.manager.get_lifecycle_manager", lambda: lifecycle
    )
    monkeypatch.setattr(_mcp, "get_mcp_manager", lambda: manager)
    monkeypatch.setattr(_mcp, "get_truthy_bool_value", lambda *a: False)
    monkeypatch.setattr(_mcp, "on_pre_mcp_autostart_sync", Mock())
    monkeypatch.setattr(_mcp, "on_pre_mcp_autostart", AsyncMock())
    try:
        yield SimpleNamespace(
            manager=manager,
            managed=managed,
            lifecycle=lifecycle,
            ready=ready,
            agent_name=agent.name,
            agent=agent,
        )
    finally:
        await asyncio.wait_for(lifecycle.stop_all(), timeout=5)
        assert not lifecycle._servers


@pytest.fixture
def offline_runtime(bound_server, monkeypatch):
    seen_tools = []

    def model(messages, info):
        names = {tool.name for tool in info.function_tools}
        seen_tools.append(names & {"retry_ping"})
        if "retry_ping" not in names:
            return ModelResponse(parts=[TextPart("No tools available")])
        if len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart("retry_ping", {})])
        tool_return = next(
            part for part in messages[-1].parts if isinstance(part, ToolReturnPart)
        )
        assert "pong" in str(tool_return.content)
        return ModelResponse(parts=[TextPart("pong")])

    async def stream(messages, info):
        for part in model(messages, info).parts:
            if isinstance(part, ToolCallPart):
                yield {0: DeltaToolCall(name=part.tool_name, json_args="{}")}
            else:
                yield part.content

    function_model = FunctionModel(model, stream_function=stream)
    monkeypatch.setattr(_builder.ModelFactory, "load_config", dict)
    monkeypatch.setattr(
        _builder, "load_model_with_fallback", lambda *a, **kw: (function_model, "test")
    )
    monkeypatch.setattr(_builder, "make_model_settings", lambda *a, **kw: None)
    monkeypatch.setattr(_builder, "load_puppy_rules", lambda: None)
    monkeypatch.setattr(_runtime, "get_enable_streaming", lambda: False)
    monkeypatch.setattr(_runtime, "sigint_fallback_cancels", lambda: True)
    monkeypatch.setattr(_runtime, "should_render_fallback", lambda *a, **kw: False)
    monkeypatch.setattr(
        "code_puppy.model_switching.resolve_run_model_selection", Mock()
    )
    monkeypatch.setattr(
        "code_puppy.agents.agent_manager._CURRENT_AGENT", bound_server.agent
    )
    return seen_tools


@pytest.fixture
def offline_subagent(bound_server, offline_runtime, monkeypatch):
    from code_puppy import config
    from code_puppy.tools import subagent_invocation

    get_value = config.get_value
    monkeypatch.setattr(
        config,
        "get_value",
        lambda key: False if key == "disable_mcp_servers" else get_value(key),
    )
    monkeypatch.setattr(config, "get_output_level", lambda: "medium")
    monkeypatch.setattr(bound_server.agent, "get_model_name", lambda: "test")
    monkeypatch.setattr(
        "code_puppy.model_factory.make_model_settings", lambda *a, **kw: None
    )
    monkeypatch.setattr("code_puppy.mcp_.get_mcp_manager", lambda: bound_server.manager)
    monkeypatch.setattr(subagent_invocation, "_save_session_history", Mock())
    monkeypatch.setattr(subagent_invocation, "_load_session_history", lambda *a: [])
    monkeypatch.setattr(subagent_invocation, "on_agent_run_context", lambda *a: [])
    monkeypatch.setattr(
        subagent_invocation, "on_wrap_pydantic_agent", lambda cfg, agent, **kw: agent
    )

    async def invoke():
        result = await subagent_invocation._invoke_agent_impl(
            Mock(), bound_server.agent_name, "Ping", emit_response_message=False
        )
        assert result.error is None
        return result

    return invoke


@pytest.mark.parametrize("entrypoint", ["main", "subagent"])
async def test_failed_bound_server_retries_on_next_invocation(
    bound_server, offline_runtime, offline_subagent, entrypoint
):
    case = bound_server

    async def invoke():
        if entrypoint == "main":
            case.agent.clear_message_history()
            await case.agent.run_with_mcp("Ping")
        else:
            await offline_subagent()

    await invoke()
    assert not case.lifecycle.is_running("retry")
    assert not case.managed.is_enabled()
    assert not case.manager.is_autostart_suppressed("retry")
    assert case.manager.status_tracker.get_server_summary("retry")["state"] == "error"
    assert case.lifecycle.start_server.await_count == 1

    case.ready.touch()
    await invoke()
    assert case.lifecycle.is_running("retry")
    assert case.lifecycle.start_server.await_count == 2
    toolsets = case.manager.get_servers_for_agent(case.agent_name)
    assert len(toolsets) == 1
    assert offline_runtime == [set(), {"retry_ping"}, {"retry_ping"}]

    assert await case.manager.stop_server("retry")
    await invoke()
    assert case.manager.is_autostart_suppressed("retry")
    assert not case.lifecycle.is_running("retry")
    assert case.manager.get_servers_for_agent(case.agent_name) == []
    assert case.lifecycle.start_server.await_count == 2
    assert await case.manager.start_server("retry")
    assert not case.manager.is_autostart_suppressed("retry")
    assert case.lifecycle.is_running("retry")


@pytest.mark.parametrize("entrypoint", ["main", "subagent"])
@pytest.mark.parametrize("disable_at", ["config", "prehook"])
async def test_config_disabled_blocks_autostart_but_manual_start_can_enable(
    bound_server, offline_runtime, offline_subagent, monkeypatch, entrypoint, disable_at
):
    case = bound_server
    case.ready.touch()
    if disable_at == "config":
        config = replace(case.managed.config, enabled=False)
        case.manager.registry.get_by_name.return_value = config
        case.managed = ManagedMCPServer(config)
        case.manager._managed_servers["retry"] = case.managed
    else:

        async def disable(*args):
            config = replace(case.managed.config, enabled=False)
            assert case.manager.update_server("retry", config)

        monkeypatch.setattr(_mcp, "on_pre_mcp_autostart", disable)

    async def invoke():
        case.agent.clear_message_history()
        if entrypoint == "main":
            await case.agent.run_with_mcp("Ping")
        else:
            await offline_subagent()

    await invoke()
    assert case.managed.config.enabled is False
    assert not case.managed.is_enabled()
    assert not case.lifecycle.is_running("retry")
    case.lifecycle.start_server.assert_not_awaited()
    assert case.manager.get_servers_for_agent(case.agent_name) == []
    assert offline_runtime == [set()]

    assert await case.manager.start_server("retry")
    assert case.managed.config.enabled is False
    assert case.managed.is_enabled()
    assert case.lifecycle.is_running("retry")
    offline_runtime.clear()
    await invoke()
    assert offline_runtime == [{"retry_ping"}, {"retry_ping"}]
    case.lifecycle.start_server.assert_awaited_once()


def test_no_loop_autostart_can_retry_when_loop_is_available(monkeypatch):
    config = ServerConfig(id="retry", name="retry", type="stdio")
    manager = MCPManager.__new__(MCPManager)
    managed = Mock()
    managed.config = config
    manager._managed_servers = {config.id: managed}
    manager.registry = Mock()
    manager.registry.get_by_name.return_value = config
    manager.status_tracker = Mock()
    manager.get_server_status = Mock(return_value={"state": "stopped"})
    lifecycle = AsyncMock()
    lifecycle.start_server.return_value = True
    monkeypatch.setattr(
        "code_puppy.mcp_.manager.get_lifecycle_manager", lambda: lifecycle
    )
    monkeypatch.setattr(
        agent_bindings,
        "get_bound_servers",
        lambda name: {"retry": {"auto_start": True}},
    )
    monkeypatch.setattr(_mcp, "on_pre_mcp_autostart_sync", Mock())
    monkeypatch.setattr(_mcp, "on_pre_mcp_autostart", AsyncMock())
    _builder._autostart_bound_servers(manager, "retry-agent")
    assert not manager.is_autostart_suppressed("retry")
    lifecycle.start_server.assert_not_called()
    asyncio.run(_builder.autostart_bound_servers_async(manager, "retry-agent"))
    lifecycle.start_server.assert_awaited_once()
    managed.enable.assert_called_once()


async def test_cached_no_loop_build_recovers_on_first_run(
    bound_server, offline_runtime
):
    case = bound_server
    case.ready.touch()
    await asyncio.to_thread(case.agent.reload_code_generation_agent)
    assert case.agent._code_generation_agent is not None
    assert case.agent._mcp_servers == []
    assert not case.manager.is_autostart_suppressed("retry")
    await case.agent.run_with_mcp("Ping")
    assert offline_runtime == [{"retry_ping"}, {"retry_ping"}]
    assert case.lifecycle.is_running("retry")


@pytest.mark.parametrize("entrypoint", ["sync", "async"])
async def test_stop_during_pre_autostart_hook_wins(
    bound_server, monkeypatch, entrypoint
):
    case = bound_server
    case.ready.touch()
    if entrypoint == "sync":
        monkeypatch.setattr(
            _mcp,
            "on_pre_mcp_autostart_sync",
            lambda *a: case.manager.stop_server_sync("retry"),
        )
        _mcp._autostart_bound_servers(case.manager, case.agent_name)
        await case.manager._pending_stop_tasks["retry"]
    else:

        async def stop(*args):
            assert await case.manager.stop_server("retry")

        monkeypatch.setattr(_mcp, "on_pre_mcp_autostart", stop)
        await _mcp.autostart_bound_servers_async(case.manager, case.agent_name)
    assert case.manager.is_autostart_suppressed("retry")
    assert not case.lifecycle.is_running("retry")
    assert not case.managed.is_enabled()


@pytest.mark.parametrize("change", ["recovered", "stopped"])
async def test_other_agent_lifecycle_change_refreshes_cached_tools(
    bound_server, offline_runtime, monkeypatch, change
):
    case = bound_server
    if change == "stopped":
        case.ready.touch()
    await case.agent.run_with_mcp("Ping")
    cached = case.agent._code_generation_agent
    monkeypatch.setattr("code_puppy.agents.agent_manager._CURRENT_AGENT", None)
    if change == "recovered":
        case.ready.touch()
        await _mcp.autostart_bound_servers_async(case.manager, "other-agent")
    else:
        assert await case.manager.stop_server("retry")
    assert case.agent._code_generation_agent is cached
    case.agent.clear_message_history()
    offline_runtime.clear()
    await case.agent.run_with_mcp("Ping")
    expected = [{"retry_ping"}, {"retry_ping"}] if change == "recovered" else [set()]
    assert offline_runtime == expected
    assert case.agent._code_generation_agent is not cached


@pytest.mark.parametrize("cancel_caller", [False, True])
async def test_stop_during_preparation_does_not_cancel_agent_turn(
    bound_server, offline_runtime, cancel_caller
):
    case = bound_server
    entered = asyncio.Event()

    async def block(*args):
        entered.set()
        await asyncio.Event().wait()

    case.lifecycle.start_server.side_effect = block
    invocation = asyncio.create_task(case.agent.run_with_mcp("Ping"))
    await entered.wait()
    if cancel_caller:
        invocation.cancel()
    assert await case.manager.stop_server("retry")
    if cancel_caller:
        with pytest.raises(asyncio.CancelledError):
            await invocation
        assert offline_runtime == []
    else:
        await asyncio.wait_for(invocation, timeout=2)
        assert invocation.cancelling() == 0
        assert offline_runtime == [set()]
    assert case.manager.is_autostart_suppressed("retry")
    assert not case.lifecycle.is_running("retry")


@pytest.mark.parametrize("cancel_key", ["\x03", "\x0b"])
@pytest.mark.parametrize("persistent_listener", [False, True])
async def test_cancel_hotkey_during_preparation_respects_editor_and_cleans_up(
    bound_server, offline_runtime, monkeypatch, cancel_key, persistent_listener
):
    from code_puppy.messaging import run_ui
    from code_puppy.messaging.line_editor import RunningLineEditor
    from code_puppy.tools import command_runner

    case = bound_server
    entered = asyncio.Event()
    release = asyncio.Event()
    start = case.lifecycle.start_server._mock_wraps

    async def delayed_start(*args):
        entered.set()
        await release.wait()
        return await start(*args)

    case.ready.touch()
    case.lifecycle.start_server.side_effect = delayed_start
    handle = _key_listeners.KeyListenerHandle(Mock(), threading.Event())
    monkeypatch.setattr(_key_listeners, "_active_handle", None)
    monkeypatch.setattr(_key_listeners, "_cancel_handler", None)
    if persistent_listener:
        _key_listeners.set_active_handle(handle)
    spawn = Mock(return_value=handle)
    monkeypatch.setattr(_key_listeners, "spawn_key_listener", spawn)
    editor = RunningLineEditor(
        bar=Mock(), history=Mock(), reverse_search=Mock(active=False)
    )
    monkeypatch.setattr(run_ui, "_editor", editor)
    monkeypatch.setattr(_key_listeners, "_line_editor", editor)
    editor.insert_paste_text("half-typed steer")

    invocation = asyncio.create_task(case.agent.run_with_mcp("Ping"))
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        assert _key_listeners._resolve_cancel_handler(None) is not None
        assert command_runner._AGENT_CANCEL_CB is not None
        _key_listeners._dispatch_key(cancel_key, lambda: None, cancel_key, None)
        if cancel_key == "\x03":
            await asyncio.sleep(0)
            assert not invocation.done()
            assert invocation.cancelling() == 0
            assert editor.buffer == ""
            _key_listeners._dispatch_key(cancel_key, lambda: None, cancel_key, None)
        else:
            assert editor.buffer == "half-typed steer"
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(invocation, timeout=2)
        assert offline_runtime == []
        assert _key_listeners._resolve_cancel_handler(None) is None
        assert command_runner._AGENT_CANCEL_CB is None
        if persistent_listener:
            spawn.assert_not_called()
            assert _key_listeners.get_active_handle() is handle
            assert not handle.stop_event.is_set()
        else:
            spawn.assert_called_once()
            assert _key_listeners.get_active_handle() is None
            assert handle.stop_event.is_set()
            handle.thread.join.assert_called_once_with(timeout=1.0)
        # Cancelling one turn must not cancel a shared server's lifecycle task.
        release.set()
        assert await case.manager.start_server("retry")
        case.agent.clear_message_history()
        await case.agent.run_with_mcp("Ping")
        assert offline_runtime == [{"retry_ping"}, {"retry_ping"}]
        assert _key_listeners._resolve_cancel_handler(None) is None
    finally:
        release.set()
        if not invocation.done():
            invocation.cancel()
        await asyncio.gather(invocation, return_exceptions=True)


@pytest.mark.parametrize("cancel_during", ["inner", "startup"])
async def test_pre_autostart_nested_run_preserves_outer_cancellation(
    bound_server, offline_runtime, monkeypatch, tmp_path, cancel_during
):
    from code_puppy import callbacks
    from code_puppy.tools import command_runner

    case = bound_server
    inner_path = tmp_path / "inner.json"
    inner_path.write_text(
        json.dumps(
            {
                "name": "inner",
                "description": "Nested",
                "system_prompt": "Hi",
                "tools": [],
            }
        ),
        encoding="utf-8",
    )
    inner = JSONAgent(inner_path)
    entered = asyncio.Event()
    if cancel_during == "inner":

        class BlockedClient:
            async def run(self, *args, **kwargs):
                entered.set()
                await asyncio.Event().wait()

        inner._code_generation_agent = BlockedClient()
    monkeypatch.setattr(
        agent_bindings,
        "get_bound_servers",
        lambda name: {"retry": {"auto_start": True}} if name == case.agent_name else {},
    )
    monkeypatch.setattr(_mcp, "on_pre_mcp_autostart", callbacks.on_pre_mcp_autostart)
    monkeypatch.setitem(callbacks._callbacks, "pre_mcp_autostart", [])
    ownership = []

    async def nested_run(*args):
        key_owner = _key_listeners._resolve_cancel_handler(None)
        shell_owner = command_runner._AGENT_CANCEL_CB
        await inner.run_with_mcp("Hi")
        ownership.append(
            (
                _key_listeners._resolve_cancel_handler(None) is key_owner,
                command_runner._AGENT_CANCEL_CB is shell_owner,
            )
        )

    callbacks.register_callback("pre_mcp_autostart", nested_run)
    handle = _key_listeners.KeyListenerHandle(Mock(), threading.Event())
    monkeypatch.setattr(_key_listeners, "_active_handle", handle)
    monkeypatch.setattr(_key_listeners, "_cancel_handler", None)
    monkeypatch.setattr(command_runner, "_AGENT_CANCEL_CB", None)

    async def block(*args):
        entered.set()
        await asyncio.Event().wait()

    case.lifecycle.start_server.side_effect = block
    invocation = asyncio.create_task(case.agent.run_with_mcp("Ping"))
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        if cancel_during == "startup":
            assert ownership == [(True, True)]
        _key_listeners._dispatch_key("\u000b", lambda: None, "\u000b", None)
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(invocation, timeout=2)
        assert ownership == [(True, True)]
        assert offline_runtime == ([set()] if cancel_during == "startup" else [])
        assert case.lifecycle.start_server.await_count == int(
            cancel_during == "startup"
        )
        assert _key_listeners._resolve_cancel_handler(None) is None
        assert command_runner._AGENT_CANCEL_CB is None
        assert _runtime._active_run_depth == 0
    finally:
        invocation.cancel()
        await asyncio.gather(invocation, return_exceptions=True)
        await case.manager.stop_server("retry")


async def test_pending_start_is_awaited_before_using_cached_client(
    bound_server, offline_runtime
):
    case = bound_server
    case.ready.touch()
    case.managed.disable()
    assert case.manager.start_server_sync("retry")
    _builder.build_pydantic_agent(case.agent)
    assert case.agent._mcp_servers == []
    await case.agent.run_with_mcp("Ping")
    assert offline_runtime == [{"retry_ping"}, {"retry_ping"}]
    assert case.lifecycle.start_server.await_count == 1


@pytest.mark.parametrize("disabled", ["tools", "mcp"])
async def test_preparation_respects_disable_flags(monkeypatch, disabled):
    get_manager = Mock(side_effect=AssertionError("MCP must remain disabled"))
    monkeypatch.setattr(_mcp, "get_mcp_manager", get_manager)
    monkeypatch.setattr(_mcp, "get_truthy_bool_value", lambda *a: disabled == "mcp")
    monkeypatch.setattr("code_puppy.tools.tools_disabled", lambda: disabled == "tools")
    async with _mcp.prepared_mcp_run(SimpleNamespace(name="agent")):
        assert _mcp.load_mcp_servers(agent_name="agent") == []
    get_manager.assert_not_called()


async def test_preparation_error_is_best_effort_without_build_retry(
    monkeypatch, caplog
):
    manager = Mock()
    manager.get_servers_for_agent.return_value = []
    monkeypatch.setattr(_mcp, "get_mcp_manager", lambda: manager)
    monkeypatch.setattr(_mcp, "get_truthy_bool_value", lambda *a: False)
    start = AsyncMock(side_effect=RuntimeError("broken prehook"))
    monkeypatch.setattr(_mcp, "autostart_bound_servers_async", start)
    sync_start = Mock()
    monkeypatch.setattr(_mcp, "_autostart_bound_servers", sync_start)
    async with _mcp.prepared_mcp_run(SimpleNamespace(name="agent")):
        assert _mcp.load_mcp_servers(agent_name="agent") == []
    assert "Could not prepare MCP servers for agent agent" in caplog.text
    sync_start.assert_not_called()
    assert _mcp._prepared_agent.get() is None


@pytest.mark.parametrize("availability", ["disabled", "quarantined", "missing"])
async def test_startup_access_keeps_unready_toolsets_hidden(bound_server, availability):
    managed = bound_server.managed
    managed.disable()
    if availability == "quarantined":
        managed.quarantine(3600)
    elif availability == "missing":
        managed._pydantic_server = None
    with pytest.raises(RuntimeError):
        managed.get_pydantic_server()
    if availability == "disabled":
        assert managed.get_pydantic_server(allow_disabled=True) is not None
    else:
        with pytest.raises(RuntimeError):
            managed.get_pydantic_server(allow_disabled=True)
    assert not managed.is_enabled()
    assert bound_server.manager.get_servers_for_agent(bound_server.agent_name) == []
