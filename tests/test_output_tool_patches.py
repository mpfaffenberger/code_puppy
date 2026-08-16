"""Integration contracts for output-tool normalization and JSON repair."""

from __future__ import annotations

import json

import pytest
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.tool_manager import ToolManager

from code_puppy.tool_call_patches import (
    patch_tool_call_callbacks,
    patch_tool_call_json_repair,
)


class _FinalOutput(BaseModel):
    answer: str


@pytest.mark.asyncio
async def test_claude_prefixed_malformed_output_tool_reaches_final_validation():
    observed = {}

    def model_function(messages, info):
        _ = messages
        output_name = info.output_tools[0].name
        observed["output_name"] = output_name
        return ModelResponse(
            parts=[
                ToolCallPart(
                    f"cp_{output_name}",
                    '{"answer":"repaired",}',
                    provider_name="claude_code",
                )
            ]
        )

    patch_tool_call_json_repair()
    patch_tool_call_callbacks()
    result = await Agent(
        FunctionModel(model_function),
        output_type=_FinalOutput,
    ).run("finish")

    assert observed["output_name"] == "final_result"
    assert result.output == _FinalOutput(answer="repaired")


@pytest.mark.asyncio
async def test_partial_output_validation_does_not_rewrite_json(monkeypatch):
    observed = []

    async def validate(self, call, **kwargs):
        _ = self
        observed.append((call.args, kwargs.get("allow_partial")))
        return call

    monkeypatch.setattr(ToolManager, "validate_output_tool_call", validate)
    assert patch_tool_call_json_repair() is True
    manager = object()
    raw = '{"answer":"partial",}'

    await ToolManager.validate_output_tool_call(
        manager,
        ToolCallPart("final_result", raw),
        schema=object(),
        allow_partial=True,
    )
    assert observed[-1] == (raw, True)

    call = ToolCallPart("final_result", raw)
    await ToolManager.validate_output_tool_call(
        manager,
        call,
        schema=object(),
        allow_partial=False,
    )
    assert json.loads(observed[-1][0]) == {"answer": "partial"}
