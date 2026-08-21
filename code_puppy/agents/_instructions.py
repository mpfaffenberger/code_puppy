"""System-prompt delivery as a first-class pydantic-ai capability.

Both agent construction paths (``agents/_builder.py`` and
``tools/subagent_invocation.py``) used to hand their fully assembled system
prompt to pydantic-ai via the ``Agent(instructions=...)`` constructor kwarg.
:class:`AssembledInstructions` moves that delivery onto the dedicated
``get_instructions()`` capability seam instead, so the prompt travels with
the rest of the agent's capabilities.

The *assembly* logic is deliberately untouched: ``_builder`` still composes
the main agent's prompt (full system prompt + AGENTS.md puppy rules +
extended-thinking note + GPT-5.6 guards) and ``subagent_invocation`` still
composes the sub-agent variant (identity prompt, no AGENTS.md), both funnelled
through ``prepare_prompt_for_model``. This capability only owns the last
mile: handing the finished string to pydantic-ai.

Parity notes (pydantic-ai 2.31.0):

* **Wire content is byte-identical.** Agent-level instructions and capability
  contributions land in the same literal pool, are joined with ``"\\n"`` and
  stripped (``Agent._get_instructions``). With the constructor kwarg unset and
  exactly one capability contributing one string, the resulting
  ``ModelRequest.instructions`` is exactly what the kwarg produced. An empty
  assembled string collapses to ``None`` on the wire on both paths.
* **Build-time freeze is preserved.** Capability instructions are re-extracted
  per run (``for_run`` re-resolution), but the default ``for_run`` returns
  ``self`` and the snapshot here is a plain string field -- config or file
  edits keep applying on agent *rebuild* only, exactly as before.
* **``Agent.override(instructions=...)`` behaves identically.** The override
  replaces *all* instructions, capability contributions included, so unlike
  the model-settings conversion there is no precedence divergence to document.
* **Spec-constructible.** The only field is a plain string, so the inherited
  ``get_serialization_name()`` / ``from_spec`` defaults are kept.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic_ai.capabilities import AbstractCapability


@dataclass
class AssembledInstructions(AbstractCapability[Any]):
    """Deliver a pre-assembled system prompt through ``get_instructions()``.

    ``instructions`` is the final, model-ready prompt text -- callers finish
    all composition (puppy rules, model-specific prep, sub-agent identity)
    before constructing this capability.
    """

    instructions: str

    def get_instructions(self) -> str:
        return self.instructions
