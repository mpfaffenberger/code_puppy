"""Regression tests for structured post-tool mutation before hook context."""

from __future__ import annotations

import asyncio
import json
import threading
import time

import pytest
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai._tool_manager import ToolManager
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from code_puppy import callbacks, pydantic_patches
from code_puppy.pydantic_patches import patch_tool_call_callbacks


class _StructuredOutput(BaseModel):
    content: str


@pytest.mark.asyncio
async def test_post_callbacks_mutate_structured_result_before_context_stringification(
    monkeypatch,
):
    observed = {}
    compose_threads = []
    real_compose = pydantic_patches._compose_hook_result_envelope

    def slow_compose(*args, **kwargs):
        compose_threads.append(threading.current_thread().name)
        time.sleep(0.1)
        return real_compose(*args, **kwargs)

    monkeypatch.setattr(
        pydantic_patches,
        "_compose_hook_result_envelope",
        slow_compose,
    )

    def model_function(messages, info):
        _ = info
        returns = [
            part
            for message in messages
            for part in message.parts
            if isinstance(part, ToolReturnPart)
        ]
        if not returns:
            return ModelResponse(parts=[ToolCallPart("structured_tool", {})])
        observed["model_response"] = returns[-1].model_response_str()
        return ModelResponse(parts=[TextPart("done")])

    def add_context(tool_name, tool_args, context=None):
        _ = tool_name, tool_args, context
        return {"context_message": "policy context"}

    def mutate_result(tool_name, tool_args, result, duration_ms, context=None):
        _ = tool_name, tool_args, duration_ms, context
        observed["post_type"] = type(result)
        result.content = "bounded"

    def observe_final(tool_name, tool_args, result, duration_ms, context=None):
        _ = tool_name, tool_args, duration_ms, context
        observed["final_result"] = result.copy()

    original_call_tool = ToolManager._call_tool
    original_get_tool_def = ToolManager.get_tool_def
    original_handle_call = ToolManager.handle_call
    callbacks.register_callback("pre_tool_call", add_context)
    callbacks.register_callback("post_tool_call", mutate_result)
    callbacks.register_callback("final_tool_result", observe_final)
    patch_tool_call_callbacks()
    patched_call_tool = ToolManager._call_tool
    patch_tool_call_callbacks()
    assert ToolManager._call_tool is patched_call_tool
    try:
        agent = Agent(FunctionModel(model_function))

        @agent.tool_plain
        def structured_tool() -> _StructuredOutput:
            return _StructuredOutput(content="original")

        ticks = 0
        running = True

        async def ticker():
            nonlocal ticks
            while running:
                ticks += 1
                await asyncio.sleep(0.005)

        ticker_task = asyncio.create_task(ticker())
        run_result = await agent.run("go")
        running = False
        await ticker_task
    finally:
        ToolManager._call_tool = original_call_tool
        ToolManager.get_tool_def = original_get_tool_def
        ToolManager.handle_call = original_handle_call
        callbacks.unregister_callback("pre_tool_call", add_context)
        callbacks.unregister_callback("post_tool_call", mutate_result)
        callbacks.unregister_callback("final_tool_result", observe_final)

    envelope = json.loads(observed["model_response"])
    assert run_result.output == "done"
    assert observed["post_type"] is _StructuredOutput
    assert compose_threads and compose_threads[0] != threading.current_thread().name
    assert ticks >= 5
    assert envelope["hook_context"] == "[hook context]\npolicy context"
    assert observed["final_result"] == envelope
    assert "bounded" in envelope["tool_result"]
    assert "original" not in envelope["tool_result"]
