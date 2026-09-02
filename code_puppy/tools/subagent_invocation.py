"""Sub-agent invocation tools."""

import asyncio
import inspect
import sys
import time
import traceback
from contextlib import AsyncExitStack
from datetime import datetime, timezone
from functools import partial
from typing import Set

from pydantic_ai import Agent, RunContext, UsageLimits
from pydantic_ai.capabilities import ProcessHistory

from code_puppy.agent_execution_context import executing_agent_context
from code_puppy.callbacks import (
    on_agent_run_cancel,
    on_agent_run_context,
    on_wrap_pydantic_agent,
)
from code_puppy.config import (
    get_message_limit,
    get_subagent_recursion_limit,
    get_subagent_recursion_limit_gpt_5_6,
)
from code_puppy.i18n import t
from code_puppy.messaging import (
    SubAgentInvocationMessage,
    SubAgentResponseMessage,
    emit_error,
    emit_info,
    emit_success,
    emit_warning,
    get_message_bus,
    get_session_context,
    set_session_context,
)
from code_puppy.tools.agent_tools import (
    AgentInvokeOutput,
    AgentInvokeWithModelOutput,
    _generate_session_hash_suffix,
    _load_session_history,
    _sanitize_for_session_id,
    _save_session_history,
    _validate_session_id,
)
from code_puppy.tools.common import generate_group_id
from code_puppy.tools.subagent_context import (
    get_conversation_root_id,
    get_subagent_chain,
    get_subagent_depth,
    get_subagent_model_name,
    subagent_context,
)
from code_puppy.tools.subagent_usage_metrics import (
    _safe_usage_metrics,
    build_invoke_output,
    extract_final_context_tokens,
    extract_per_request_usage,
)

# Set to track active subagent invocation tasks
_active_subagent_tasks: Set[asyncio.Task] = set()

# Sub-agents interrupted by cancellation, drained into the parent's history at
# the next run start (single seam shared by invoke_agent and /fork). Same-loop
# populate/drain makes a plain list safe.
_interrupted_subagents: list[dict] = []


def record_interrupted_subagent(
    *, agent_name: str, session_id: str, saved_count: int | None
) -> None:
    """Remember that ``agent_name``'s session was interrupted."""
    _interrupted_subagents.append(
        {
            "agent_name": agent_name,
            "session_id": session_id,
            "saved_count": saved_count,
        }
    )


def drain_interrupted_subagents() -> list[dict]:
    """Return and clear all pending interrupted-subagent records."""
    drained = list(_interrupted_subagents)
    _interrupted_subagents.clear()
    return drained


def _subagent_recursion_blocked() -> bool:
    """Return whether another invocation would exceed the configured depth."""
    return get_subagent_depth() >= get_subagent_recursion_limit()


def _gpt_5_6_recursion_blocked() -> bool:
    """Enforce the GPT-5.6 overlay cap on resulting sub-agent chain depth.

    The rule keys off the *immediate* caller's model (via the
    ``subagent_model_name`` contextvar). An earlier GPT-5.6 ancestor that
    has since handed off to a non-GPT-5.6 sub-agent is intentionally not
    penalised -- broadening to a full-chain scan would be a policy change
    beyond this cap. The limit itself is user-tunable via the
    ``subagent_recursion_limit_gpt_5_6`` config key.
    """
    from code_puppy.agents._builder import _is_gpt_5_6_family

    if not _is_gpt_5_6_family(get_subagent_model_name()):
        return False
    attempted_depth = get_subagent_depth() + 1
    return attempted_depth > get_subagent_recursion_limit_gpt_5_6()


def recursion_guard_error(agent_name: str) -> str | None:
    """Verdict of the recursion guards: the denial message, or None if allowed.

    Single source of truth for both custodies -- the
    ``SubagentRecursionGuard`` capability (``wrap_tool_execute`` seam, wired
    at both pydantic-agent construction sites) and the in-tool guest
    fallback in ``_invoke_agent_impl`` -- so the two verdicts can never
    drift.
    """
    if _subagent_recursion_blocked():
        return t(
            "subagent.recursion_limit_reached",
            limit=get_subagent_recursion_limit(),
            agent=agent_name,
        )
    if _gpt_5_6_recursion_blocked():
        return t(
            "subagent.gpt_5_6_recursion_blocked",
            agent=agent_name,
            depth=get_subagent_depth() + 1,
            limit=get_subagent_recursion_limit_gpt_5_6(),
        )
    return None


