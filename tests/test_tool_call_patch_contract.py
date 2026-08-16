"""Contract tests for the pydantic-ai v2 tool execution boundary."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic_ai.tool_manager import ToolManager

from code_puppy import callbacks
from code_puppy.tool_call_patches import (
    patch_tool_call_callbacks,
    patch_tool_call_json_repair,
)

_DEFAULT_TOOL = object()


def _tool(kind: str = "function"):
    return SimpleNamespace(tool_def=SimpleNamespace(kind=kind))


def _manager(*, provider: str = "openai", tools=None):
    return SimpleNamespace(
        ctx=SimpleNamespace(
            usage=SimpleNamespace(tool_calls=0),
            model=SimpleNamespace(
                provider=SimpleNamespace(name=provider),
            ),
        ),
        tools=tools or {"safe": _tool()},
        succeeded_tools=set(),
    )


def _call(name="safe", args='{"value":1}', provider="openai"):
    return SimpleNamespace(
        tool_name=name,
        args=args,
        provider_name=provider,
    )


def _validated(call, *, tool=_DEFAULT_TOOL, **overrides):
    values = {
        "call": call,
        "tool": _tool() if tool is _DEFAULT_TOOL else tool,
        "ctx": SimpleNamespace(),
        "args_valid": True,
        "validated_args": {"value": 1},
        "validation_error": None,
        "deferral": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _install_callback_patch(monkeypatch, execute, validate=None):
    if validate is None:

        async def validate(self, call, **kwargs):
            _ = self, kwargs
            return call

    def get_tool_def(self, name):
        tool = (self.tools or {}).get(name)
        return None if tool is None else tool.tool_def

    monkeypatch.setattr(ToolManager, "execute_tool_call", execute)
    monkeypatch.setattr(ToolManager, "validate_tool_call", validate)
    monkeypatch.setattr(ToolManager, "get_tool_def", get_tool_def)
    assert patch_tool_call_callbacks() is True


@pytest.mark.asyncio
async def test_block_is_fail_closed_and_balances_lifecycle(monkeypatch):
    executed = []
    lifecycle = []
    final_calls = []

    async def execute(self, validated, **kwargs):
        _ = self, kwargs
        executed.append(validated)
        return "executed"

    def started(tool_name, tool_args, context=None):
        _ = tool_name, tool_args, context
        lifecycle.append("started")

    def blocker(tool_name, tool_args, context=None):
        _ = tool_name, tool_args, context
        return {"blocked": True, "reason": object()}

    def finished(tool_name, tool_args, result, duration_ms, context=None):
        _ = tool_name, tool_args, duration_ms, context
        lifecycle.append(result.copy())

    def final(*args, **kwargs):
        final_calls.append((args, kwargs))

    callbacks.clear_callbacks("pre_tool_call")
    callbacks.clear_callbacks("post_tool_call")
    callbacks.clear_callbacks("final_tool_result")
    callbacks.register_callback("pre_tool_call", started)
    callbacks.register_callback("pre_tool_call", blocker)
    callbacks.register_callback("post_tool_call", finished)
    callbacks.register_callback("final_tool_result", final)
    monkeypatch.setattr(
        "code_puppy.messaging.emit_warning",
        lambda message: (_ for _ in ()).throw(RuntimeError(message)),
    )
    _install_callback_patch(monkeypatch, execute)

    manager = _manager()
    call = _call()
    result = await ToolManager.execute_tool_call(manager, _validated(call))

    assert "ERROR: Hook blocked" in result
    assert executed == []
    assert lifecycle[0] == "started"
    assert lifecycle[1]["blocked"] is True
    assert manager.ctx.usage.tool_calls == 1
    assert manager.succeeded_tools == {"safe"}
    assert final_calls == []

    raw_manager = _manager()
    raw_result = await ToolManager.execute_tool_call(
        raw_manager,
        _validated(_call()),
        wrap_validation_errors=False,
    )
    assert "ERROR: Hook blocked" in raw_result
    assert raw_manager.ctx.usage.tool_calls == 1
    assert raw_manager.succeeded_tools == set()


@pytest.mark.asyncio
async def test_non_executable_states_delegate_without_callbacks(monkeypatch):
    delegated = []
    callback_calls = []

    async def execute(self, validated, **kwargs):
        _ = self, kwargs
        delegated.append(validated)
        raise validated.expected

    def callback(*args, **kwargs):
        callback_calls.append((args, kwargs))

    callbacks.clear_callbacks("pre_tool_call")
    callbacks.clear_callbacks("post_tool_call")
    callbacks.clear_callbacks("final_tool_result")
    callbacks.register_callback("pre_tool_call", callback)
    callbacks.register_callback("post_tool_call", callback)
    callbacks.register_callback("final_tool_result", callback)
    _install_callback_patch(monkeypatch, execute)

    cases = [
        {"deferral": RuntimeError("deferred")},
        {
            "args_valid": False,
            "validated_args": None,
            "validation_error": RuntimeError("invalid"),
        },
        {"tool": None, "validated_args": None},
        {"tool": _tool("external")},
    ]
    for case in cases:
        expected = next(
            (value for value in case.values() if isinstance(value, Exception)),
            RuntimeError("delegated"),
        )
        validated = _validated(_call(), expected=expected, **case)
        with pytest.raises(RuntimeError) as caught:
            await ToolManager.execute_tool_call(_manager(), validated)
        assert caught.value is expected

    manager_without_context = _manager()
    manager_without_context.ctx = None
    expected = RuntimeError("missing context")
    validated = _validated(_call(), expected=expected)
    with pytest.raises(RuntimeError) as caught:
        await ToolManager.execute_tool_call(manager_without_context, validated)
    assert caught.value is expected

    assert len(delegated) == len(cases) + 1
    assert callback_calls == []


@pytest.mark.asyncio
async def test_normalization_uses_call_provider_and_exact_tool_lookup(monkeypatch):
    observed = []

    async def execute(self, validated, **kwargs):
        _ = self, kwargs
        return validated

    async def validate(self, call, **kwargs):
        _ = self, kwargs
        observed.append(call.tool_name)
        return call

    _install_callback_patch(monkeypatch, execute, validate)

    tools = {"safe": _tool(), "cp_legit": _tool()}
    claude = _manager(provider="openai", tools=tools)
    await ToolManager.validate_tool_call(
        claude, _call("cp_safe", provider="claude_code")
    )
    await ToolManager.validate_tool_call(claude, _call("cp_safe", provider="openai"))
    await ToolManager.validate_tool_call(
        claude, _call("cp_legit", provider="claude_code")
    )
    fallback = _manager(provider="claude_code", tools=tools)
    await ToolManager.validate_tool_call(fallback, _call("cp_safe", provider=None))

    assert observed == ["safe", "cp_safe", "cp_legit", "safe"]
    exact = ToolManager.get_tool_def(claude, "cp_legit")
    assert exact is tools["cp_legit"].tool_def


@pytest.mark.asyncio
async def test_noop_preserves_raw_bytes_and_typed_mutation_stays_consistent(
    monkeypatch,
):
    executions = []

    async def execute(self, validated, **kwargs):
        _ = self, kwargs
        executions.append((validated.call.args, validated.validated_args.copy()))
        return "ok"

    callbacks.clear_callbacks("pre_tool_call")
    callbacks.clear_callbacks("post_tool_call")
    callbacks.clear_callbacks("final_tool_result")
    _install_callback_patch(monkeypatch, execute)
    manager = _manager()
    raw = '{ "path": "/tmp/café", "count": 1, "nested": {"x": 1} }'

    def noop(*args, **kwargs):
        _ = args, kwargs

    callbacks.register_callback("pre_tool_call", noop)
    call = _call(args=raw)
    validated = _validated(
        call,
        validated_args={
            "path": Path("/tmp/café"),
            "count": 1,
            "nested": {"x": 1},
        },
    )
    await ToolManager.execute_tool_call(manager, validated)
    assert executions[-1][0] == raw

    callbacks.unregister_callback("pre_tool_call", noop)

    def mutate(tool_name, tool_args, context=None):
        _ = tool_name, context
        tool_args["count"] = 2
        tool_args["nested"]["x"] = 3

    callbacks.register_callback("pre_tool_call", mutate)
    call = _call(args=raw)
    validated = _validated(
        call,
        validated_args={
            "path": Path("/tmp/café"),
            "count": 1,
            "nested": {"x": 1},
        },
    )
    await ToolManager.execute_tool_call(manager, validated)

    history = json.loads(executions[-1][0])
    assert history == {"path": "/tmp/café", "count": 2, "nested": {"x": 3}}
    assert executions[-1][1]["path"] == Path("/tmp/café")
    assert executions[-1][1]["count"] == 2
    assert executions[-1][1]["nested"] == {"x": 3}


@pytest.mark.asyncio
async def test_unserializable_hook_mutation_blocks_instead_of_diverging(monkeypatch):
    executions = []
    post_results = []

    async def execute(self, validated, **kwargs):
        _ = self, kwargs
        executions.append(validated)
        return "should not run"

    def mutate(tool_name, tool_args, context=None):
        _ = tool_name, context
        tool_args["value"] = object()

    def observe(tool_name, tool_args, result, duration_ms, context=None):
        _ = tool_name, tool_args, duration_ms, context
        post_results.append(result.copy())

    callbacks.clear_callbacks("pre_tool_call")
    callbacks.clear_callbacks("post_tool_call")
    callbacks.clear_callbacks("final_tool_result")
    callbacks.register_callback("pre_tool_call", mutate)
    callbacks.register_callback("post_tool_call", observe)
    _install_callback_patch(monkeypatch, execute)

    result = await ToolManager.execute_tool_call(
        _manager(),
        _validated(_call()),
    )

    assert "cannot be serialized safely" in result
    assert executions == []
    assert post_results[0]["blocked"] is True


@pytest.mark.asyncio
async def test_json_repair_preserves_valid_bytes_and_rejects_non_object_repair(
    monkeypatch,
):
    observed = []

    async def validate(self, call, **kwargs):
        _ = self, kwargs
        observed.append(call.args)
        return call

    monkeypatch.setattr(ToolManager, "validate_tool_call", validate)
    assert patch_tool_call_json_repair() is True
    manager = _manager()
    valid = '{ "text": "café", "value": 1 }'
    invalid = '{"value":1,}'
    unrecoverable = "definitely not a JSON object"

    await ToolManager.validate_tool_call(manager, _call(args=valid))
    await ToolManager.validate_tool_call(manager, _call(args=invalid))
    await ToolManager.validate_tool_call(manager, _call(args=unrecoverable))

    assert observed[0] == valid
    assert json.loads(observed[1]) == {"value": 1}
    assert observed[2] == unrecoverable
