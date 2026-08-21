"""Contract tests for the ``ToolCallJsonRepair`` capability.

Covers the promotion of ``patch_tool_call_json_repair`` (an eager
``ToolManager.validate_tool_call`` monkeypatch) onto pydantic-ai's
``before_tool_validate`` capability seam:

* direct-seam semantics (repair, custody via ``call.args``, pass-throughs,
  swallowed repair failures, optional-dependency fallback);
* end-to-end ``Agent.run()`` proof that the tool executes with repaired
  args AND the recorded history carries the repaired JSON (byte parity
  with the patch's in-place mutation);
* the explicit-when-ours / fallback-for-guests split: the patch steps
  aside when the run's capability tree contains ``ToolCallJsonRepair``,
  and keeps repairing for raw guest agents;
* the documented bounded divergence: unknown-tool calls keep their raw
  (unrepaired) args in history, failing identically either way;
* construction-site wiring at both ``capabilities=[...]`` blocks.
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.tools import ToolDefinition

from code_puppy.agents import _json_repair as json_repair_module
from code_puppy.agents._json_repair import (
    ToolCallJsonRepair,
    build_tool_call_json_repair,
)

BROKEN_ARGS = '{"x": 1,}'  # trailing comma — json_repair's bread and butter
REPAIRED_ARGS = '{"x": 1}'


def _tool_def(name: str = "grab") -> ToolDefinition:
    return ToolDefinition(name=name)


def _call(args: Any, name: str = "grab") -> ToolCallPart:
    return ToolCallPart(tool_name=name, args=args)


async def _invoke_seam(call: ToolCallPart, args: Any) -> Any:
    """Drive before_tool_validate exactly as _run_validate_hooks does."""
    cap = ToolCallJsonRepair()
    return await cap.before_tool_validate(
        None,  # RunContext unused by the hook
        call=call,
        tool_def=_tool_def(call.tool_name),
        args=args,
    )


def _tool_call_args_in(messages: list[ModelMessage]) -> list[Any]:
    return [
        part.args
        for message in messages
        for part in message.parts
        if isinstance(part, ToolCallPart)
    ]


def _broken_then_done_model() -> FunctionModel:
    """First response: tool call with broken JSON args. Then: plain text."""

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if len(messages) == 1:
            return ModelResponse(
                parts=[ToolCallPart(tool_name="grab", args=BROKEN_ARGS)]
            )
        return ModelResponse(parts=[TextPart("done")])

    return FunctionModel(fn)


def _register_grab(agent: Agent, seen: list[int]) -> None:
    @agent.tool_plain
    def grab(x: int) -> str:
        seen.append(x)
        return "ok"


@pytest.fixture
def restore_validate_tool_call():
    """Snapshot/restore ToolManager.validate_tool_call around patch tests.

    The patch mutates the class process-globally; without this, one test's
    patch application leaks into every later test in the session.
    """
    from pydantic_ai.tool_manager import ToolManager

    original = ToolManager.validate_tool_call
    yield
    ToolManager.validate_tool_call = original


# ---------------------------------------------------------------------------
# Direct seam semantics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_broken_string_args_are_repaired_and_mirrored():
    call = _call(BROKEN_ARGS)
    result = await _invoke_seam(call, BROKEN_ARGS)
    assert result == REPAIRED_ARGS
    # Custody: the live ToolCallPart (recorded in run state) carries the
    # repaired bytes — exactly the patch's in-place mutation.
    assert call.args == REPAIRED_ARGS


@pytest.mark.asyncio
async def test_valid_json_args_pass_through_untouched():
    call = _call(REPAIRED_ARGS)
    result = await _invoke_seam(call, REPAIRED_ARGS)
    assert result is REPAIRED_ARGS  # same object, no re-serialization
    assert call.args == REPAIRED_ARGS


@pytest.mark.asyncio
async def test_dict_args_pass_through_untouched():
    args = {"x": 1}
    call = _call(args)
    result = await _invoke_seam(call, args)
    assert result is args
    assert call.args is args


@pytest.mark.asyncio
async def test_empty_string_args_pass_through():
    # Patch parity: the eager patch guarded `call.args` truthiness too.
    call = _call("")
    result = await _invoke_seam(call, "")
    assert result == ""
    assert call.args == ""


@pytest.mark.asyncio
async def test_repair_failure_is_swallowed(monkeypatch):
    def explode(_args: str) -> str:
        raise RuntimeError("repair go boom")

    monkeypatch.setattr(json_repair_module.json_repair, "repair_json", explode)
    call = _call(BROKEN_ARGS)
    result = await _invoke_seam(call, BROKEN_ARGS)
    # Original args proceed to validation; the model earns its retry.
    assert result == BROKEN_ARGS
    assert call.args == BROKEN_ARGS


@pytest.mark.asyncio
async def test_missing_json_repair_dependency_noops(monkeypatch):
    monkeypatch.setattr(json_repair_module, "json_repair", None)
    call = _call(BROKEN_ARGS)
    result = await _invoke_seam(call, BROKEN_ARGS)
    assert result == BROKEN_ARGS
    assert call.args == BROKEN_ARGS


def test_builder_skips_capability_without_dependency(monkeypatch):
    monkeypatch.setattr(json_repair_module, "json_repair", None)
    assert build_tool_call_json_repair() == []


def test_builder_returns_single_capability():
    caps = build_tool_call_json_repair()
    assert len(caps) == 1
    assert isinstance(caps[0], ToolCallJsonRepair)


# ---------------------------------------------------------------------------
# End-to-end runs through the real capability chain
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_executes_tool_with_repaired_args_and_records_them():
    seen: list[int] = []
    agent = Agent(model=_broken_then_done_model(), capabilities=[ToolCallJsonRepair()])
    _register_grab(agent, seen)

    result = await agent.run("go")

    assert seen == [1]  # tool ran with the repaired payload — no retry burned
    assert result.output == "done"
    assert _tool_call_args_in(result.all_messages()) == [REPAIRED_ARGS]


@pytest.mark.asyncio
async def test_wire_parity_with_eager_patch(restore_validate_tool_call):
    """A guest agent under the patch and an agent under the capability
    produce identical recorded tool-call args and identical output."""
    from code_puppy.pydantic_patches import patch_tool_call_json_repair

    seen_cap: list[int] = []
    cap_agent = Agent(
        model=_broken_then_done_model(), capabilities=[ToolCallJsonRepair()]
    )
    _register_grab(cap_agent, seen_cap)
    cap_result = await cap_agent.run("go")

    assert patch_tool_call_json_repair()
    seen_patch: list[int] = []
    guest_agent = Agent(model=_broken_then_done_model())
    _register_grab(guest_agent, seen_patch)
    patch_result = await guest_agent.run("go")

    assert seen_cap == seen_patch == [1]
    assert cap_result.output == patch_result.output == "done"
    assert (
        _tool_call_args_in(cap_result.all_messages())
        == _tool_call_args_in(patch_result.all_messages())
        == [REPAIRED_ARGS]
    )


def _unknown_tool_model() -> FunctionModel:
    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if len(messages) == 1:
            return ModelResponse(
                parts=[ToolCallPart(tool_name="not_a_tool", args=BROKEN_ARGS)]
            )
        return ModelResponse(parts=[TextPart("recovered")])

    return FunctionModel(fn)


def _retry_prompt_contents(messages: list[ModelMessage]) -> list[Any]:
    return [
        part.content
        for message in messages
        for part in message.parts
        if isinstance(part, RetryPromptPart)
    ]


@pytest.mark.asyncio
async def test_unknown_tool_args_stay_raw_in_history():
    """Documented bounded divergence: resolution fails before the seam
    fires, so an unknown tool's recorded args keep the model's raw bytes.
    (Unavailable tools share the same code path — ``_resolve_tool`` raises
    before ``_run_validate_hooks`` runs any hook.)"""
    seen: list[int] = []
    agent = Agent(model=_unknown_tool_model(), capabilities=[ToolCallJsonRepair()])
    _register_grab(agent, seen)

    result = await agent.run("go")

    assert result.output == "recovered"
    assert seen == []
    assert _tool_call_args_in(result.all_messages()) == [BROKEN_ARGS]


@pytest.mark.asyncio
async def test_unknown_tool_retry_parity_with_eager_patch(restore_validate_tool_call):
    """The divergence is history bytes ONLY: the unknown-tool call earns
    the identical ModelRetry prompt and recovery under the eager patch and
    under the capability."""
    from code_puppy.pydantic_patches import patch_tool_call_json_repair

    cap_agent = Agent(model=_unknown_tool_model(), capabilities=[ToolCallJsonRepair()])
    _register_grab(cap_agent, [])
    cap_result = await cap_agent.run("go")

    assert patch_tool_call_json_repair()
    guest_agent = Agent(model=_unknown_tool_model())
    _register_grab(guest_agent, [])
    patch_result = await guest_agent.run("go")

    assert cap_result.output == patch_result.output == "recovered"
    # Identical retry feedback to the model on both paths.
    cap_retries = _retry_prompt_contents(cap_result.all_messages())
    patch_retries = _retry_prompt_contents(patch_result.all_messages())
    assert cap_retries == patch_retries
    assert len(cap_retries) == 1
    # The old patch repaired even a doomed call's recorded args; the
    # capability leaves them raw. This is the entire divergence.
    assert _tool_call_args_in(cap_result.all_messages()) == [BROKEN_ARGS]
    assert _tool_call_args_in(patch_result.all_messages()) == [REPAIRED_ARGS]


# ---------------------------------------------------------------------------
# Patch gating: explicit-when-ours, fallback-for-guests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_steps_aside_when_capability_present(
    monkeypatch, restore_validate_tool_call
):
    import json_repair as json_repair_lib

    from code_puppy.pydantic_patches import patch_tool_call_json_repair

    calls = {"n": 0}
    real_repair = json_repair_lib.repair_json

    def counting(args: str, *a: Any, **k: Any) -> str:
        calls["n"] += 1
        return real_repair(args, *a, **k)

    # Both the patch and the capability resolve repair_json at call time
    # through their own module handles; patch both.
    monkeypatch.setattr(json_repair_lib, "repair_json", counting)
    monkeypatch.setattr(json_repair_module.json_repair, "repair_json", counting)

    assert patch_tool_call_json_repair()

    seen: list[int] = []
    agent = Agent(model=_broken_then_done_model(), capabilities=[ToolCallJsonRepair()])
    _register_grab(agent, seen)
    result = await agent.run("go")

    assert seen == [1]
    assert result.output == "done"
    # Exactly one repair: the capability's. The gated patch never ran its own.
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_patch_still_repairs_for_guest_agents(restore_validate_tool_call):
    from code_puppy.pydantic_patches import patch_tool_call_json_repair

    assert patch_tool_call_json_repair()

    seen: list[int] = []
    guest = Agent(model=_broken_then_done_model())
    _register_grab(guest, seen)
    result = await guest.run("go")

    assert seen == [1]
    assert _tool_call_args_in(result.all_messages()) == [REPAIRED_ARGS]


def test_run_owns_json_repair_walks_capability_leaves():
    from code_puppy.pydantic_patches import _run_owns_json_repair

    class FakeToolManager:
        def __init__(self, root: Any) -> None:
            self.root_capability = root

    assert not _run_owns_json_repair(FakeToolManager(None))
    assert _run_owns_json_repair(FakeToolManager(ToolCallJsonRepair()))

    # Nested inside a combined tree (the shape a real run produces).
    from pydantic_ai.capabilities import CombinedCapability, ProcessHistory

    combined = CombinedCapability(
        [
            ProcessHistory(lambda ctx, messages: messages),
            ToolCallJsonRepair(),
        ]
    )
    assert _run_owns_json_repair(FakeToolManager(combined))

    without = CombinedCapability([ProcessHistory(lambda ctx, messages: messages)])
    assert not _run_owns_json_repair(FakeToolManager(without))


# ---------------------------------------------------------------------------
# Construction-site wiring
# ---------------------------------------------------------------------------


def test_builder_splices_capability_into_main_agent():
    from code_puppy.agents import _builder

    source = inspect.getsource(_builder)
    assert "*build_tool_call_json_repair()," in source


def test_subagent_invocation_splices_capability():
    from code_puppy.tools import subagent_invocation

    source = inspect.getsource(subagent_invocation)
    assert "*build_tool_call_json_repair()," in source


def test_before_tool_validate_signature_matches_seam():
    """Pin the seam signature so a pydantic-ai upgrade that changes the
    hook contract fails loudly here instead of silently never firing.

    Compares names, kinds, and defaults — not annotations, which
    legitimately differ (the seam spells ``RawToolArgs``, we spell the
    underlying union)."""
    from pydantic_ai.capabilities import AbstractCapability

    base = inspect.signature(AbstractCapability.before_tool_validate)
    ours = inspect.signature(ToolCallJsonRepair.before_tool_validate)
    base_shape = [(p.name, p.kind, p.default) for p in base.parameters.values()]
    ours_shape = [(p.name, p.kind, p.default) for p in ours.parameters.values()]
    assert base_shape == ours_shape
