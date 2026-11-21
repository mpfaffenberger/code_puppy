"""Actual ToolManager supplies stable identity to both mutable callback phases."""

import asyncio

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.tool_manager import ToolManager

from code_puppy import callbacks, pydantic_patches
from code_puppy.tool_identity import current_tool_identity


@pytest.mark.parametrize("case", ["ok", "exception", "cancelled"])
async def test_real_runtime_identity_is_authoritative(monkeypatch, case):
    monkeypatch.setattr(
        callbacks, "_callbacks", {key: [] for key in callbacks._callbacks}
    )
    originals = {
        "execute_tool_call": "_original_execute_tool_call",
        "get_tool_def": "_original_get_tool_def",
        "validate_tool_call": "_original_validate_tool_call",
        "validate_output_tool_call": "_original_validate_output_tool_call",
    }
    for name, original in originals.items():
        method = getattr(ToolManager, name)
        while getattr(method, "__closure__", None):
            cells = dict(
                zip(
                    method.__code__.co_freevars,
                    (cell.cell_contents for cell in method.__closure__),
                )
            )
            if original not in cells:
                break
            method = cells[original]
        monkeypatch.setattr(ToolManager, name, method)
    assert pydantic_patches.patch_tool_call_callbacks()
    seen = []

    def mutate(name, args, context):
        context["tool_call_id"] = "mutated"
        args["command"] = "changed"

    def pre(*args):
        seen.append(("pre", current_tool_identity().tool_call_id))

    def post(*args):
        seen.append(("post", current_tool_identity().tool_call_id))

    callbacks.register_callback("pre_tool_call", mutate)
    callbacks.register_callback("pre_tool_call", pre)
    callbacks.register_callback("post_tool_call", post)
    entered = asyncio.Event()

    async def operation(command: str):
        assert command == "changed"
        if case == "exception":
            raise ValueError("synthetic error")
        if case == "cancelled":
            entered.set()
            await asyncio.Event().wait()
        return "safe result"

    def model(messages, info):
        if len(messages) == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "operation",
                        {"command": "original"},
                        tool_call_id="authoritative",
                    )
                ]
            )
        return ModelResponse(parts=[TextPart("done")])

    task = asyncio.create_task(
        Agent(FunctionModel(model), tools=[operation]).run("run")
    )
    if case == "cancelled":
        await asyncio.wait_for(entered.wait(), 5)
        task.cancel("original cancellation")
        with pytest.raises(asyncio.CancelledError, match="original cancellation"):
            await task
    elif case == "exception":
        with pytest.raises(ValueError, match="synthetic error"):
            await task
    else:
        await task
    assert seen == [("pre", "authoritative"), ("post", "authoritative")]
    assert current_tool_identity() is None
