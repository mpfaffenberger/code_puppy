"""A cancellation absorbed by a pre-tool callback must not let the tool run.

pydantic-ai runs each tool call in its own task and re-asserts a pending
cancel only after the step finishes. These tests pin the re-check that
``_patched_execute_tool_call`` performs right after the ``pre_tool_call``
callbacks return and before anything else is honored or executed.
"""

import asyncio
from types import SimpleNamespace

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.tool_manager import ToolManager

from code_puppy import _pydantic_tool_helpers as helpers
from code_puppy import callbacks, pydantic_patches

BLOCK_RESULT = {"blocked": True, "reason": "policy says no"}


def _snapshot_tool_manager(monkeypatch):
    """Record every method the patch replaces so monkeypatch restores them."""
    for name in (
        "execute_tool_call",
        "get_tool_def",
        "validate_tool_call",
        "validate_output_tool_call",
    ):
        monkeypatch.setattr(ToolManager, name, getattr(ToolManager, name))


def _absorbing_callback(entered: asyncio.Event, results: list | None = None):
    """A pre_tool_call callback that swallows the cancel delivered mid-scan."""

    async def on_pre_tool_call(tool_name, tool_args, context=None):
        entered.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            pass
        return results or []

    return on_pre_tool_call


def _immediate_callback(results: list | None = None):
    async def on_pre_tool_call(tool_name, tool_args, context=None):
        return results or []

    return on_pre_tool_call


@pytest.fixture
def executed(monkeypatch):
    """Patch ToolManager around a stub tool; the list records each execution."""
    runs: list = []

    async def original_execute(_manager, validated, **_kwargs):
        runs.append(validated)
        return "tool result"

    _snapshot_tool_manager(monkeypatch)
    monkeypatch.setattr(ToolManager, "execute_tool_call", original_execute)
    assert pydantic_patches.patch_tool_call_callbacks() is True
    return runs


@pytest.fixture
def post_calls(monkeypatch):
    recorded: list = []

    async def on_post_tool_call(*args, **kwargs):
        recorded.append(args)
        return []

    monkeypatch.setattr(callbacks, "on_post_tool_call", on_post_tool_call)
    monkeypatch.setattr("code_puppy.messaging.emit_warning", lambda *_a, **_k: None)
    return recorded


def _call_patched_execute():
    manager = SimpleNamespace(tools={})
    call = SimpleNamespace(
        tool_name="write_file", args={"file_path": "a.py"}, tool_call_id="call-123"
    )
    validated = SimpleNamespace(call=call, validated_args={"file_path": "a.py"})
    return ToolManager.execute_tool_call(manager, validated)


async def _cancel_while_scanning(entered: asyncio.Event):
    tool_task = asyncio.create_task(_call_patched_execute())
    await entered.wait()
    tool_task.cancel()
    return tool_task


async def test_absorbed_cancel_stops_the_tool_before_it_executes(
    executed, post_calls, monkeypatch
):
    entered = asyncio.Event()
    monkeypatch.setattr(callbacks, "on_pre_tool_call", _absorbing_callback(entered))

    tool_task = await _cancel_while_scanning(entered)
    with pytest.raises(asyncio.CancelledError):
        await tool_task

    assert tool_task.cancelled()
    assert executed == []
    assert len(post_calls) == 1
    assert post_calls[0][2]["cancelled"] is True
    assert post_calls[0][4]["outcome"] == "cancelled"
    assert post_calls[0][4]["exception_type"] == "CancelledError"
    assert post_calls[0][4]["execution_started"] is False
    assert post_calls[0][4]["tool_call_id"] == "call-123"


async def test_absorbed_cancel_wins_over_a_block_result(
    executed, post_calls, monkeypatch
):
    entered = asyncio.Event()
    monkeypatch.setattr(
        callbacks, "on_pre_tool_call", _absorbing_callback(entered, [BLOCK_RESULT])
    )

    tool_task = await _cancel_while_scanning(entered)
    with pytest.raises(asyncio.CancelledError):
        await tool_task

    assert executed == []
    assert len(post_calls) == 1
    assert post_calls[0][4]["outcome"] == "cancelled"


async def test_without_a_cancel_the_tool_runs_and_returns_its_result(
    executed, post_calls, monkeypatch
):
    monkeypatch.setattr(callbacks, "on_pre_tool_call", _immediate_callback())

    result = await _call_patched_execute()

    assert result == "tool result"
    assert len(executed) == 1
    assert len(post_calls) == 1
    assert post_calls[0][4]["outcome"] == "ok"
    assert post_calls[0][4]["execution_started"] is True


async def test_without_a_cancel_a_block_result_still_blocks(
    executed, post_calls, monkeypatch
):
    monkeypatch.setattr(
        callbacks, "on_pre_tool_call", _immediate_callback([BLOCK_RESULT])
    )

    result = await _call_patched_execute()

    assert "Hook blocked this tool call" in result
    assert "policy says no" in result
    assert executed == []
    assert len(post_calls) == 1
    assert post_calls[0][4]["outcome"] == "blocked"
    assert post_calls[0][4]["execution_started"] is False
    assert post_calls[0][2] == {"blocked": True, "error": result}


