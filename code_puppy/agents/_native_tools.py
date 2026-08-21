"""Native tool delivery as a first-class pydantic-ai capability.

Code Puppy's own tools (file ops, shell, sub-agent invocation, browser,
plugin-contributed extras, ...) were historically bolted onto the constructed
``pydantic_ai.Agent`` *after* the fact, via ``@agent.tool`` registration in
``code_puppy.tools.register_tools_for_agent``. pydantic-ai's capability
system has a dedicated seam for exactly this contribution --
``AbstractCapability.get_toolset()`` -- so the tool suite now arrives as a
:class:`NativeTools` capability instead of post-construction surgery.

Registration mechanics are deliberately unchanged: every ``register_*``
function in ``code_puppy.tools`` only ever uses the ``.tool`` decorator on
the object it is handed, and ``pydantic_ai.toolsets.FunctionToolset.tool``
is signature-identical to ``Agent.tool``. :func:`build_native_toolset`
therefore just points the existing registry at a ``FunctionToolset`` -- all
registry semantics (plugin tool merging, ``edit_file`` expansion,
kill-switches, per-model filtering, UC wrappers) live in
``register_tools_for_agent``, untouched.

Per-tool retry budgets are also unchanged: both registration paths leave
``max_retries=None`` on each tool, which pydantic-ai resolves to the
agent-level ``retries`` at ``get_tools`` time (``FunctionToolset.get_tools``
falls back to ``ctx.max_retries``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence

from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.toolsets import FunctionToolset


def build_native_toolset(
    tool_names: Sequence[str],
    model_name: Optional[str] = None,
    agent_name: Optional[str] = None,
) -> FunctionToolset:
    """Register ``tool_names`` from the tool registry onto a fresh toolset.

    Delegates to ``register_tools_for_agent`` -- imported at call time so
    test patches on ``code_puppy.tools`` still apply -- which only ever uses
    the ``.tool`` decorator on what it is given: historically an ``Agent``,
    here a ``FunctionToolset``. When tools are globally disabled
    (``--no-tools``) or every registration is filtered out, the returned
    toolset is simply empty.
    """
    from code_puppy.tools import register_tools_for_agent

    toolset: FunctionToolset = FunctionToolset()
    register_tools_for_agent(
        toolset,
        list(tool_names),
        model_name=model_name,
        agent_name=agent_name,
    )
    return toolset


@dataclass
class NativeTools(AbstractCapability[Any]):
    """Deliver code_puppy's registered tool suite via ``get_toolset()``.

    A pure configuration-seam capability: its position in the agent's
    ``capabilities=[...]`` list is inert, and it carries no per-run state.
    """

    toolset: FunctionToolset

    def get_toolset(self) -> Optional[FunctionToolset]:
        # An agent with nothing registered (``--no-tools``, or a test that
        # stubbed registration out) contributes no toolset at all, keeping
        # the run's toolset chain identical to the old post-construction
        # registration path (which likewise added nothing).
        return self.toolset if self.toolset.tools else None

    @classmethod
    def get_serialization_name(cls) -> Optional[str]:
        # Built from the live tool registry (plugins included) -- not
        # spec-constructible. Same opt-out as SteerInjection & friends.
        return None
