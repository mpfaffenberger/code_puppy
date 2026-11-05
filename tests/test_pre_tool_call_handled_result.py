"""A pre_tool_call hook may handle a call itself and supply its result.

An editor client that shows ``ask_user_question`` as its own question UI has
*handled* the call: the terminal picker must not run, but the model should
not be told that a hook policy denied the tool either. Such a hook blocks and
passes ``tool_result``, which the model receives as the tool's return value.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic_ai.tool_manager import ToolManager

from code_puppy import callbacks, pydantic_patches
from code_puppy._pydantic_tool_helpers import (
    _handled_result_for_blocks,
    _handled_tool_result,
)

HANDLED = {"blocked": True, "tool_result": "Shown to the user; wait for answers."}
DENY = {"blocked": True, "error_message": "policy says no"}


def test_handled_result_needs_a_non_blank_string():
    assert _handled_tool_result(HANDLED) == HANDLED["tool_result"]
    assert _handled_tool_result({"blocked": True, "tool_result": "  "}) is None
    assert _handled_tool_result({"blocked": True, "tool_result": 42}) is None
    assert _handled_tool_result(DENY) is None


def test_a_plain_deny_from_any_hook_wins():
    assert _handled_result_for_blocks([HANDLED]) == HANDLED["tool_result"]
    assert _handled_result_for_blocks([HANDLED, DENY]) is None
    assert _handled_result_for_blocks([None, {"blocked": False}]) is None
    assert _handled_result_for_blocks([]) is None


@pytest.fixture
def patched_execute(monkeypatch):
    """Install the tool-call patch over a stub that records real executions."""
    executed = []

    async def execute_tool_call(_manager, validated, **_kwargs):
        executed.append(validated.call.tool_name)
        return "tool ran"

    for name in ("get_tool_def", "validate_tool_call", "validate_output_tool_call"):
        monkeypatch.setattr(ToolManager, name, getattr(ToolManager, name))
    monkeypatch.setattr(ToolManager, "execute_tool_call", execute_tool_call)
    assert pydantic_patches.patch_tool_call_callbacks() is True
    monkeypatch.setitem(callbacks._callbacks, "pre_tool_call", [])
    yield executed


async def _call(tool_name: str) -> str:
    call = SimpleNamespace(tool_name=tool_name, args={"questions": []})
    validated = SimpleNamespace(call=call, validated_args={"questions": []})
    manager = SimpleNamespace(tools={tool_name: object()})
    return await ToolManager.execute_tool_call(manager, validated)


@pytest.mark.asyncio
async def test_handled_call_returns_the_hook_result(patched_execute):
    callbacks.register_callback("pre_tool_call", lambda *a, **k: dict(HANDLED))

    result = await _call("ask_user_question")

    assert result == HANDLED["tool_result"]
    assert patched_execute == []


@pytest.mark.asyncio
async def test_plain_block_is_still_a_deny(patched_execute):
    callbacks.register_callback("pre_tool_call", lambda *a, **k: dict(DENY))

    result = await _call("ask_user_question")

    assert result.startswith("ERROR: 🚫 Hook blocked this tool call: policy says no")
    assert patched_execute == []


@pytest.mark.asyncio
async def test_unblocked_call_runs(patched_execute):
    callbacks.register_callback("pre_tool_call", lambda *a, **k: None)

    assert await _call("ask_user_question") == "tool ran"
    assert patched_execute == ["ask_user_question"]