def denied_invocation_output(
    *,
    agent_name: str,
    model_name: str | None,
    include_usage_metrics: bool,
    error: str,
) -> AgentInvokeOutput:
    """Emit the denial and build the model-facing error output.

    Shared by both recursion-guard custodies so the user-visible emit and
    the model-visible output stay byte-identical regardless of which layer
    denies. Mirrors the historical blocked path exactly: ``session_id`` is
    deliberately left ``None`` even when the caller supplied one.
    """
    emit_error(error, message_group=generate_group_id("invoke_agent", agent_name))
    return build_invoke_output(
        include_usage_metrics=include_usage_metrics,
        response=None,
        agent_name=agent_name,
        model_name=model_name,
        error=error,
    )


def _subagent_identity_prompt(agent_name: str) -> str:
    """Build explicit nesting context for the child agent's system prompt."""
    depth = get_subagent_depth() + 1
    limit = get_subagent_recursion_limit()
    chain = " -> ".join(("main agent", *get_subagent_chain(), agent_name))
    remaining = max(limit - depth, 0)
    return f"""## Sub-agent execution context (mandatory)

You are the sub-agent `{agent_name}`, not the main agent. Your nesting depth is
{depth} (main agent = 0). Invocation chain: {chain}. The configured maximum
sub-agent depth is {limit}; {remaining} deeper level(s) remain.

Complete your assigned task directly. NEVER invoke yourself, an agent already in
the invocation chain, or another agent merely to repeat/continue your own role.
Default to no further delegation. If delegation is truly essential, invoke at
most one child level for a narrowly scoped task, tell that child to complete the
work directly without further delegation, then finish the task yourself. Do not
create recursive, cyclic, or open-ended agent chains."""


def _contains_cancellation(exc: BaseException) -> bool:
    """True if ``exc`` is a cancellation, including one nested in a group.

    Async teardown (e.g. ``AsyncExitStack``) can wrap ``CancelledError`` in a
    ``BaseExceptionGroup``. Such a shape is still an interruption, not a crash,
    so it must follow the cancellation path rather than the failure path.
    """
    if isinstance(exc, asyncio.CancelledError):
        return True
    if isinstance(exc, BaseExceptionGroup):
        return any(_contains_cancellation(inner) for inner in exc.exceptions)
    return False


def _save_partial_session(
    *,
    agent_config,
    session_id: str,
    agent_name: str,
    baseline_count: int,
    initial_prompt: str | None,
) -> int | None:
    """Persist any progress made before an interruption or crash.

    The history processor keeps ``agent_config._message_history`` in sync with
    each completed turn, so this captures every committed turn up to the exit
    point. Best-effort: a save failure must never mask the original error, so
    anything the save itself raises is swallowed.

    Returns the saved message count, or ``None`` if nothing was persisted.
    """
    try:
        partial_history = agent_config.get_message_history() if agent_config else []
        if partial_history and len(partial_history) > baseline_count:
            _save_session_history(
                session_id=session_id,
                message_history=partial_history,
                agent_name=agent_name,
                initial_prompt=initial_prompt,
            )
            return len(partial_history)
    except Exception:
        pass
    return None


