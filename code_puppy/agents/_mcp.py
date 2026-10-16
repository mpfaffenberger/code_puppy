"""Agent-bound MCP startup and toolset selection.

Called by: agents._builder and BaseAgent.run_with_mcp.
Depends on: MCPManager lifecycle, bindings, and pre-autostart callbacks.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any, Dict, List, Optional, Set

from code_puppy.callbacks import on_pre_mcp_autostart, on_pre_mcp_autostart_sync
from code_puppy.config import get_truthy_bool_value
from code_puppy.mcp_ import get_mcp_manager
from code_puppy.messaging import emit_info, emit_warning

logger = logging.getLogger(__name__)

_prepared_agent: ContextVar[str | None] = ContextVar("mcp_prepared_agent", default=None)


def load_mcp_servers(
    extra_headers: Optional[Dict[str, str]] = None,
    agent_name: Optional[str] = None,
) -> List[Any]:
    """Return pydantic-ai compatible MCP servers, or ``[]`` if disabled.

    When ``agent_name`` is provided, only servers bound to that agent (via
    ``mcp_agent_bindings.json``) are returned. Servers marked ``auto_start``
    in their binding are kicked off in the background here so they're warm
    by the time the agent runs.
    """
    del extra_headers  # accepted for API compatibility; manager owns headers
    from code_puppy.tools import tools_disabled

    if tools_disabled():
        # --no-tools implies no MCP toolsets either (issue #182).
        return []

    if get_truthy_bool_value("disable_mcp_servers", False):
        return []

    manager = get_mcp_manager()
    if agent_name and _prepared_agent.get() != agent_name:
        _autostart_bound_servers(manager, agent_name)
    return manager.get_servers_for_agent(agent_name=agent_name)


def _with_runtime_mcp_toolsets(agent: Any, mcp_servers: List[Any]) -> List[Any]:
    """Append the MCP toolsets injected for this agent instance.

    Embedders (an ACP client's ``mcpServers``) attach these with
    ``BaseAgent.set_runtime_mcp_toolsets``. ``--no-tools`` still means no MCP
    toolsets at all.
    """
    from code_puppy.tools import tools_disabled

    runtime = getattr(agent, "get_runtime_mcp_toolsets", lambda: [])()
    if not runtime or tools_disabled():
        return mcp_servers
    return list(mcp_servers or []) + list(runtime)


def _iter_autostart_targets(manager: Any, agent_name: str):
    """Yield ``(server_name, config)`` tuples that need to be auto-started.

    Walks the bindings for ``agent_name``, filters to ``auto_start=True``,
    skips servers that are already running/starting, and skips bindings
    whose server config has been deleted.

    Side effect: emits a one-shot warning per missing server so a user who
    copied a JSON sub-agent config from elsewhere isn't left wondering why
    its tools silently disappeared. Warnings are deduped via
    ``_warn_missing_server`` so a long-running session doesn't spam the
    same message every invocation.
    """
    try:
        from code_puppy.mcp_.agent_bindings import get_bound_servers
        from code_puppy.mcp_.managed_server import ServerState
    except Exception:  # pragma: no cover - defensive import
        return

    bindings = get_bound_servers(agent_name)
    if not bindings:
        return

    for server_name, opts in bindings.items():
        if not opts.get("auto_start"):
            continue
        config = manager.get_server_by_name(server_name)
        if config is None:
            _warn_missing_server(agent_name, server_name)
            continue
        suppressed = getattr(manager, "is_autostart_suppressed", None)
        if suppressed is not None and suppressed(config.id) is True:
            continue
        try:
            status = manager.get_server_status(config.id)
            state = status.get("state")
        except Exception:  # pragma: no cover - defensive
            continue
        if status.get("enabled") is False and not config.enabled:
            continue
        if state in (ServerState.RUNNING.value, ServerState.STARTING.value):
            continue
        yield server_name, config


# Dedupe set of ``(agent_name, server_name)`` pairs already warned about — no
# TTLs, a fresh process resets it ("warn once per session").
_WARNED_MISSING: set[tuple[str, str]] = set()


def _warn_missing_server(agent_name: str, server_name: str) -> None:
    """Warn once that an agent declares an MCP server that isn't installed."""
    key = (agent_name, server_name)
    if key in _WARNED_MISSING:
        return
    _WARNED_MISSING.add(key)
    emit_warning(
        f"Agent '{agent_name}' declares MCP server '{server_name}' but it's "
        f"not installed. Run `/mcp install` to add it, or remove the entry "
        f"from the agent's JSON config."
    )


def _autostart_bound_servers(manager: Any, agent_name: str) -> None:
    """Schedule bound startups without claiming readiness.

    Called by: load_mcp_servers for synchronous builds outside prepared_mcp_run.
    Depends on: pre-autostart callbacks and MCPManager.start_server_sync.
    Async callers use autostart_bound_servers_async before building toolsets.
    """
    targets = list(_iter_autostart_targets(manager, agent_name))
    if not targets:
        return
    on_pre_mcp_autostart_sync(agent_name, [name for name, _ in targets])
    for server_name, config in targets:
        try:
            if not manager.start_server_sync(config.id, auto_start=True):
                continue
            emit_info(
                f"Auto-started MCP server '{server_name}' for agent '{agent_name}'"
            )
        except Exception as exc:  # pragma: no cover - defensive
            emit_warning(f"Auto-start failed for MCP server '{server_name}': {exc}")


async def autostart_bound_servers_async(manager: Any, agent_name: str) -> None:
    """Await readiness so lifecycle tasks own MCP cancel scopes before a run.

    Called by: prepared_mcp_run and tools.subagent_invocation.
    Depends on: pre-autostart callbacks and MCPManager.start_server.
    """
    targets = list(_iter_autostart_targets(manager, agent_name))
    if not targets:
        return
    task = asyncio.current_task()
    cancellations = task.cancelling() if task is not None else 0
    await on_pre_mcp_autostart(agent_name, [name for name, _ in targets])
    # Nested runtimes can consume CancelledError; a cancelled hook must not start MCP.
    if task is not None and task.cancelling() > cancellations:
        raise asyncio.CancelledError
    for server_name, config in targets:
        try:
            if not await manager.start_server(config.id, auto_start=True):
                continue
            emit_info(
                f"Auto-started MCP server '{server_name}' for agent '{agent_name}'"
            )
        except Exception as exc:  # pragma: no cover - defensive
            emit_warning(f"Auto-start failed for MCP server '{server_name}': {exc}")


@asynccontextmanager
async def prepared_mcp_run(agent: Any) -> AsyncIterator[None]:
    """Prepare once per invocation before a cached client can be reused.

    Called by: BaseAgent.run_with_mcp.
    Depends on: bound-server autostart and MCPManager readiness/toolset selection.
    """
    from code_puppy.agents._run_signals import mcp_preparation_cancellation
    from code_puppy.tools import tools_disabled

    if tools_disabled() or get_truthy_bool_value("disable_mcp_servers", False):
        yield
        return

    try:
        manager = get_mcp_manager()
        with mcp_preparation_cancellation():
            await autostart_bound_servers_async(manager, agent.name)
            await manager.wait_for_pending_starts()
        if agent._bound_mcp_toolsets != manager.get_servers_for_agent(agent.name):
            agent._code_generation_agent = None
            agent.pydantic_agent = None
            agent._mcp_servers = []
    except Exception:
        logger.warning(
            "Could not prepare MCP servers for agent %s", agent.name, exc_info=True
        )

    # A failed attempt must not be retried again by a build in this invocation.
    token = _prepared_agent.set(agent.name)
    try:
        yield
    finally:
        _prepared_agent.reset(token)


def reload_mcp_servers(agent_name: Optional[str] = None) -> List[Any]:
    """Force re-sync from ``mcp_servers.json`` and return updated servers."""
    manager = get_mcp_manager()
    manager.sync_from_config()
    return manager.get_servers_for_agent(agent_name=agent_name)


def filter_conflicting_mcp_tools(
    mcp_servers: List[Any],
    existing_tool_names: Set[str],
) -> List[Any]:
    """Hide MCP tools whose names collide with already-registered tools.

    Wraps each toolset in a public ``FilteredToolset`` (via
    ``AbstractToolset.filtered``) that drops colliding tool names at
    ``get_tools`` time — no private-attribute surgery. Objects that aren't
    pydantic-ai toolsets pass through unchanged; better to risk a duplicate
    than to drop the whole server.
    """
    if not mcp_servers or not existing_tool_names:
        return list(mcp_servers) if mcp_servers else []

    from pydantic_ai.toolsets import AbstractToolset

    conflicts = frozenset(existing_tool_names)

    def _keep(ctx: Any, tool_def: Any) -> bool:
        return tool_def.name not in conflicts

    return [
        server.filtered(_keep) if isinstance(server, AbstractToolset) else server
        for server in mcp_servers
    ]
