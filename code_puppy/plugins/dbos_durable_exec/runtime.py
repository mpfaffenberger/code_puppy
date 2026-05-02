"""Async context manager wrapping pydantic_agent.run() with DBOS workflow ID
and (when needed) MCP toolset injection on the inner pydantic agent."""

from __future__ import annotations

from contextlib import asynccontextmanager

from .workflow_ids import generate_dbos_workflow_id


def skip_fallback_render(_agent) -> bool:
    """DBOS renders its own output; tell core to skip the non-streaming fallback."""
    return True


@asynccontextmanager
async def dbos_run_context(agent, pydantic_agent, group_id, mcp_servers):
    """Wrap a run() call with SetWorkflowID and a temporary MCP toolset swap.

    For sub-agent invocations (group_id starting with 'invoke_agent'), append
    an atomic counter to ensure DBOS workflow ID uniqueness across rapid
    back-to-back calls. For the main agent, use group_id as-is.
    """
    try:
        from dbos import SetWorkflowID
    except ImportError:
        yield
        return

    workflow_id = (
        generate_dbos_workflow_id(group_id)
        if group_id and group_id.startswith("invoke_agent")
        else group_id
    )

    # The inner pydantic agent under DBOSAgent is exposed via `.wrapped`
    # (see pydantic_ai.agent.WrapperAgent). Fall back defensively.
    inner = getattr(pydantic_agent, "wrapped", pydantic_agent)

    original = None
    swapped = False
    if mcp_servers:
        original = getattr(inner, "_toolsets", []) or []
        inner._toolsets = list(original) + list(mcp_servers)
        swapped = True
    try:
        with SetWorkflowID(workflow_id):
            yield workflow_id
    finally:
        if swapped:
            inner._toolsets = original
