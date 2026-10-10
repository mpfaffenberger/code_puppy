"""Native routing preserves multimodal tool content through real agent execution."""

from unittest.mock import Mock

import pytest
from pydantic_ai import Agent, BinaryContent, RunContext, ToolReturn
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.tools import ToolDefinition
from pydantic_ai_harness.code_mode import CodeMode

from code_puppy.agents._code_mode import (
    NATIVE_TOOL_METADATA_KEY,
    _sandbox_tool,
)


@pytest.mark.parametrize("declaration", [True, False, None, "true", 1])
def test_native_metadata_requires_literal_true(declaration):
    definition = ToolDefinition(
        name="future_plugin_capture",
        metadata={NATIVE_TOOL_METADATA_KEY: declaration},
    )
    assert _sandbox_tool(Mock(spec=RunContext), definition) is (declaration is not True)


def test_speculation_declaration_does_not_imply_native_routing():
    definition = ToolDefinition(name="plugin_read", metadata={"speculatable": True})
    assert _sandbox_tool(Mock(spec=RunContext), definition)


@pytest.mark.parametrize(
    "name, metadata",
    [
        ("future_plugin_capture", {NATIVE_TOOL_METADATA_KEY: True}),
        ("computer_screenshot", {}),
    ],
)
async def test_native_image_reaches_next_model_request(name, metadata):
    image = BinaryContent(data=b"image-contract-fixture", media_type="image/png")
    requests = []

    def model(messages, info):
        requests.append(messages)
        if len(requests) == 1:
            names = {tool.name for tool in info.function_tools}
            assert name in names
            assert "run_code" in names
            return ModelResponse(parts=[ToolCallPart(name, {}, tool_call_id="capture")])
        images = [
            item
            for message in messages
            if isinstance(message, ModelRequest)
            for part in message.parts
            if isinstance(part, UserPromptPart) and not isinstance(part.content, str)
            for item in part.content
            if isinstance(item, BinaryContent)
        ]
        assert len(images) == 1
        assert images[0].data == image.data
        assert images[0].media_type == image.media_type
        return ModelResponse(parts=[TextPart("image received")])

    agent = Agent(
        FunctionModel(model),
        capabilities=[CodeMode(tools=_sandbox_tool)],
    )

    def capture() -> ToolReturn:
        return ToolReturn(return_value={"success": True}, content=["capture", image])

    agent.tool_plain(capture, name=name, metadata=metadata)
    result = await agent.run("Capture once")
    assert result.output == "image received"
    assert len(requests) == 2
