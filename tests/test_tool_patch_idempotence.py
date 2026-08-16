"""Independent idempotence contracts for each patched pydantic-ai seam."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic_ai._agent_graph import CallToolsNode
from pydantic_ai.tool_manager import ToolManager

from code_puppy import callbacks
from code_puppy.tool_call_patches import patch_tool_call_callbacks


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "perturbed",
    ["execute", "get", "output_validate", "validate", "handle"],
)
async def test_partial_patch_repair_does_not_duplicate_lifecycle(
    monkeypatch,
    perturbed,
):
    lifecycle = []

    async def execute(self, validated, **kwargs):
        _ = self, validated, kwargs
        return "ok"

    def get_tool_def(self, name):
        tool = self.tools.get(name)
        return None if tool is None else tool.tool_def

    async def validate(self, call, **kwargs):
        _ = self, kwargs
        return call

    async def output_validate(self, call, **kwargs):
        _ = self, kwargs
        return call

    async def handle(self, ctx, tool_calls, **kwargs):
        _ = self, ctx, tool_calls, kwargs
        if False:
            yield None

    monkeypatch.setattr(ToolManager, "execute_tool_call", execute)
    monkeypatch.setattr(ToolManager, "get_tool_def", get_tool_def)
    monkeypatch.setattr(ToolManager, "validate_tool_call", validate)
    monkeypatch.setattr(ToolManager, "validate_output_tool_call", output_validate)
    monkeypatch.setattr(CallToolsNode, "_handle_tool_calls", handle)
    assert patch_tool_call_callbacks() is True

    owners = {
        "execute": (ToolManager, "execute_tool_call"),
        "get": (ToolManager, "get_tool_def"),
        "output_validate": (ToolManager, "validate_output_tool_call"),
        "validate": (ToolManager, "validate_tool_call"),
        "handle": (CallToolsNode, "_handle_tool_calls"),
    }
    before = {name: getattr(owner, attr) for name, (owner, attr) in owners.items()}
    owner, attribute = owners[perturbed]
    monkeypatch.setattr(owner, attribute, before[perturbed].__wrapped__)
    assert patch_tool_call_callbacks() is True

    after = {name: getattr(owner, attr) for name, (owner, attr) in owners.items()}
    assert all(after[name] is before[name] for name in owners if name != perturbed)

    callbacks.clear_callbacks("pre_tool_call")
    callbacks.clear_callbacks("post_tool_call")
    callbacks.clear_callbacks("final_tool_result")
    callbacks.register_callback(
        "pre_tool_call", lambda *args, **kwargs: lifecycle.append("pre")
    )
    callbacks.register_callback(
        "post_tool_call", lambda *args, **kwargs: lifecycle.append("post")
    )
    callbacks.register_callback(
        "final_tool_result", lambda *args, **kwargs: lifecycle.append("final")
    )
    tool = SimpleNamespace(tool_def=SimpleNamespace(kind="function"))
    manager = SimpleNamespace(
        ctx=SimpleNamespace(
            usage=SimpleNamespace(tool_calls=0),
            model=SimpleNamespace(provider=SimpleNamespace(name="openai")),
        ),
        tools={"safe": tool},
        succeeded_tools=set(),
    )
    call = SimpleNamespace(
        tool_name="safe",
        args='{"value":1}',
        provider_name="openai",
    )
    validated = SimpleNamespace(
        call=call,
        tool=tool,
        args_valid=True,
        validated_args={"value": 1},
        validation_error=None,
        deferral=None,
    )

    assert await ToolManager.execute_tool_call(manager, validated) == "ok"
    assert lifecycle == ["pre", "post", "final"]