async def _invoke_agent_impl(
    context: RunContext,
    agent_name: str,
    prompt: str,
    session_id: str | None = None,
    model_name: str | None = None,
    emit_response_message: bool = True,
    include_usage_metrics: bool = False,
    is_fork: bool = False,
) -> AgentInvokeOutput:
    """Invoke a sub-agent, optionally suppressing its standard response message.

    ``include_usage_metrics`` is set by ``invoke_agent_with_model`` only; it
    gates BOTH the returned type (``AgentInvokeWithModelOutput`` vs the plain
    ``AgentInvokeOutput``) and whether any timing/usage instrumentation runs
    at all, so ``invoke_agent`` callers see zero behavioral or performance
    change from before this instrumentation existed.

    ``is_fork`` is set by the ``/fork`` plugin (a companion package,
    ``code_puppy_core_plugins.fork.register_callbacks::_run_fork``, which
    feature-detects this kwarg via ``inspect.signature`` before passing it --
    this repo has no direct caller). It flags the emitted
    ``SubAgentInvocationMessage`` so renderers can show a distinct banner
    instead of the generic tool-call one.
    """
    from code_puppy.agents.agent_manager import load_agent

    group_id = generate_group_id("invoke_agent", agent_name)
    # Guest custody of the recursion guards: agents built by code_puppy carry
    # ``SubagentRecursionGuard`` (wrap_tool_execute), which denies before this
    # body runs, making this re-check an unreachable no-op there. It stays for
    # direct callers and foreign registrations of the invoke tools. The shared
    # verdict/denial helpers keep both custodies byte-identical.
    error = recursion_guard_error(agent_name)
    if error:
        return denied_invocation_output(
            agent_name=agent_name,
            model_name=model_name,
            include_usage_metrics=include_usage_metrics,
            error=error,
        )

    # Validate user-provided session_id if given
    if session_id is not None:
        try:
            _validate_session_id(session_id)
        except ValueError as e:
            # Return error immediately if session_id is invalid
            emit_error(str(e), message_group=group_id)
            return build_invoke_output(
                include_usage_metrics=include_usage_metrics,
                response=None,
                agent_name=agent_name,
                model_name=model_name,
                error=str(e),
            )

    # Existing user-provided session, or new (None → generated below)?
    if session_id is not None:
        message_history = _load_session_history(session_id)
        is_new_session = len(message_history) == 0
    else:
        message_history = []
        is_new_session = True

    # Generate or finalize session_id
    if session_id is None:
        # Auto-generate a kebab-cased ``<agent>-session-<hash>`` ID (capitalised
        # names like "LPZ-Main-Coder" would otherwise produce invalid IDs).
        hash_suffix = _generate_session_hash_suffix()
        safe_agent_name = _sanitize_for_session_id(agent_name) or "agent"
        session_id = f"{safe_agent_name}-session-{hash_suffix}"
    elif is_new_session:
        # New session with user base name: append hash suffix, sanitized to a
        # valid kebab-case ID (forgiving of casing/underscores).
        hash_suffix = _generate_session_hash_suffix()
        safe_base = _sanitize_for_session_id(session_id) or "session"
        session_id = f"{safe_base}-{hash_suffix}"
    # else: continuing existing session, use session_id as-is

    # Lazy imports to avoid circular dependency
    from code_puppy.agents.subagent_stream_handler import subagent_stream_handler

    # Emit structured invocation message via MessageBus
    bus = get_message_bus()
    bus.emit(
        SubAgentInvocationMessage(
            agent_name=agent_name,
            session_id=session_id,
            prompt=prompt,
            is_new_session=is_new_session,
            message_count=len(message_history),
            model_name=model_name,
            is_fork=is_fork,
        )
    )

    # Save current session context and set the new one for this sub-agent
    previous_session_id = get_session_context()
    set_session_context(session_id)

    # Keep parallel browser agents isolated without importing Playwright on Android.
    browser_session_token = None
    if sys.platform != "android":
        from code_puppy.tools.browser.browser_manager import set_browser_session

        browser_session_token = set_browser_session(f"browser-{session_id}")

    # Bound up-front so the ``except`` block can always reach for it even
    # if load_agent() itself fails before assignment.
    agent_config = None
    effective_model_name = model_name

    try:
        # Lazy import to break circular dependency with messaging module
        from code_puppy.model_factory import ModelFactory, make_model_settings

        # Load the specified agent config
        agent_config = load_agent(agent_name)

        with agent_config.temporary_model_name_override(model_name):
            # Seed history so make_history_processor (wired into history_processors)
            # mutates ``agent_config._message_history`` in place — letting us read
            # partial progress off the wrapper after a mid-run crash.
            agent_config.set_message_history(list(message_history))

            # Resolve the effective model through the agent so precedence lives
            # in one place: runtime override -> pinned model -> global default.
            requested_model_name = agent_config.get_model_name()
            models_config = ModelFactory.load_config()

            if not requested_model_name:
                raise ValueError("No model configured for sub-agent invocation")

            # A pinned/ambient model that has vanished from config (removed entry,
            # unsupported type, missing creds) degrades like the main agent: warn +
            # fall back via ``load_model_with_fallback``. An EXPLICIT override is a
            # different contract — a bad one stays a hard per-call failure.
            from code_puppy.agents._builder import load_model_with_fallback

            if model_name:
                try:
                    model = ModelFactory.get_model(requested_model_name, models_config)
                    if model is None:
                        raise ValueError(
                            f"Model '{requested_model_name}' is configured but "
                            "could not be initialized. Check credentials, "
                            "provider availability, and usage limits for that "
                            "model."
                        )
                except ValueError as exc:
                    available = list(models_config.keys())
                    available_str = (
                        ", ".join(sorted(available))
                        if available
                        else "no configured models"
                    )
                    raise ValueError(
                        f"Explicit model override '{requested_model_name}' is "
                        f"unavailable: {exc} Available models: {available_str}."
                    ) from exc
                effective_model_name = requested_model_name
            else:
                model, effective_model_name = load_model_with_fallback(
                    requested_model_name,
                    models_config,
                    group_id,
                    agent_name=agent_name,
                    # Scope warn-once dedup to the conversation's ROOT identity
                    # (ContextVar set at the top-level boundary), NOT this call's
                    # session_id or the shared message-bus context: concurrent
                    # conversations stay separate, and nested A→B→C invocations
                    # share one id so "once per conversation" holds tree-wide.
                    conversation_scope=get_conversation_root_id(),
                )

            # Create a temporary agent instance to avoid interfering with current agent state
            instructions = agent_config.get_full_system_prompt()
            instructions += f"\n\n{_subagent_identity_prompt(agent_name)}"

            # AGENTS.md deliberately NOT injected into sub-agents: those are
            # user-facing steering for the MAIN agent and would create recursion
            # traps (e.g. "always invoke xyz" makes xyz invoke itself).

            # NOTE: load_prompt fragments are already baked into get_full_system_prompt
            # via BaseAgent — appending again would double-inject them.
            from code_puppy.model_utils import prepare_prompt_for_model

            # Model-family prep (e.g. claude-code): may split off a standing
            # system_prompt part, or touch the user prompt on the first message.
            prepared = prepare_prompt_for_model(
                effective_model_name,
                instructions,
                prompt,
                prepend_system_to_user=is_new_session,  # Only prepend on first message
            )
            instructions = prepared.instructions
            prompt = prepared.user_prompt

            model_settings = make_model_settings(
                effective_model_name,
                overrides=agent_config.get_model_settings_overrides(),
            )

            # Warm up bound MCP servers with the ASYNC autostart variant: the run
            # is wrapped in create_task, and the sync variant races pydantic-ai's
            # cancel-scope entry ("Attempted to exit a cancel scope..."). Awaiting
            # readiness ensures the lifecycle task owns scopes before handoff.
            from code_puppy.agents._builder import autostart_bound_servers_async
            from code_puppy.config import get_value
            from code_puppy.mcp_ import get_mcp_manager

            mcp_servers = []
            mcp_disabled = get_value("disable_mcp_servers")
            if not (
                mcp_disabled and str(mcp_disabled).lower() in ("1", "true", "yes", "on")
            ):
                manager = get_mcp_manager()
                bound_agent_name = getattr(agent_config, "name", None)
                if bound_agent_name:
                    await autostart_bound_servers_async(manager, bound_agent_name)
                mcp_servers = manager.get_servers_for_agent(agent_name=bound_agent_name)

            from code_puppy.agents._compaction import make_history_processor
            from code_puppy.agents._subagent_recursion import (
                build_subagent_recursion_guard,
            )
            from code_puppy.agents._model_message_transform import (
                build_model_message_transform,
            )

            # Build the pydantic-ai agent. MCP servers always included; plugins
            # (e.g. DBOS) may swap them via the agent_run_context hook.
            agent_tools = agent_config.get_available_tools()
            temp_agent = Agent(
                model=model,
                # Explicit name: without it pydantic-ai infers one from the
                # caller's frame variables, so every sub-agent's observability
                # span reads "invoke_agent temp_agent" instead of the logical
                # agent name (e.g. "invoke_agent web-retriever").
                name=agent_name,
                system_prompt=prepared.system_prompt_parts,
                instructions=instructions,
                output_type=str,
                retries=3,
                toolsets=mcp_servers,
                # ProcessHistory capability replaces the deprecated
                # `history_processors=` kwarg (removed in pydantic-ai v2).
                capabilities=[
                    ProcessHistory(make_history_processor(agent_config)),
                    build_model_message_transform(agent_name),
                    # Recursion guards ride the wrap_tool_execute seam so a
                    # sub-agent's own invoke_agent calls are denied before
                    # the tool body runs. Sole wrap_tool_execute implementer,
                    # so position is inert.
                    *build_subagent_recursion_guard(agent_tools),
                ],
                model_settings=model_settings,
            )

            # Register the tools that the agent needs
            from code_puppy.tools import register_tools_for_agent

            register_tools_for_agent(
                temp_agent, agent_tools, model_name=effective_model_name
            )

            # Allow plugins to wrap the agent (e.g. DBOS durable-exec wrapper).
            temp_agent = on_wrap_pydantic_agent(
                agent_config,
                temp_agent,
                event_stream_handler=None,
                message_group=group_id,
                kind="subagent",
            )

            # subagent_stream_handler silences sub-agent output (aggregated
            # dashboard); high mode streams it inline via a StreamingTextDetector,
            # falling back to one-shot render if no text tokens were emitted.
            from code_puppy.config import get_output_level

            is_high_mode = get_output_level() == "high"
            streaming_detector = None

            if is_high_mode:
                from code_puppy.agents._non_streaming_render import (
                    StreamingTextDetector,
                )
                from code_puppy.agents.event_stream_handler import (
                    event_stream_handler as _main_stream_handler,
                )

                streaming_detector = StreamingTextDetector(_main_stream_handler)
                stream_handler = streaming_detector
            else:
                stream_handler = partial(subagent_stream_handler, session_id=session_id)

            with (
                subagent_context(agent_name, effective_model_name),
                executing_agent_context(agent_config),
            ):
                run_ctxs = on_agent_run_context(
                    agent_config, temp_agent, group_id, mcp_servers
                )
                async with AsyncExitStack() as stack:
                    for cm in run_ctxs:
                        await stack.enter_async_context(cm)
                    # streaming_retry on the model stream (5xx SSE / dropped socket)
                    # with the SUBAGENT retry profile — this raw temp_agent.run()
                    # was the only unprotected stream call; 5xx surfaced to the REPL.
                    from code_puppy.agents.retry_profiles import (
                        make_streaming_retry,
                    )

                    @make_streaming_retry(
                        "subagent",
                        effective_model_name,
                        # Growing history = real progress -> refresh the no-progress
                        # retry budget (completed steps are checkpointed in place).
                        progress_fn=lambda: len(
                            agent_config.get_message_history() or []
                        ),
                    )
                    async def _run_subagent():
                        # Resume from live checkpoint so a retried turn reuses
                        # completed steps instead of redoing them.
                        return await temp_agent.run(
                            prompt,
                            message_history=agent_config.get_message_history(),
                            usage_limits=UsageLimits(request_limit=get_message_limit()),
                            event_stream_handler=stream_handler,
                        )

                    # Time the full run (incl. retries) so duration_ms reflects real
                    # latency: UTC ISO-8601 start/end + monotonic duration. Only for
                    # invoke_agent_with_model (include_usage_metrics=True).
                    run_started = time.perf_counter() if include_usage_metrics else None
                    start_time = (
                        datetime.now(timezone.utc).isoformat()
                        if include_usage_metrics
                        else None
                    )
                    task = asyncio.create_task(_run_subagent())
                    _active_subagent_tasks.add(task)

                    try:
                        result = await task
                    finally:
                        _active_subagent_tasks.discard(task)
                        if task.cancelled():
                            await on_agent_run_cancel(group_id)

                    # Capture usage + latency as close to the run boundary as
                    # possible, before any rendering/history/emit bookkeeping.
                    if include_usage_metrics:
                        end_time = datetime.now(timezone.utc).isoformat()
                        duration_ms = (time.perf_counter() - run_started) * 1000.0
                        usage_metrics = _safe_usage_metrics(result)
                    else:
                        end_time = None
                        duration_ms = None
                        usage_metrics = None

                # Still inside subagent_context: if high mode and streaming
                # didn't produce any text, fall back to the one-shot renderer
                # so the user always sees the response.
                streamed_text = (
                    streaming_detector is not None and streaming_detector.streamed_text
                )
                if is_high_mode and not streamed_text:
                    from code_puppy.agents._non_streaming_render import (
                        render_result_without_streaming,
                    )

                    render_result_without_streaming(result)

            # Extract the response from the result
            response = result.output

            # Update the session history with the new messages from this interaction
            # The result contains all_messages which includes the full conversation
            updated_history = result.all_messages()

            # Save to filesystem (include initial prompt only for new sessions)
            _save_session_history(
                session_id=session_id,
                message_history=updated_history,
                agent_name=agent_name,
                initial_prompt=prompt if is_new_session else None,
            )

            # Emit via MessageBus; skip in high mode when streaming already
            # rendered the response (avoids future double-render).
            if emit_response_message and not (is_high_mode and streamed_text):
                bus.emit(
                    SubAgentResponseMessage(
                        agent_name=agent_name,
                        session_id=session_id,
                        response=response,
                        message_count=len(updated_history),
                    )
                )

            # Emit clean completion summary
            emit_success(
                f"✓ {agent_name} completed successfully", message_group=group_id
            )

            return build_invoke_output(
                include_usage_metrics=include_usage_metrics,
                response=response,
                agent_name=agent_name,
                session_id=session_id,
                model_name=effective_model_name,
                usage_metrics=usage_metrics,
                per_request_usage=(
                    # all_messages() would re-report calls from earlier runs.
                    extract_per_request_usage(result.new_messages())
                    if include_usage_metrics
                    else None
                ),
                final_context_tokens=(
                    extract_final_context_tokens(result.new_messages())
                    if include_usage_metrics
                    else None
                ),
                start_time=start_time,
                end_time=end_time,
                duration_ms=duration_ms,
            )

    except BaseException as e:
        interrupted = isinstance(
            e, (asyncio.CancelledError, KeyboardInterrupt)
        ) or _contains_cancellation(e)

        if interrupted:
            # CancelledError derives from BaseException, so it slipped past the
            # old ``except Exception`` save path. Persist progress, tell the user
            # how to resume, then re-raise (persistence must not mask cancel).
            saved = _save_partial_session(
                agent_config=agent_config,
                session_id=session_id,
                agent_name=agent_name,
                baseline_count=len(message_history),
                initial_prompt=prompt if is_new_session else None,
            )
            detail = (
                f"{saved} message(s) saved"
                if saved is not None
                else "no new messages to save"
            )
            # Durable breadcrumb for the parent: the awaited call would be pruned
            # as dangling, so note the delegation; injected at the next run start.
            record_interrupted_subagent(
                agent_name=agent_name,
                session_id=session_id,
                saved_count=saved,
            )
            emit_warning(
                f"{agent_name} interrupted - {detail}. "
                f"Resume: invoke_agent(session_id='{session_id}')",
                message_group=group_id,
            )
            raise

        if not isinstance(e, Exception):
            # Non-cancellation BaseException (e.g. SystemExit): don't swallow.
            raise

        # Emit clean failure summary
        emit_error(f"{agent_name} failed: {str(e)}", message_group=group_id)

        # Full traceback for debugging
        error_msg = f"Error invoking agent '{agent_name}': {traceback.format_exc()}"
        emit_error(error_msg, message_group=group_id)

        # Save whatever progress the agent made before crashing.
        saved = _save_partial_session(
            agent_config=agent_config,
            session_id=session_id,
            agent_name=agent_name,
            baseline_count=len(message_history),
            initial_prompt=prompt if is_new_session else None,
        )
        if saved is not None:
            emit_info(
                f"Saved partial session '{session_id}' "
                f"({saved} message(s)) before error",
                message_group=group_id,
            )

        return build_invoke_output(
            include_usage_metrics=include_usage_metrics,
            response=None,
            agent_name=agent_name,
            session_id=session_id,
            model_name=effective_model_name,
            error=error_msg,
        )

    finally:
        # Restore the previous session context
        set_session_context(previous_session_id)
        if browser_session_token is not None:
            from code_puppy.tools.browser.browser_manager import _browser_session_var

            _browser_session_var.reset(browser_session_token)


