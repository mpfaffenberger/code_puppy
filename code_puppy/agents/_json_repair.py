"""Tool-call JSON repair as a first-class pydantic-ai capability.

Promotes the ``patch_tool_call_json_repair`` monkeypatch (see
``code_puppy.pydantic_patches``) to the ``before_tool_validate`` capability
seam. LLMs sometimes emit slightly broken JSON in tool-call arguments
(trailing commas, missing quotes, unclosed braces); repairing the raw args
before validation prevents an unnecessary retry round-trip.

**Delivery model — explicit-when-ours, fallback-for-guests** (the same
split ``Instrumentation`` uses for tracing): agents built by code_puppy's
own construction sites carry an explicit :class:`ToolCallJsonRepair`
capability, and the monkeypatch detects it (via the run's
``ToolManager.root_capability`` tree) and steps aside. Raw pydantic-ai
agents built by plugins (e.g. wiggum's judge, which registers real
read-only tools) carry no capability, so the patch keeps repairing for
them exactly as before.

Parity notes versus the eager patch:

* **Same repair, same custody.** The hook receives the *live*
  ``ToolCallPart`` — the object recorded in the run's message state — so
  assigning ``call.args`` here lands the repaired JSON in message history
  exactly as the patch's in-place mutation did, while the returned args
  feed validation.
* **Unknown/unavailable tools are a bounded divergence.**
  ``ToolManager._resolve_tool`` raises before ``before_tool_validate``
  fires, so a call to a nonexistent tool no longer gets its recorded args
  repaired (the patch repaired first, resolution failed after). The call
  fails with the identical ``ModelRetry`` either way; history now keeps
  the model's true emitted bytes, which is arguably more honest.
* **Output tools were never covered.** On pydantic-ai 2.31.0, tool-based
  structured output validates through ``validate_output_tool_call`` — a
  method the patch never wrapped — so skipping the ``kind == 'output'``
  carve-out here (pydantic-ai excludes output tools from tool hooks
  anyway) changes nothing.

``json_repair`` is an optional dependency: :func:`build_tool_call_json_repair`
returns ``[]`` when it is missing (mirroring the patch's quiet skip and the
``build_tool_output_limits`` conditional-splice pattern), and the hook
no-ops defensively if a capability instance is constructed anyway.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List

from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import ToolDefinition

try:  # pragma: no cover - exercised via the None-fallback tests
    import json_repair
except ImportError:  # pragma: no cover - optional dependency absent
    json_repair = None  # type: ignore[assignment]

__all__ = ["ToolCallJsonRepair", "build_tool_call_json_repair"]


@dataclass
class ToolCallJsonRepair(AbstractCapability[Any]):
    """Repair malformed JSON tool-call arguments before validation.

    Stateless: safe to share across construction passes and spec-construct
    (the default ``get_serialization_name``/``from_spec`` apply).
    """

    async def before_tool_validate(
        self,
        ctx: RunContext[Any],
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: str | dict[str, Any],
    ) -> str | dict[str, Any]:
        """Return repaired raw args; mirror the repair onto ``call.args``.

        Only string args are candidates (dict args already parsed upstream).
        Repair failures are swallowed — the original args proceed to
        validation, which produces the retry the model would have earned
        anyway. Both guards match the patch byte-for-byte.
        """
        if json_repair is None:
            return args
        if isinstance(args, str) and args:
            try:
                repaired = json_repair.repair_json(args)
                if repaired != args:
                    # Same in-place custody the patch performed: this is the
                    # ToolCallPart recorded in the run's message state, so
                    # history shows the repaired JSON the tool actually ran
                    # with.
                    call.args = repaired
                    return repaired
            except Exception:
                pass  # let validation surface the original breakage
        return args


def build_tool_call_json_repair() -> List[ToolCallJsonRepair]:
    """Build the repair capability, or ``[]`` when ``json_repair`` is absent.

    Returned as a list so callers can splice it into ``capabilities=[...]``
    unconditionally, exactly like ``build_tool_output_limits``.
    """
    if json_repair is None:
        return []
    return [ToolCallJsonRepair()]
