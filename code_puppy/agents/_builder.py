"""Pydantic-ai agent construction + MCP wiring, extracted from ``BaseAgent``.

Collapses the previous duplicated build paths and the parallel
``_create_agent_with_output_type`` method into a single ``build_pydantic_agent``
entry point. Everything else in here (puppy rules loading, MCP server loading,
model fallback, MCP tool filtering) is a pure free function.

Plugins may wrap the constructed pydantic agent via the ``wrap_pydantic_agent``
hook; see :func:`code_puppy.callbacks.on_wrap_pydantic_agent`.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from pydantic_ai import Agent as PydanticAgent
from rich.text import Text

from code_puppy.agents._compaction import make_history_processor
from code_puppy.agents._steer_processor import make_steer_history_processor
from code_puppy.agents.event_stream_handler import event_stream_handler
from code_puppy.callbacks import (
    on_pre_mcp_autostart,
    on_pre_mcp_autostart_sync,
    on_wrap_pydantic_agent,
)
from code_puppy.config import (
    CONFIG_DIR,
    get_global_model_name,
    get_value,
)
from code_puppy.mcp_ import get_mcp_manager
from code_puppy.messaging import emit_error, emit_info, emit_warning
from code_puppy.model_factory import ModelFactory, make_model_settings

_AGENT_RULE_FILES = ("AGENTS.md", "AGENT.md", "agents.md", "agent.md")
_CODE_PUPPY_DIR = ".code_puppy"


def load_puppy_rules() -> Optional[str]:
    """Load AGENT(S).md from global config dir and/or the current project dir.

    Global rules (``~/.code_puppy/AGENTS.md``) come first; project-local rules
    are appended, allowing projects to override/extend global ones.

    **Search order for project rules:**

    1. ``.code_puppy/AGENTS.md`` (preferred — keeps root clean)
    2. ``./AGENTS.md`` (alternate location)

    Returns ``None`` if neither exists.
    """
    global_rules: Optional[str] = None
    for name in _AGENT_RULE_FILES:
        candidate = Path(CONFIG_DIR) / name
        if candidate.exists():
            global_rules = candidate.read_text(encoding="utf-8-sig")
            break

    project_rules: Optional[str] = None

    # Priority 1: Check .code_puppy/ directory (preferred location)
    code_puppy_dir = Path(_CODE_PUPPY_DIR)
    if code_puppy_dir.is_dir():
        for name in _AGENT_RULE_FILES:
            candidate = code_puppy_dir / name
            if candidate.exists():
                project_rules = candidate.read_text(encoding="utf-8-sig")
                break

    # Priority 2: Fallback to project root
    if project_rules is None:
        for name in _AGENT_RULE_FILES:
            candidate = Path(name)
            if candidate.exists():
                project_rules = candidate.read_text(encoding="utf-8-sig")
                break

    rules = [r for r in (global_rules, project_rules) if r]
    return "\n\n".join(rules) if rules else None


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
    mcp_disabled = get_value("disable_mcp_servers")
    if mcp_disabled and str(mcp_disabled).lower() in ("1", "true", "yes", "on"):
        return []

    manager = get_mcp_manager()
    if agent_name:
        _autostart_bound_servers(manager, agent_name)
    return manager.get_servers_for_agent(agent_name=agent_name)


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
        try:
            status = manager.get_server_status(config.id)
            state = status.get("state")
        except Exception:  # pragma: no cover - defensive
            continue
        if state in (ServerState.RUNNING.value, ServerState.STARTING.value):
            continue
        yield server_name, config


# Module-level dedupe set: ``(agent_name, server_name)`` pairs we've already
# warned about. We don't bother with TTLs — a fresh process resets it, which
# matches "warn at most once per session per missing binding". Cleared in
# tests via ``_reset_missing_warning_cache``.
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


def _reset_missing_warning_cache() -> None:
    """Clear the warn-once cache. Test hook only."""
    _WARNED_MISSING.clear()


def _autostart_bound_servers(manager: Any, agent_name: str) -> None:
    """Start any stopped servers bound to ``agent_name`` with auto_start=True.

    Fire-and-forget: schedules the start via ``start_server_sync`` and returns
    immediately. **The server is NOT guaranteed to be ready** when this
    returns — it just kicks off a background task. Safe for the main agent
    boot path because there's plenty of wall-clock time before the first
    ``agent.run()``. **Not safe** for callers that immediately spin up a
    pydantic-ai agent against the same MCP singleton in a different task
    (e.g. ``invoke_agent`` wrapping ``temp_agent.run`` in
    ``asyncio.create_task``) — those should use
    :func:`autostart_bound_servers_async` instead, which awaits readiness so
    pydantic-ai's re-entry hits the refcount fast-path and never creates a
    competing cancel scope.
    """
    targets = list(_iter_autostart_targets(manager, agent_name))
    if not targets:
        return
    on_pre_mcp_autostart_sync(agent_name, [name for name, _ in targets])
    for server_name, config in targets:
        try:
            manager.start_server_sync(config.id)
            emit_info(
                f"Auto-started MCP server '{server_name}' for agent '{agent_name}'"
            )
        except Exception as exc:  # pragma: no cover - defensive
            emit_warning(f"Auto-start failed for MCP server '{server_name}': {exc}")


async def autostart_bound_servers_async(manager: Any, agent_name: str) -> None:
    """Async variant of :func:`_autostart_bound_servers` that waits for ready.

    Calls ``manager.start_server`` (the async API) and awaits it, so when
    this coroutine returns the lifecycle task has finished entering the
    pydantic-ai MCP singleton's context. A subsequent re-entry from
    pydantic-ai inside ``agent.run()`` will see ``_running_count > 0`` and
    take the no-op fast-path, avoiding the cross-task cancel-scope crash.

    Use this from any async caller that's about to immediately invoke a
    pydantic-ai agent against the same MCP servers (sub-agent invocation,
    notably).
    """
    targets = list(_iter_autostart_targets(manager, agent_name))
    if not targets:
        return
    await on_pre_mcp_autostart(agent_name, [name for name, _ in targets])
    for server_name, config in targets:
        try:
            await manager.start_server(config.id)
            emit_info(
                f"Auto-started MCP server '{server_name}' for agent '{agent_name}'"
            )
        except Exception as exc:  # pragma: no cover - defensive
            emit_warning(f"Auto-start failed for MCP server '{server_name}': {exc}")


def reload_mcp_servers(agent_name: Optional[str] = None) -> List[Any]:
    """Force re-sync from ``mcp_servers.json`` and return updated servers."""
    manager = get_mcp_manager()
    manager.sync_from_config()
    return manager.get_servers_for_agent(agent_name=agent_name)


def load_model_with_fallback(
    requested_model_name: str,
    models_config: Dict[str, Any],
    message_group: str,
) -> Tuple[Any, str]:
    """Load the requested model, or fall back to a sensible alternative.

    Falls back in order: the globally configured model, then any other
    configured model. Raises ``ValueError`` only if nothing loads.
    """
    try:
        return ModelFactory.get_model(
            requested_model_name, models_config
        ), requested_model_name
    except ValueError as exc:
        available = list(models_config.keys())
        available_str = (
            ", ".join(sorted(available)) if available else "no configured models"
        )
        emit_warning(
            f"Model '{requested_model_name}' not found. Available models: {available_str}",
            message_group=message_group,
        )

        candidates: List[str] = []
        global_candidate = get_global_model_name()
        if global_candidate:
            candidates.append(global_candidate)
        for candidate in available:
            if candidate not in candidates:
                candidates.append(candidate)

        for candidate in candidates:
            if not candidate or candidate == requested_model_name:
                continue
            try:
                model = ModelFactory.get_model(candidate, models_config)
                emit_info(
                    f"Using fallback model: {candidate}", message_group=message_group
                )
                return model, candidate
            except ValueError:
                continue

        friendly = (
            "No valid model could be loaded. Update the model configuration or "
            "set a valid model with `config set`."
        )
        emit_error(friendly, message_group=message_group)
        raise ValueError(friendly) from exc


def filter_conflicting_mcp_tools(
    mcp_servers: List[Any],
    existing_tool_names: Set[str],
) -> List[Any]:
    """Strip any MCP tools whose names collide with already-registered tools.

    Returns a new list of MCP toolsets (possibly containing filtered ``ToolSet``
    replacements). If a server doesn't expose a ``.tools`` attribute we pass it
    through unchanged — better to risk a duplicate than to drop the whole server.
    """
    if not mcp_servers or not existing_tool_names:
        return list(mcp_servers) if mcp_servers else []

    from pydantic_ai.tools import ToolSet

    filtered: List[Any] = []
    for server in mcp_servers:
        server_tools = getattr(server, "tools", None)
        if server_tools is None:
            filtered.append(server)
            continue

        kept = {
            name: func
            for name, func in server_tools.items()
            if name not in existing_tool_names
        }
        if not kept:
            continue  # whole server was conflicts — drop it

        replacement = ToolSet()
        for name, func in kept.items():
            replacement._tools[name] = func
        filtered.append(replacement)

    return filtered


def _assemble_instructions(agent: Any, resolved_model_name: str) -> str:
    """Compose full system prompt + puppy rules + extended-thinking note."""
    from code_puppy.model_utils import prepare_prompt_for_model
    from code_puppy.tools import (
        EXTENDED_THINKING_PROMPT_NOTE,
        has_extended_thinking_active,
    )

    instructions = agent.get_full_system_prompt()
    puppy_rules = load_puppy_rules()
    if puppy_rules:
        instructions += f"\n{puppy_rules}"

    if has_extended_thinking_active(resolved_model_name):
        instructions += EXTENDED_THINKING_PROMPT_NOTE

    prepared = prepare_prompt_for_model(
        agent.get_model_name(), instructions, "", prepend_system_to_user=False
    )
    return prepared.instructions


def build_pydantic_agent(
    agent: Any,
    output_type: Any = str,
    message_group: Optional[str] = None,
) -> Any:
    """Build (and wire up) the pydantic-ai agent for ``agent``.

    Replaces the old ``reload_code_generation_agent`` + ``_create_agent_with_output_type``
    pair. Side effects on ``agent``:

    - ``agent._puppy_rules = None`` (invalidates any cached rules)
    - ``agent.cur_model``             ← resolved pydantic-ai model
    - ``agent._last_model_name``      ← resolved model name
    - ``agent.pydantic_agent``        ← the final (possibly plugin-wrapped) agent
    - ``agent._code_generation_agent`` ← same as ``pydantic_agent``
    - ``agent._mcp_servers``          ← MCP toolsets (post-filter)

    The build happens in two passes: we construct once with ``toolsets=[]`` so
    we can introspect registered tool names, then rebuild with MCP servers
    filtered against those names to prevent collisions. Plugins may wrap the
    final pydantic agent via the ``wrap_pydantic_agent`` hook (e.g. to swap
    in a durable-exec wrapper).
    """
    from code_puppy.tools import register_tools_for_agent

    agent._puppy_rules = None
    message_group = message_group or str(uuid.uuid4())

    models_config = ModelFactory.load_config()
    model, resolved_model_name = load_model_with_fallback(
        agent.get_model_name(), models_config, message_group
    )
    instructions = _assemble_instructions(agent, resolved_model_name)
    mcp_servers = load_mcp_servers(agent_name=getattr(agent, "name", None))
    model_settings = make_model_settings(resolved_model_name)
    history_processor = make_history_processor(agent)
    steer_processor = make_steer_history_processor(agent)

    def _new_pydantic_agent(toolsets: List[Any]) -> PydanticAgent:
        return PydanticAgent(
            model=model,
            instructions=instructions,
            output_type=output_type,
            retries=3,
            toolsets=toolsets,
            # Order is critical: compaction first (may trim history to fit
            # context), THEN steer injection (the steer must NOT be subject
            # to compaction on this call — it just arrived).
            history_processors=[history_processor, steer_processor],
            model_settings=model_settings,
        )

    # Pass 1: build with empty toolsets so we can see what pydantic-ai + our
    # tool registry actually produced, and filter MCP to avoid name clashes.
    probe_agent = _new_pydantic_agent(toolsets=[])
    agent_tools = agent.get_available_tools()
    register_tools_for_agent(probe_agent, agent_tools, model_name=resolved_model_name)

    existing_tool_names: Set[str] = set(getattr(probe_agent, "_tools", {}) or {})
    filtered_mcp_servers = filter_conflicting_mcp_tools(
        mcp_servers, existing_tool_names
    )

    dropped = len(mcp_servers) - len(filtered_mcp_servers)
    if dropped:
        emit_info(
            Text.from_markup(f"[dim]Filtered {dropped} conflicting MCP tools[/dim]")
        )

    # Pass 2: real build. MCP servers are always included in the constructor;
    # plugins (e.g. DBOS) may swap them out at run time via the
    # ``agent_run_context`` hook if their wrapper can't handle them directly.
    final_pydantic = _new_pydantic_agent(toolsets=filtered_mcp_servers)
    register_tools_for_agent(
        final_pydantic, agent_tools, model_name=resolved_model_name
    )

    agent.cur_model = model
    agent._last_model_name = resolved_model_name
    agent._mcp_servers = filtered_mcp_servers

    wrapped = on_wrap_pydantic_agent(
        agent,
        final_pydantic,
        event_stream_handler=event_stream_handler,
        message_group=message_group,
        kind="main",
    )
    agent.pydantic_agent = wrapped
    agent._code_generation_agent = wrapped
    return wrapped
