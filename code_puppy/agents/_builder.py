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
from pydantic_ai.capabilities import ProcessHistory

from code_puppy.agents._compaction import make_history_processor
from code_puppy.agents._json_repair import build_tool_call_json_repair
from code_puppy.agents._model_message_transform import build_model_message_transform
from code_puppy.agents._output_limits import (
    build_response_clamp,
    build_tool_output_limits,
)
from code_puppy.agents._steer_processor import make_steer_history_processor
from code_puppy.agents.event_stream_handler import event_stream_handler
from code_puppy.callbacks import (
    on_pre_mcp_autostart,
    on_pre_mcp_autostart_sync,
    on_wrap_pydantic_agent,
)
from code_puppy.config import (
    AGENTS_MD_MAX_CHARS_DEFAULT,
    CONFIG_DIR,
    get_agents_md_max_chars,
    get_global_model_name,
    get_value,
)
from code_puppy.mcp_ import get_mcp_manager
from code_puppy.messaging import emit_error, emit_info, emit_warning
from code_puppy.model_factory import ModelFactory, make_model_settings

_AGENT_RULE_FILES = ("AGENTS.md", "AGENT.md", "agents.md", "agent.md")
_CODE_PUPPY_DIR = ".code_puppy"

# Re-export the default so existing importers keep working. The *effective*
# cap is ``get_agents_md_max_chars()`` (user override via /set); this constant
# is just the fallback used by tests and the warning notice.
AGENTS_MD_MAX_CHARS = AGENTS_MD_MAX_CHARS_DEFAULT


def _friendly_path(candidate: Path) -> str:
    """Render ``candidate`` as ``~/relative`` when it's under ``$HOME``.

    Keeps the absolute home path out of the system prompt (and out of any
    Slack paste of the agent's "please trim AGENTS.md" reply).
    """
    try:
        return f"~/{candidate.relative_to(Path.home())}"
    except ValueError:
        return str(candidate)


# BOM signatures mapped to their codecs. Check UTF-32 before UTF-16:
# the UTF-32 LE BOM starts with the UTF-16 LE BOM bytes.
_BOM_CODECS = (
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe\x00\x00", "utf-32-le"),
    (b"\x00\x00\xfe\xff", "utf-32-be"),
    (b"\xff\xfe", "utf-16-le"),
    (b"\xfe\xff", "utf-16-be"),
)


def _read_rules_text(candidate: Path) -> Optional[str]:
    """Read a rules file and detect its encoding from the BOM.

    PowerShell redirection (``echo hi > AGENTS.md``) writes UTF-16 LE
    with a BOM. A plain UTF-8 read crashes on it. This helper sniffs
    the BOM, decodes with the correct codec, and never raises. It
    returns ``None`` when the file is not readable.
    """
    try:
        raw = candidate.read_bytes()
    except OSError as exc:
        emit_warning(f"Could not read {candidate}: {exc}")
        return None
    for bom, codec in _BOM_CODECS:
        if raw.startswith(bom):
            try:
                text = raw.decode(codec)
            except UnicodeDecodeError:
                break
            # Drop the BOM character that non-sig codecs keep.
            return text.lstrip("\ufeff")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        emit_warning(
            f"{candidate} is not valid UTF-8; bad bytes were replaced. "
            f"Save the file as UTF-8 to fix this."
        )
        return raw.decode("utf-8", errors="replace")


def _truncate_agents_md(content: str, source: str, max_chars: int) -> str:
    """Cap one AGENTS.md file at ``max_chars`` with a labelled notice.

    Returns ``content`` unchanged when it's within the cap. When it overflows,
    keeps exactly the first ``max_chars`` characters of the original and
    appends a delimited warning addressed to the agent (so the agent can
    surface it to the user on the next turn). ``source`` is a human-readable
    label for the file — used in the warning so the agent can tell the user
    which specific file to trim when multiple files overflow. ``max_chars``
    is resolved once per load by the caller (see ``get_agents_md_max_chars``)
    so a session-wide ``/set`` override is honoured.
    """
    original_len = len(content)
    if original_len <= max_chars:
        return content
    dropped = original_len - max_chars
    notice = (
        f"\n\n--- AGENTS.md truncated ---\n"
        f"The {source} content was truncated: original was "
        f"{original_len:,} chars, {dropped:,} chars dropped. Please tell "
        f"the user to trim {source} below {max_chars:,} "
        f"characters so the full rules can take effect (or raise the cap "
        f"via `/set agents_md_max_chars=<int>`).\n"
        f"--- end truncation notice ---"
    )
    return content[:max_chars] + notice