def register_invoke_agent(agent):
    """Register the default invoke_agent tool with no model override affordance."""

    async def invoke_agent(
        context: RunContext,
        agent_name: str,
        prompt: str,
        session_id: str | None = None,
        **_ignored_kwargs,
    ) -> AgentInvokeOutput:
        """Invoke a specific sub-agent using its configured model.

        Delegation safety: never invoke yourself or an agent already in the
        invocation chain. Default to doing the work directly. If delegation is
        essential, go at most one level deeper for one narrowly scoped task and
        explicitly tell that child not to delegate further. Never create cyclic,
        recursive, or open-ended delegation chains.

        Args:
            agent_name: Name of the sub-agent to invoke.
            prompt: Task prompt for the sub-agent.
            session_id: Optional kebab-case session id for continuing memory.

        Returns:
            AgentInvokeOutput: Contains response, agent_name, session_id,
            effective model_name, and error fields.
        """
        return await _invoke_agent_impl(
            context=context,
            agent_name=agent_name,
            prompt=prompt,
            session_id=session_id,
            model_name=None,
        )

    # Keep the schema free of **kwargs/model_name (Python-call compat only); the
    # explicit model override is register_invoke_agent_with_model — not here.
    invoke_agent.__signature__ = inspect.Signature(
        parameter
        for parameter in inspect.signature(invoke_agent).parameters.values()
        if parameter.kind is not inspect.Parameter.VAR_KEYWORD
    )

    return agent.tool(invoke_agent)


