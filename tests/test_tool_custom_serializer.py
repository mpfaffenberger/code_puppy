"""Tool callback compatibility with annotation-level Pydantic serializers."""

from __future__ import annotations

from typing import Annotated

import pytest
from pydantic import PlainSerializer, PlainValidator, WithJsonSchema
from pydantic_ai import Agent
from pydantic_ai._agent_graph import CallToolsNode
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.tool_manager import ToolManager

from code_puppy import callbacks
from code_puppy.tool_call_patches import patch_tool_call_callbacks


def _validate_range(value):
    if type(value) is range:
        return value
    return range(*value)


RangeArgument = Annotated[
    range,
    PlainValidator(_validate_range),
    PlainSerializer(lambda value: [value.start, value.stop, value.step]),
    WithJsonSchema({"type": "array", "items": {"type": "integer"}}),
]


@pytest.mark.asyncio
async def test_noop_hooks_do_not_block_schema_serializable_argument():
    executed = []

    def model_function(messages, info):
        _ = info
        returned = any(
            isinstance(part, ToolReturnPart)
            for message in messages
            for part in message.parts
        )
        if returned:
            return ModelResponse(parts=[TextPart("done")])
        return ModelResponse(parts=[ToolCallPart("range_tool", {"value": [1, 4]})])

    originals = (
        ToolManager.execute_tool_call,
        ToolManager.get_tool_def,
        ToolManager.validate_tool_call,
        ToolManager.validate_output_tool_call,
        CallToolsNode._handle_tool_calls,
    )
    callbacks.clear_callbacks("pre_tool_call")
    callbacks.clear_callbacks("post_tool_call")
    callbacks.clear_callbacks("final_tool_result")
    patch_tool_call_callbacks()
    try:
        agent = Agent(FunctionModel(model_function))

        @agent.tool_plain
        def range_tool(value: RangeArgument) -> str:
            executed.append(value)
            return "ok"

        result = await agent.run("go")
    finally:
        (
            ToolManager.execute_tool_call,
            ToolManager.get_tool_def,
            ToolManager.validate_tool_call,
            ToolManager.validate_output_tool_call,
            CallToolsNode._handle_tool_calls,
        ) = originals

    assert result.output == "done"
    assert executed == [range(1, 4)]
