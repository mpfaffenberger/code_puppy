"""DBOSAgent wrapper, registered via the wrap_pydantic_agent hook.

The DBOS wrapper can't pickle async-generator MCP toolsets, so we stash
them off the inner pydantic agent before wrapping. They're restored at
run-time inside :mod:`runtime` so MCP tools remain available during the run.
"""

from __future__ import annotations

import itertools

_reload_count = itertools.count()


def wrap_with_dbos_agent(
    agent,
    pydantic_agent,
    *,
    event_stream_handler=None,
    message_group=None,
    kind: str = "main",
):
    """Return a DBOSAgent wrapping ``pydantic_agent`` (or None if DBOS missing).

    Returns None — meaning "don't wrap, leave the plain pydantic agent alone" —
    in three cases:
      1. pydantic_ai.durable_exec.dbos is not importable.
      2. DBOS itself was never launched (e.g. wrapper hook fired in the
         pytest process where on_startup() was never called).

    Without case 2 the wrapper would hand back a DBOSAgent whose .run()
    fails because there is no running DBOS instance — exactly the
    `run_with_mcp returned None` regression seen when [durable] extras
    were installed in the CI test environment.
    """
    # Subagents are ephemeral child runs invoked from the main agent's tool
    # call. They don't need their own durable DBOS workflow — and wrapping
    # them forces DBOS to pickle the per-run inputs, which crashes on the
    # ``event_stream_handler`` closure that subagent_invocation passes
    # (``Can't get local object '_make_stream_handler_wrapper.<locals>._wrapped'``).
    # Leave subagents as plain pydantic agents; the main agent's workflow
    # already provides durability for the tool call that spawned them.
    if kind != "main":
        return None

    from .lifecycle import is_launched

    if not is_launched():
        return None

    try:
        from pydantic_ai.durable_exec.dbos import DBOSAgent
    except ImportError:
        return None

    # Reset toolsets — DBOS can't pickle async-generator MCP toolsets.
    # The runtime hook re-injects MCP servers from its own arg at run time.
    pydantic_agent._toolsets = []

    name_suffix = next(_reload_count)
    agent_name = getattr(agent, "name", "agent")
    # Sub-agent path historically didn't pass an event stream handler.
    handler = event_stream_handler if kind == "main" else None
    return DBOSAgent(
        pydantic_agent,
        name=f"{agent_name}-{kind}-{name_suffix}",
        event_stream_handler=handler,
    )
