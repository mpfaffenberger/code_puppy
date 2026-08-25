"""The Phase 3 model-layer seam: substitute Anthropic's native, client-executed
text-editor tool declaration for one specific pydantic-ai tool, leaving every
other tool's request/response handling completely unmodified.

Why a subclass and not a generic HTTP body rewrite (per the plan's Phase 3
step 1): pydantic-ai's public ``native_tools`` surface has no text-editor
tool class (verified against the installed ``pydantic-ai-slim`` 2.31.0 -- see
``.context/plan/anthropic-editor-adapter.md``, Phase 3 step 0), so there is
no supported public API to prefer. This overrides exactly one well-defined,
private-but-stable extension point (``_map_tool_definition``, the single
place a ``ToolDefinition`` becomes the wire-level tool param) rather than
reimplementing request construction.

The inbound side needs no changes at all: we still register
``str_replace_based_edit_tool`` as an ordinary pydantic-ai function tool (see
``code_puppy/tools/anthropic_editor_tool.py``). Claude's ``tool_use`` blocks
for this tool carry the same command-shaped JSON regardless of which wire
declaration triggered them, and pydantic-ai's normal FunctionToolset dispatch
already validates that JSON against our function's own parameter model. Only
the *outbound* declaration -- what we tell Anthropic this tool looks like --
needs to differ from the generic ``{name, description, input_schema}`` shape.
Because history is stored as ordinary ``ToolCallPart``/``ToolReturnPart``
entries (not an Anthropic-specific block type), switching models mid-session
also needs no special normalization here -- see `History and model
switching` in the plan.
"""

from __future__ import annotations

from typing import Any

from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.tools import ToolDefinition

from code_puppy.model_capabilities import (
    NATIVE_EDITOR_TOOL_NAME,
    NATIVE_EDITOR_TOOL_TYPE,
)


class AnthropicNativeEditorModel(AnthropicModel):
    """``AnthropicModel`` that declares the native text-editor tool natively.

    Every other tool continues through the base class's normal JSON-schema
    tool-definition path unchanged.
    """

    def _map_tool_definition(
        self,
        f: ToolDefinition,
        model_settings: Any,
        *,
        visibility: Any,
    ) -> Any:
        if f.name != NATIVE_EDITOR_TOOL_NAME:
            return super()._map_tool_definition(
                f, model_settings, visibility=visibility
            )

        # Anthropic's client-executed editor tool: the API already knows this
        # tool's input shape from training, so -- unlike a normal custom
        # tool -- no `input_schema`/`description` travels on the wire at all.
        tool_param: dict[str, Any] = {
            "name": NATIVE_EDITOR_TOOL_NAME,
            "type": NATIVE_EDITOR_TOOL_TYPE,
        }
        if visibility == "deferred":
            tool_param["defer_loading"] = True
        return tool_param
