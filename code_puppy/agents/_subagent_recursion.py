"""Sub-agent recursion limits as a pydantic-ai capability.

The recursion guards -- the general ``subagent_recursion_limit`` depth cap
and the GPT-5.6 overlay cap -- historically lived at the top of
``_invoke_agent_impl``, inside the tool body, invisible to the agent's
declared wiring. ``wrap_tool_execute`` is pydantic-ai's seam for exactly
that decision: it fires after plugin ``pre_tool_call`` dispatch and after
argument validation, and returning without calling ``handler()`` replaces
the tool result without ever running the tool.

``SubagentRecursionGuard`` denies ``invoke_agent`` /
``invoke_agent_with_model`` calls that would exceed the configured depth,
producing the byte-identical denial the in-tool guard produced: same i18n
error strings, same ``AgentInvokeOutput`` / ``AgentInvokeWithModelOutput``
shape, same ``emit_error``. ``post_tool_call`` plugin callbacks still see
the denial as the tool result (the seam sits inside the patched
``ToolManager.execute_tool_call``), so observability is unchanged.

Custody note (the RoundRobinRequests "guest" doctrine): the in-tool guard
in ``_invoke_agent_impl`` stays intact as *guest* custody -- direct callers
and foreign agents that registered the invoke tools without this capability
keep the old protection. For agents built by code_puppy (both construction
sites wire this capability) the seam denies first, making the in-tool
re-check an unreachable no-op; both custodies share
``recursion_guard_error`` / ``denied_invocation_output``, so their verdicts
and denial bytes can never drift.

Deliberate precedence pin: ``invoke_agent_with_model`` rejects an *empty*
``model_name`` before the recursion guard runs (that check lives in the
tool wrapper, above the impl guard). Blank-model calls therefore pass
through this capability untouched so the tool's own error keeps winning.
"""

from __future__ import annotations

from typing import Any, FrozenSet, List

from pydantic_ai.capabilities import AbstractCapability

# Tool names whose execution is gated by the recursion guards.
GUARDED_TOOL_NAMES: FrozenSet[str] = frozenset(
    {"invoke_agent", "invoke_agent_with_model"}
)


class SubagentRecursionGuard(AbstractCapability[Any]):
    """Deny sub-agent invocations that would exceed the recursion limits.

    Stateless: the guards read ambient ``subagent_context`` contextvars and
    live config at call time, exactly as the in-tool custody does, so the
    verdict is identical at either layer.
    """

    async def wrap_tool_execute(
        self,
        ctx: Any,
        *,
        call: Any,
        tool_def: Any,
        args: Any,
        handler: Any,
    ) -> Any:
        if tool_def.name not in GUARDED_TOOL_NAMES:
            return await handler(args)
        # Lazy import: this capability is wired from both construction sites
        # (agents/_builder and tools/subagent_invocation); a top-level import
        # of the tool module would be circular.
        from code_puppy.tools.subagent_invocation import (
            denied_invocation_output,
            recursion_guard_error,
        )

        if not isinstance(args, dict):  # pragma: no cover - defensive
            return await handler(args)
        agent_name = args.get("agent_name")
        if not isinstance(agent_name, str):
            # Malformed args: let the tool's own validation/error path own it.
            return await handler(args)

        include_usage_metrics = tool_def.name == "invoke_agent_with_model"
        model_name: str | None = None
        if include_usage_metrics:
            raw_model_name = args.get("model_name")
            model_name = (
                raw_model_name.strip() if isinstance(raw_model_name, str) else ""
            )
            if not model_name:
                # Empty-model rejection precedes the recursion guard on main;
                # fall through so the tool's own check answers first.
                return await handler(args)

        error = recursion_guard_error(agent_name)
        if error is None:
            return await handler(args)
        return denied_invocation_output(
            agent_name=agent_name,
            model_name=model_name,
            include_usage_metrics=include_usage_metrics,
            error=error,
        )


def build_subagent_recursion_guard(
    tool_names: Any,
) -> List[SubagentRecursionGuard]:
    """Conditional splice: guard only agents that expose the invoke tools.

    Returned as a list so callers can splice it into ``capabilities=[...]``
    unconditionally (same shape as ``build_tool_output_limits``); agents
    without ``invoke_agent`` tools keep a byte-identical capability list.
    """
    if GUARDED_TOOL_NAMES & set(tool_names or ()):
        return [SubagentRecursionGuard()]
    return []