async def test_execution_phase_cancel_is_reported_then_reraised(
    monkeypatch, post_calls
):
    entered = asyncio.Event()

    async def cancelling_execute(_manager, _validated, **_kwargs):
        entered.set()
        await asyncio.sleep(30)

    _snapshot_tool_manager(monkeypatch)
    monkeypatch.setattr(ToolManager, "execute_tool_call", cancelling_execute)
    assert pydantic_patches.patch_tool_call_callbacks() is True
    monkeypatch.setattr(callbacks, "on_pre_tool_call", _immediate_callback())

    task = asyncio.create_task(_call_patched_execute())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(post_calls) == 1
    assert post_calls[0][4]["outcome"] == "cancelled"
    assert post_calls[0][4]["exception_type"] == "CancelledError"
    assert post_calls[0][4]["execution_started"] is True
    assert post_calls[0][2] == {
        "cancelled": True,
        "error": "Tool call cancelled",
    }


async def test_base_exception_is_reported_as_error(monkeypatch, post_calls):
    async def interrupted(_manager, _validated, **_kwargs):
        raise KeyboardInterrupt("stop")

    _snapshot_tool_manager(monkeypatch)
    monkeypatch.setattr(ToolManager, "execute_tool_call", interrupted)
    assert pydantic_patches.patch_tool_call_callbacks() is True
    monkeypatch.setattr(callbacks, "on_pre_tool_call", _immediate_callback())

    with pytest.raises(KeyboardInterrupt, match="stop"):
        await _call_patched_execute()

    assert post_calls[0][4]["outcome"] == "error"
    assert post_calls[0][4]["exception_type"] == "KeyboardInterrupt"


async def test_cancel_during_blocked_terminal_dispatch_does_not_dispatch_twice(
    executed, monkeypatch
):
    entered = asyncio.Event()
    outcomes = []

    async def slow_terminal(*args):
        outcomes.append(args[4]["outcome"])
        entered.set()
        await asyncio.sleep(30)

    monkeypatch.setattr(
        callbacks, "on_pre_tool_call", _immediate_callback([BLOCK_RESULT])
    )
    monkeypatch.setattr(callbacks, "on_post_tool_call", slow_terminal)
    task = asyncio.create_task(_call_patched_execute())
    await entered.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert executed == []
    assert outcomes == ["blocked"]


async def test_cancel_during_ok_terminal_dispatch_propagates(executed, monkeypatch):
    entered = asyncio.Event()
    outcomes = []

    async def slow_terminal(*args):
        outcomes.append(args[4]["outcome"])
        entered.set()
        await asyncio.sleep(30)

    monkeypatch.setattr(callbacks, "on_pre_tool_call", _immediate_callback())
    monkeypatch.setattr(callbacks, "on_post_tool_call", slow_terminal)
    task = asyncio.create_task(_call_patched_execute())
    await entered.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(executed) == 1
    assert outcomes == ["ok"]


async def test_real_agent_run_never_executes_the_tool_after_an_absorbed_cancel(
    monkeypatch,
):
    _snapshot_tool_manager(monkeypatch)
    assert pydantic_patches.patch_tool_call_callbacks() is True
    entered = asyncio.Event()
    monkeypatch.setattr(callbacks, "on_pre_tool_call", _absorbing_callback(entered))
    ran: list[str] = []

    def model_fn(messages, _info):
        if len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart("side_effect", {})])
        return ModelResponse(parts=[TextPart("done")])

    agent = Agent(FunctionModel(model_fn))

    @agent.tool_plain
    async def side_effect() -> str:
        ran.append("executed")
        return "ok"

    run_task = asyncio.create_task(agent.run("go"))
    await entered.wait()
    run_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await run_task

    assert ran == []


def test_helper_is_a_noop_outside_an_event_loop():
    helpers._raise_if_cancel_pending()


async def test_helper_is_a_noop_without_a_pending_cancel():
    helpers._raise_if_cancel_pending()


async def test_helper_reasserts_a_cancel_the_task_absorbed():
    entered = asyncio.Event()

    async def absorb_then_check():
        entered.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            pass
        helpers._raise_if_cancel_pending()
        return "completed"

    task = asyncio.create_task(absorb_then_check())
    await entered.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


async def test_helper_leaves_the_cancel_count_for_outer_layers():
    entered = asyncio.Event()

    async def absorb_check_and_report():
        entered.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            pass
        try:
            helpers._raise_if_cancel_pending()
        except asyncio.CancelledError:
            return asyncio.current_task().cancelling()
        return -1

    task = asyncio.create_task(absorb_check_and_report())
    await entered.wait()
    task.cancel()

    assert await task == 1


async def test_helper_ignores_a_cancel_that_was_properly_balanced():
    entered = asyncio.Event()

    async def handle_then_check():
        entered.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            asyncio.current_task().uncancel()
        helpers._raise_if_cancel_pending()
        return "completed"

    task = asyncio.create_task(handle_then_check())
    await entered.wait()
    task.cancel()

    assert await task == "completed"