def load_puppy_rules() -> Optional[str]:
    """Load AGENT(S).md from global config dir and/or the current project dir.

    Global rules (``~/.code_puppy/AGENTS.md``) come first; project-local rules
    are appended, allowing projects to override/extend global ones.

    **Search order for project rules:**

    1. ``.code_puppy/AGENTS.md`` (preferred — keeps root clean)
    2. ``./AGENTS.md`` (alternate location)

    Each file is independently truncated via :func:`_truncate_agents_md` so
    the combined system-prompt overhead stays bounded. The per-file cap is
    resolved once per call via :func:`get_agents_md_max_chars` so a user
    can raise (or lower) it with ``/set agents_md_max_chars=<int>``.

    Returns ``None`` if neither exists.
    """
    max_chars = get_agents_md_max_chars()

    global_rules: Optional[str] = None
    for name in _AGENT_RULE_FILES:
        candidate = Path(CONFIG_DIR) / name
        if candidate.exists():
            text = _read_rules_text(candidate)
            if text is None:
                continue
            global_rules = _truncate_agents_md(
                text,
                source=f"global {_friendly_path(candidate)}",
                max_chars=max_chars,
            )
            break

    project_rules: Optional[str] = None

    # Priority 1: Check .code_puppy/ directory (preferred location)
    code_puppy_dir = Path(_CODE_PUPPY_DIR)
    if code_puppy_dir.is_dir():
        for name in _AGENT_RULE_FILES:
            candidate = code_puppy_dir / name
            if candidate.exists():
                text = _read_rules_text(candidate)
                if text is None:
                    continue
                project_rules = _truncate_agents_md(
                    text,
                    source=f"project {candidate}",
                    max_chars=max_chars,
                )
                break

    # Priority 2: Fallback to project root
    if project_rules is None:
        for name in _AGENT_RULE_FILES:
            candidate = Path(name)
            if candidate.exists():
                text = _read_rules_text(candidate)
                if text is None:
                    continue
                project_rules = _truncate_agents_md(
                    text,
                    source=f"project {candidate}",
                    max_chars=max_chars,
                )
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
    from code_puppy.tools import tools_disabled

    if tools_disabled():
        # --no-tools implies no MCP toolsets either (issue #182).
        return []

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
    """Start any stopped servers bound to ``agent_name`` with auto_start=True.

    Fire-and-forget: schedules the start via ``start_server_sync`` and returns
    immediately. **The server is NOT guaranteed to be ready** when this
    returns — it just kicks off a background task. Safe for the main agent
    boot path because there's plenty of wall-clock time before the first
    ``agent.run()``. Callers that immediately spin up a pydantic-ai agent
    against the same MCP singleton (e.g. ``invoke_agent`` wrapping
    ``temp_agent.run`` in ``asyncio.create_task``) should use
    :func:`autostart_bound_servers_async` instead, which awaits readiness
    so the run starts against a fully started server.
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
    pydantic-ai MCP singleton's context and a subsequent re-entry from
    pydantic-ai inside ``agent.run()`` takes the no-op fast-path.

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


# (conversation_scope, agent_name, requested_model_name) combos already
# warned about. Scope keeps concurrent ACP sessions' warning state separate
# (subagent_invocation.py passes the parent session id; build_pydantic_agent
# leaves it ``None`` for the main-agent bucket). NOT cleared when a model
# loads again — only reset_model_fallback_warnings() resets it, so a broken
# pin doesn't re-nag per rebuild but a fresh conversation does. The pin
# itself stays a human decision (config.clear_agent_pinned_model).
_warned_model_fallbacks: Set[Tuple[Optional[str], Optional[str], str]] = set()

# Sentinel distinguishing reset() with no args (nuke everything — CLI /clear)
# from reset(scope=X) (clear only that conversation's bucket, e.g. ACP session
# creation). ``None`` is itself a valid scope (the main-agent bucket), so it
# can't double as "unset".
_UNSET = object()


def reset_model_fallback_warnings(scope: Any = _UNSET) -> None:
    """Forget which fallback warnings have already fired.

    Called with no arguments on a genuinely fresh conversation (the CLI's
    ``/clear``) to clear every scope's warning state.

    Called with an explicit ``scope`` (e.g. an ACP session boundary) to
    clear only that conversation's bucket -- notably ``scope=None`` clears
    just the shared main-agent-build bucket without wiping the per-session
    warning state other live conversations already earned via
    ``load_model_with_fallback(..., conversation_scope=<their own id>)``.
    """
    if scope is _UNSET:
        _warned_model_fallbacks.clear()
        return
    stale = {key for key in _warned_model_fallbacks if key[0] == scope}
    _warned_model_fallbacks.difference_update(stale)


def _model_fallback_fix_hint(agent_name: Optional[str]) -> str:
    """Build the how-to-fix tail appended to model fallback warnings."""
    if agent_name:
        return (
            f"Fix it with `/pin {agent_name} <model>` once a working model is "
            f"available, or `/unpin {agent_name}` to just track the global "
            "default from now on. Run `/model` to see configured models."
        )
    return "Set a valid model with `/model`, or check your models configuration."


def load_model_with_fallback(
    requested_model_name: str,
    models_config: Dict[str, Any],
    message_group: str,
    agent_name: Optional[str] = None,
    conversation_scope: Optional[str] = None,
) -> Tuple[Any, str]:
    """Load the requested model, or fall back to a sensible alternative.

    Falls back in order: the globally configured model, then any other
    configured model. Raises ``ValueError`` only if nothing loads.

    ``agent_name``, when given, scopes the model-unavailable warning to fire
    once per (conversation, agent, requested model) combo per conversation
    (see ``reset_model_fallback_warnings``) and tailors the fix instructions
    to that agent's ``/pin``/``/unpin`` commands. The agent's pinned model is
    never auto-cleared -- that stays a deliberate, human-initiated action.

    ``conversation_scope`` identifies the conversation this call belongs to
    (e.g. an ACP session id) so independent conversations sharing one
    process don't share warning-dedup state -- one session's warning must
    not silently suppress the identical warning for a completely different
    session. Leave ``None`` for the single main-agent-per-process case
    (default; unaffected by this parameter).
    """
    try:
        model = ModelFactory.get_model(requested_model_name, models_config)
        if model is None:
            raise ValueError(
                f"Model '{requested_model_name}' was found in configuration but "
                f"could not be instantiated (handler returned None)."
            )
        return model, requested_model_name
    except ValueError as exc:
        available = list(models_config.keys())
        available_str = (
            ", ".join(sorted(available)) if available else "no configured models"
        )
        warn_key = (conversation_scope, agent_name, requested_model_name)
        already_warned = warn_key in _warned_model_fallbacks
        _warned_model_fallbacks.add(warn_key)
        fix_hint = _model_fallback_fix_hint(agent_name)

        # Distinguish between "key missing", "type unsupported", and "creation failed"
        exc_msg = str(exc)
        if already_warned:
            pass
        elif "not found in configuration" in exc_msg:
            emit_warning(
                f"Model '{requested_model_name}' not found. Available models: "
                f"{available_str}. {fix_hint}",
                message_group=message_group,
            )
        elif "Unsupported model type" in exc_msg:
            model_type = models_config.get(requested_model_name, {}).get("type", "?")
            emit_warning(
                f"Model type '{model_type}' is not supported (model '{requested_model_name}'). "
                f"Available models: {available_str}. {fix_hint}",
                message_group=message_group,
            )
        elif "could not be instantiated" in exc_msg:
            emit_warning(
                f"Model '{requested_model_name}' could not be instantiated. "
                f"Available models: {available_str}. {fix_hint}",
                message_group=message_group,
            )
        else:
            emit_warning(
                f"Model '{requested_model_name}' failed: {exc_msg}. "
                f"Available models: {available_str}. {fix_hint}",
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


def _build_gpt_5_6_invoke_agent_guard_text() -> str:
    """Compose the GPT-5.6 delegation guard, interpolating the live cap.

    Reading the limit at prompt-assembly time (rather than baking it into a
    module constant) guarantees the model-facing guidance and the runtime
    enforcement in ``subagent_invocation._gpt_5_6_recursion_blocked`` can
    never drift out of sync -- they both resolve to
    ``get_subagent_recursion_limit_gpt_5_6()``.
    """
    # Local import to avoid a top-level ``code_puppy.config`` cycle -- this
    # module is imported very early during agent construction.
    from code_puppy.config import get_subagent_recursion_limit_gpt_5_6

    limit = get_subagent_recursion_limit_gpt_5_6()
    return (
        "\n\n## Sub-Agent Delegation (GPT-5.6)\n"
        "Use `invoke_agent` only for focused work that benefits from separate "
        "context or specialized tools. Handle work directly when you can. "
        "Never invoke `planning-agent`. "
        f"Hard cap: as a GPT-5.6 caller you may only invoke a sub-agent while "
        f"the resulting chain depth stays at or below {limit} "
        f"(main agent = depth 0). Do not attempt deeper chains.\n"
    )


_GPT_5_6_RUN_SHELL_COMMAND_GUARD_TEXT = """

