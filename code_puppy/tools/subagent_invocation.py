"""Sub-agent invocation tools."""

import asyncio
import inspect
import traceback
from contextlib import AsyncExitStack
from functools import partial
from typing import Set

from pydantic_ai import Agent, RunContext, UsageLimits

from code_puppy.callbacks import (
    on_agent_run_cancel,
    on_agent_run_context,
    on_wrap_pydantic_agent,
)
from code_puppy.config import get_message_limit
from code_puppy.messaging import (
    SubAgentInvocationMessage,
    SubAgentResponseMessage,
    emit_error,
    emit_info,
    emit_success,
    get_message_bus,
    get_session_context,
    set_session_context,
)
from code_puppy.tools.agent_tools import (
    AgentInvokeOutput,
    _generate_session_hash_suffix,
    _load_session_history,
    _sanitize_for_session_id,
    _save_session_history,
    _validate_session_id,
)
from code_puppy.tools.common import generate_group_id
from code_puppy.tools.subagent_context import subagent_context

# Set to track active subagent invocation tasks
_active_subagent_tasks: Set[asyncio.Task] = set()


async def _invoke_agent_impl(
    context: RunContext,
    agent_name: str,
    prompt: str,
    session_id: str | None = None,
    model_name: str | None = None,
) -> AgentInvokeOutput:
    """Invoke a sub-agent, optionally with an explicit temporary model override."""
    from code_puppy.agents.agent_manager import load_agent

    # Validate user-provided session_id if given
    if session_id is not None:
        try:
            _validate_session_id(session_id)
        except ValueError as e:
            # Return error immediately if session_id is invalid
            group_id = generate_group_id("invoke_agent", agent_name)
            emit_error(str(e), message_group=group_id)
            return AgentInvokeOutput(
                response=None,
                agent_name=agent_name,
                model_name=model_name,
                error=str(e),
            )

    # Generate a group ID for this tool execution
    group_id = generate_group_id("invoke_agent", agent_name)

    # Check if this is an existing session or a new one
    # For user-provided session_id, check if it exists
    # For None, we'll generate a new one below
    if session_id is not None:
        message_history = _load_session_history(session_id)
        is_new_session = len(message_history) == 0
    else:
        message_history = []
        is_new_session = True

    # Generate or finalize session_id
    if session_id is None:
        # Auto-generate a session ID with hash suffix for uniqueness
        # Example: "qa-expert-session-a3f2b1"
        # Sanitize agent_name to kebab-case so capitalised names like
        # "LPZ-Main-Coder" don't produce invalid session IDs.
        hash_suffix = _generate_session_hash_suffix()
        safe_agent_name = _sanitize_for_session_id(agent_name) or "agent"
        session_id = f"{safe_agent_name}-session-{hash_suffix}"
    elif is_new_session:
        # User provided a base name for a NEW session - append hash suffix
        # Example: "review-auth" -> "review-auth-a3f2b1"
        # Sanitize the user-provided base to be forgiving of casing/
        # underscores while still producing a valid kebab-case ID.
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
        )
    )

    # Save current session context and set the new one for this sub-agent
    previous_session_id = get_session_context()
    set_session_context(session_id)

    # Set browser session for browser tools (qa-kitten, etc.)
    # This allows parallel agent invocations to each have their own browser
    from code_puppy.tools.browser.browser_manager import (
        set_browser_session,
    )

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
            # Seed the wrapper's message history with the loaded session so that
            # ``make_history_processor(agent_config)`` — wired into the temp
            # agent's ``history_processors`` — mutates ``agent_config._message_history``
            # in place as the run progresses. That means on a mid-run crash we
            # can read partial progress straight off the wrapper below.
            agent_config.set_message_history(list(message_history))

            # Resolve the effective model through the agent so precedence lives
            # in one place: runtime override -> pinned model -> global default.
            effective_model_name = agent_config.get_model_name()
            models_config = ModelFactory.load_config()

            if not effective_model_name:
                raise ValueError("No model configured for sub-agent invocation")

            # Only proceed if we have a valid model configuration
            if effective_model_name not in models_config:
                raise ValueError(
                    f"Model '{effective_model_name}' not found in configuration"
                )

            model = ModelFactory.get_model(effective_model_name, models_config)
            if model is None:
                raise ValueError(
                    f"Model '{effective_model_name}' is configured but could not be "
                    "initialized. Check credentials, provider availability, and usage "
                    "limits for that model."
                )

            # Create a temporary agent instance to avoid interfering with current agent state
            instructions = agent_config.get_full_system_prompt()

            # Add AGENTS.md content to subagents.
            # ``load_puppy_rules`` lives on the builder module since the
            # base_agent split in 79dfc3c8; it's not a method on the agent.
            from code_puppy.agents._builder import load_puppy_rules

            puppy_rules = load_puppy_rules()
            if puppy_rules:
                instructions += f"\n\n{puppy_rules}"

            # NOTE: ``load_prompt`` fragments (file-permission handling, kennel
            # memory, ...) are already baked into ``get_full_system_prompt``
            # via BaseAgent, so we must NOT append them again here — doing so
            # double-injected them for class-based agents.
            from code_puppy.model_utils import prepare_prompt_for_model

            # Handle claude-code models: swap instructions, and prepend system prompt only on first message
            prepared = prepare_prompt_for_model(
                effective_model_name,
                instructions,
                prompt,
                prepend_system_to_user=is_new_session,  # Only prepend on first message
            )
            instructions = prepared.instructions
            prompt = prepared.user_prompt

            model_settings = make_model_settings(effective_model_name)

            # Get MCP servers bound to this sub-agent and warm up any with
            # ``auto_start=True``. We MUST use the async autostart variant
            # here (NOT ``start_server_sync``/``load_mcp_servers``) because
            # ``temp_agent.run(...)`` below is wrapped in
            # ``asyncio.create_task``, so pydantic-ai opens the MCP toolset's
            # anyio cancel scopes inside *that* task. The fire-and-forget
            # sync variant returns before the lifecycle task has entered
            # the MCP singleton's context, which races pydantic-ai's entry
            # and produces ``Attempted to exit a cancel scope that isn't
            # the current task's current cancel scope`` on unwind.
            # ``autostart_bound_servers_async`` awaits readiness, so by the
            # time we hand the toolsets to pydantic-ai the lifecycle task
            # already owns each cancel scope and pydantic-ai's re-entry
            # hits the ``_running_count > 0`` no-op fast-path.
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

            # Build the pydantic-ai agent. MCP servers are always included in
            # the constructor; plugins (e.g. DBOS) may swap them out at run
            # time via the ``agent_run_context`` hook if their wrapper can't
            # handle them directly.
            temp_agent = Agent(
                model=model,
                instructions=instructions,
                output_type=str,
                retries=3,
                toolsets=mcp_servers,
                history_processors=[make_history_processor(agent_config)],
                model_settings=model_settings,
            )

            # Register the tools that the agent needs
            from code_puppy.tools import register_tools_for_agent

            agent_tools = agent_config.get_available_tools()
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

            # Always use subagent_stream_handler to silence output and update console manager
            # This ensures all sub-agent output goes through the aggregated dashboard.
            # Exception: high output mode streams subagent activity inline so
            # the user sees thinking, tool calls, and responses in real time.
            #
            # In high mode we wrap the handler in a StreamingTextDetector so
            # we know whether the backend actually emitted text tokens. If it
            # didn't (buffered response), we fall back to a one-shot render
            # so the user always sees the result.
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

            # Wrap the agent run in subagent context for tracking
            with subagent_context(agent_name):
                run_ctxs = on_agent_run_context(
                    agent_config, temp_agent, group_id, mcp_servers
                )
                async with AsyncExitStack() as stack:
                    for cm in run_ctxs:
                        await stack.enter_async_context(cm)
                    task = asyncio.create_task(
                        temp_agent.run(
                            prompt,
                            message_history=message_history,
                            usage_limits=UsageLimits(request_limit=get_message_limit()),
                            event_stream_handler=stream_handler,
                        )
                    )
                    _active_subagent_tasks.add(task)

                    try:
                        result = await task
                    finally:
                        _active_subagent_tasks.discard(task)
                        if task.cancelled():
                            await on_agent_run_cancel(group_id)

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

            # Emit structured response message via MessageBus.
            # In high mode, skip the emit when streaming already rendered the
            # response to avoid a double-render if any future subscriber
            # starts rendering SubAgentResponseMessage.
            if not (is_high_mode and streamed_text):
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

            return AgentInvokeOutput(
                response=response,
                agent_name=agent_name,
                session_id=session_id,
                model_name=effective_model_name,
            )

    except Exception as e:
        # Emit clean failure summary
        emit_error(f"✗ {agent_name} failed: {str(e)}", message_group=group_id)

        # Full traceback for debugging
        error_msg = f"Error invoking agent '{agent_name}': {traceback.format_exc()}"
        emit_error(error_msg, message_group=group_id)

        # Save whatever progress the agent made before crashing. The history
        # processor keeps ``agent_config._message_history`` in sync with each
        # completed turn, so this captures every committed turn up to the
        # failure point. Best-effort: a save failure must not mask the
        # original error, so we swallow anything the save itself raises.
        try:
            partial_history = agent_config.get_message_history() if agent_config else []
            if partial_history and len(partial_history) > len(message_history):
                _save_session_history(
                    session_id=session_id,
                    message_history=partial_history,
                    agent_name=agent_name,
                    initial_prompt=prompt if is_new_session else None,
                )
                emit_info(
                    f"💾 Saved partial session '{session_id}' "
                    f"({len(partial_history)} message(s)) before error",
                    message_group=group_id,
                )
        except Exception:
            pass

        return AgentInvokeOutput(
            response=None,
            agent_name=agent_name,
            session_id=session_id,
            model_name=effective_model_name,
            error=error_msg,
        )

    finally:
        # Restore the previous session context
        set_session_context(previous_session_id)
        # Reset browser session context
        from code_puppy.tools.browser.browser_manager import (
            _browser_session_var,
        )

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

    # Keep the pydantic-ai tool schema intentionally free of **kwargs/model_name
    # while preserving Python-call compatibility with older tests/callers that
    # passed extra keywords directly. The explicit model override affordance is
    # register_invoke_agent_with_model; don't smuggle it back into invoke_agent.
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
    ) -> AgentInvokeOutput:
        """Invoke a sub-agent with an explicit one-call model override.

        Use this only when a model override is intentionally required. For
        normal delegation, use invoke_agent so the sub-agent's configured model
        is respected.

        Args:
            agent_name: Name of the sub-agent to invoke.
            prompt: Task prompt for the sub-agent.
            model_name: Configured model alias to use for this invocation only.
            session_id: Optional kebab-case session id for continuing memory.

        Returns:
            AgentInvokeOutput: Contains response, agent_name, session_id,
            effective model_name, and error fields.
        """
        normalized_model_name = model_name.strip()
        if not normalized_model_name:
            group_id = generate_group_id("invoke_agent", agent_name)
            error_msg = "model_name cannot be empty"
            emit_error(error_msg, message_group=group_id)
            return AgentInvokeOutput(
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
        )

    return invoke_agent_with_model