def register_invoke_agent_with_model(agent):
    """Register the explicit model-override sub-agent invocation tool."""

    @agent.tool
    async def invoke_agent_with_model(
        context: RunContext,
        agent_name: str,
        prompt: str,
        model_name: str,
        session_id: str | None = None,
    ) -> AgentInvokeWithModelOutput:
        """Invoke a sub-agent with an explicit one-call model override.

        Use this only when a model override is intentionally required. For
        normal delegation, use invoke_agent so the sub-agent's configured model
        is respected. Never invoke yourself or an agent already in the invocation
        chain. Default to doing the work directly; if delegation is essential,
        go at most one level deeper for one narrowly scoped task, tell that child
        not to delegate further, and never create recursive or cyclic chains.

        Args:
            agent_name: Name of the sub-agent to invoke.
            prompt: Task prompt for the sub-agent.
            model_name: Configured model alias to use for this invocation only.
            session_id: Optional kebab-case session id for continuing memory.

        Returns:
            AgentInvokeWithModelOutput: Contains response, agent_name,
            session_id, effective model_name, and error fields. On a
            successful run it also reports usage and timing; those fields are
            None on errors. Use per_request_usage for pricing. invoke_agent is
            unaffected.
        """
        normalized_model_name = model_name.strip()
        if not normalized_model_name:
            group_id = generate_group_id("invoke_agent", agent_name)
            error_msg = "model_name cannot be empty"
            emit_error(error_msg, message_group=group_id)
            return AgentInvokeWithModelOutput(
                response=None,
                agent_name=agent_name,
                session_id=session_id,
                model_name=model_name,
                error=error_msg,
            )
        return await _invoke_agent_impl(
            context=context,
            agent_name=agent_name,
            prompt=prompt,
            session_id=session_id,
            model_name=normalized_model_name,
            include_usage_metrics=True,
        )

    return invoke_agent_with_model