## Shell Safety (GPT-5.6)
Before using `agent_run_shell_command`, prefer inspection and dry runs. Confirm
with the user before irreversible deletion, overwrites, history rewrites,
database or production mutations, or other actions without a clear rollback.
"""


def _is_gpt_5_6_family(model_name: Optional[str]) -> bool:
    return bool(model_name and "gpt-5.6" in model_name.lower())


def _agent_exposes_tool(agent: Any, tool_name: str) -> bool:
    try:
        return tool_name in (agent.get_available_tools() or ())
    except Exception:
        return False


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

    if _is_gpt_5_6_family(resolved_model_name):
        if _agent_exposes_tool(agent, "invoke_agent"):
            instructions += _build_gpt_5_6_invoke_agent_guard_text()
        if _agent_exposes_tool(agent, "agent_run_shell_command"):
            instructions += _GPT_5_6_RUN_SHELL_COMMAND_GUARD_TEXT

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
        agent.get_model_name(),
        models_config,
        message_group,
        agent_name=getattr(agent, "name", None),
    )
    instructions = _assemble_instructions(agent, resolved_model_name)
    mcp_servers = load_mcp_servers(agent_name=getattr(agent, "name", None))
    model_settings = make_model_settings(resolved_model_name)
    history_processor = make_history_processor(agent)
    steer_processor = make_steer_history_processor(agent)
    logical_agent_name = getattr(agent, "name", None) or agent.__class__.__name__

    def _new_pydantic_agent(toolsets: List[Any]) -> PydanticAgent:
        return PydanticAgent(
            model=model,
            # Explicit name: without it pydantic-ai infers one from the
            # caller's frame variables, so observability spans read
            # "invoke_agent pydantic_agent" instead of the logical agent name.
            name=logical_agent_name,
            instructions=instructions,
            output_type=output_type,
            retries=3,
            toolsets=toolsets,
            # Order matters: compaction first (may trim history to fit
            # context), THEN steer injection (a fresh steer must not be
            # compacted away). ProcessHistory capabilities apply in
            # registration order (replaces the deprecated
            # `history_processors=` kwarg, removed in pydantic-ai v2).
            # ToolOutputLimits reduces oversized tool returns on a different
            # hook (after_tool_execute), so its position is inert; the
            # response clamp runs before_model_request after both history
            # processors. The plugin transform wraps the final model request.
            # ToolCallJsonRepair rides the before_tool_validate seam, which
            # never interacts with the history hooks, so its position is
            # inert too.
            capabilities=[
                *build_tool_output_limits(),
                *build_tool_call_json_repair(),
                ProcessHistory(history_processor),
                ProcessHistory(steer_processor),
                build_response_clamp(),
                build_model_message_transform(logical_agent_name),
            ],
            model_settings=model_settings,
        )

    # Pass 1: build with empty toolsets so we can see what pydantic-ai + our
    # tool registry actually produced, and filter MCP to avoid name clashes.
    probe_agent = _new_pydantic_agent(toolsets=[])
    agent_tools = agent.get_available_tools()
    register_tools_for_agent(
        probe_agent,
        agent_tools,
        model_name=resolved_model_name,
        agent_name=logical_agent_name,
    )

    existing_tool_names: Set[str] = set(getattr(probe_agent, "_tools", {}) or {})
    filtered_mcp_servers = filter_conflicting_mcp_tools(
        mcp_servers, existing_tool_names
    )

    # Pass 2: real build. MCP servers always go in the constructor; plugins
    # (e.g. DBOS) may swap them at run time via ``agent_run_context``.
    final_pydantic = _new_pydantic_agent(toolsets=filtered_mcp_servers)
    register_tools_for_agent(
        final_pydantic,
        agent_tools,
        model_name=resolved_model_name,
        agent_name=logical_agent_name,
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


def build_tool_probe_for_agent(agent: Any) -> Optional[Any]:
    """Build a stripped-down pydantic agent JUST for tool introspection.

    Used by token-overhead estimators (e.g. the ``context_indicator`` plugin)
    that need to count tool docs/schemas *before* the real agent has been
    constructed. Skips MCP servers, history processors, instructions, and
    plugin wrapping — only the registered pydantic-ai tools matter here.

    Returns ``None`` if model resolution fails. The caller is responsible for
    caching the result; this is a non-trivial construction even with the
    shortcuts.
    """
    from code_puppy.tools import register_tools_for_agent

    try:
        models_config = ModelFactory.load_config()
        model, resolved_model_name = load_model_with_fallback(
            agent.get_model_name() or "",
            models_config,
            message_group=str(uuid.uuid4()),
            agent_name=getattr(agent, "name", None),
        )
    except Exception:
        return None

    try:
        probe = PydanticAgent(
            model=model,
            instructions="",
            output_type=str,
            retries=1,
            toolsets=[],
        )
        register_tools_for_agent(
            probe, agent.get_available_tools(), model_name=resolved_model_name
        )
    except Exception:
        return None
    return probe
