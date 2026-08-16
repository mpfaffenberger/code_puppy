"""Regression tests for JSON repair before pre-tool policy callbacks."""

from __future__ import annotations

import pytest
from pydantic_ai import Agent
from pydantic_ai._tool_manager import ToolManager
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from code_puppy import callbacks
from code_puppy.pydantic_patches import (
    patch_tool_call_callbacks,
    patch_tool_call_json_repair,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked", [False, True])
async def test_repair_precedes_hook_inspection_writeback_and_blocking(blocked):
    observed = {}
    executed = []

    def model_function(messages, info):
        _ = info
        returns = [
            part
            for message in messages
            for part in message.parts
            if isinstance(part, ToolReturnPart)
        ]
        if not returns:
            return ModelResponse(
                parts=[ToolCallPart("echo_tool", '{"command":"safe",}')]
            )
        observed["response"] = returns[-1].model_response_str()
        return ModelResponse(parts=[TextPart("done")])

    def policy_hook(tool_name, tool_args, context=None):
        _ = tool_name, context
        observed["hook_args"] = tool_args.copy()
        if blocked:
            return {"blocked": True, "reason": "policy denied repaired command"}
        tool_args["command"] = "mutated"
        return None

    original_call_tool = ToolManager._call_tool
    original_get_tool_def = ToolManager.get_tool_def
    original_handle_call = ToolManager.handle_call
    callbacks.register_callback("pre_tool_call", policy_hook)
    patch_tool_call_json_repair()
    patch_tool_call_callbacks()
    try:
        agent = Agent(FunctionModel(model_function))

        @agent.tool_plain
        def echo_tool(command: str) -> str:
            executed.append(command)
            return command

        run_result = await agent.run("go")
    finally:
        ToolManager._call_tool = original_call_tool
        ToolManager.get_tool_def = original_get_tool_def
        ToolManager.handle_call = original_handle_call
        callbacks.unregister_callback("pre_tool_call", policy_hook)

    assert run_result.output == "done"
    assert observed["hook_args"] == {"command": "safe"}
    if blocked:
        assert executed == []
        assert "policy denied repaired command" in observed["response"]
    else:
        assert executed == ["mutated"]
        assert "mutated" in observed["response"]
