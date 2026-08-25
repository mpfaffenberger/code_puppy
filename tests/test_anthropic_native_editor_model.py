"""``AnthropicNativeEditorModel`` wire-declaration override tests.

Verifies the one seam this class exists for: the native editor tool gets
Anthropic's fixed client-executed-tool shape (no schema/description), while
every other tool still gets the normal JSON-schema tool param the base
class builds. A regression here would either leak our schema onto the wire
for the native tool (defeating the point of using the trained-on interface)
or silently stop declaring some other tool correctly.
"""

from unittest.mock import patch

from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessagesTypeAdapter,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import ToolDefinition

from code_puppy.anthropic_native_editor_model import AnthropicNativeEditorModel
from code_puppy.model_capabilities import (
    NATIVE_EDITOR_TOOL_NAME,
    NATIVE_EDITOR_TOOL_TYPE,
)
from code_puppy.tools.anthropic_editor_tool import register_str_replace_based_edit_tool


def _make_model() -> AnthropicNativeEditorModel:
    # __init__ requires a real/valid provider; bypass it since these tests
    # only exercise _map_tool_definition, a pure function of its arguments.
    return AnthropicNativeEditorModel.__new__(AnthropicNativeEditorModel)


def test_native_editor_tool_gets_the_raw_anthropic_shape_with_no_schema():
    model = _make_model()
    tool_def = ToolDefinition(
        name=NATIVE_EDITOR_TOOL_NAME,
        description="whatever our function's docstring says",
        parameters_json_schema={"type": "object", "properties": {"command": {}}},
    )

    result = model._map_tool_definition(tool_def, {}, visibility="visible")

    assert result == {
        "name": NATIVE_EDITOR_TOOL_NAME,
        "type": NATIVE_EDITOR_TOOL_TYPE,
    }


def test_native_editor_tool_sets_defer_loading_when_deferred():
    model = _make_model()
    tool_def = ToolDefinition(
        name=NATIVE_EDITOR_TOOL_NAME, description="", parameters_json_schema={}
    )

    result = model._map_tool_definition(tool_def, {}, visibility="deferred")

    assert result == {
        "name": NATIVE_EDITOR_TOOL_NAME,
        "type": NATIVE_EDITOR_TOOL_TYPE,
        "defer_loading": True,
    }


def test_every_other_tool_still_uses_the_base_class_json_schema_path():
    """A tool with any other name must be completely unaffected -- proves
    this is a narrow, single-tool override, not a broad behavior change."""
    model = _make_model()
    other_tool = ToolDefinition(
        name="read_file",
        description="Reads a file.",
        parameters_json_schema={"type": "object", "properties": {"path": {}}},
    )

    with patch(
        "pydantic_ai.models.anthropic.AnthropicModel._map_tool_definition"
    ) as base_map:
        base_map.return_value = {
            "name": "read_file",
            "sentinel": "base-class-built-this",
        }
        result = model._map_tool_definition(other_tool, {}, visibility="visible")

    base_map.assert_called_once_with(other_tool, {}, visibility="visible")
    assert result == {"name": "read_file", "sentinel": "base-class-built-this"}


def test_no_message_history_or_serialization_method_is_overridden():
    """Model-switch safety (see `History and model switching` in the plan)
    rests on this class touching *only* outbound tool-declaration shape --
    never how a request/response/history message is built or replayed.
    Assert that directly on the class body rather than trusting the module
    docstring's claim: this fails the moment a second override is added
    without updating the model-switching reasoning that depends on there
    being exactly one.
    """
    own_members = {
        name: value
        for name, value in vars(AnthropicNativeEditorModel).items()
        if callable(value) and not name.startswith("__")
    }
    assert set(own_members) == {"_map_tool_definition"}


def test_native_editor_history_replays_cleanly_through_a_non_anthropic_model():
    """Verification (not the sole safeguard -- see the plan's `History and
    model switching` section) for the highest-risk claim in this plan: a
    native-editor tool call/result surviving a mid-session model switch
    without producing a hard 400 on the next provider.

    The prior test proves *why* this should hold (no history-shaping
    override exists). This test proves it end-to-end using the exact
    mechanism `session_storage.py` relies on for every save/load regardless
    of provider (`ModelMessagesTypeAdapter`): run the real tool through a
    plain, non-Anthropic pydantic-ai model, then round-trip the resulting
    history through that adapter and assert it comes back byte-for-byte
    identical, made only of ordinary ToolCallPart/ToolReturnPart -- never an
    Anthropic-specific block type a different provider's mapper could choke
    on.
    """
    agent = Agent(TestModel(call_tools=[NATIVE_EDITOR_TOOL_NAME]))
    register_str_replace_based_edit_tool(agent)

    result = agent.run_sync("call the editor tool")
    messages = result.all_messages()

    tool_call_parts = [
        p for m in messages for p in m.parts if isinstance(p, ToolCallPart)
    ]
    tool_return_parts = [
        p for m in messages for p in m.parts if isinstance(p, ToolReturnPart)
    ]
    assert tool_call_parts and all(
        type(p) is ToolCallPart and p.tool_name == NATIVE_EDITOR_TOOL_NAME
        for p in tool_call_parts
    )
    assert tool_return_parts and all(
        type(p) is ToolReturnPart and p.tool_name == NATIVE_EDITOR_TOOL_NAME
        for p in tool_return_parts
    )
    # The dispatcher's result is a plain JSON-shaped dict, not some
    # Anthropic-only content block.
    assert all(isinstance(p.content, dict) for p in tool_return_parts)

    dumped = ModelMessagesTypeAdapter.dump_python(messages)
    restored = ModelMessagesTypeAdapter.validate_python(dumped)
    assert restored == messages
