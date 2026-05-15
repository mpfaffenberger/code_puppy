import asyncio
import logging
import traceback
from typing import Any, Callable, Dict, List, Literal, Optional

PhaseType = Literal[
    "startup",
    "shutdown",
    "invoke_agent",
    "agent_exception",
    "version_check",
    "edit_file",
    "create_file",
    "replace_in_file",
    "delete_snippet",
    "delete_file",
    "run_shell_command",
    "load_model_config",
    "load_models_config",
    "load_prompt",
    "agent_reload",
    "custom_command",
    "custom_command_help",
    "file_permission",
    "pre_tool_call",
    "post_tool_call",
    "stream_event",
    "register_tools",
    "register_agents",
    "register_model_type",
    "get_model_system_prompt",
    "prepare_model_prompt",
    "agent_run_start",
    "agent_run_end",
    "agent_run_result",
    "register_mcp_catalog_servers",
    "register_browser_types",
    "register_model_providers",
    "message_history_processor_start",
    "message_history_processor_end",
    "on_message",
    "wrap_pydantic_agent",
    "agent_run_context",
    "agent_run_cancel",
    "should_skip_fallback_render",
    "pre_mcp_autostart",
    "interactive_turn_end",
    "interactive_turn_cancel",
    "agent_pause_requested",
]
CallbackFunc = Callable[..., Any]

_callbacks: Dict[PhaseType, List[CallbackFunc]] = {
    "startup": [],
    "shutdown": [],
    "invoke_agent": [],
    "agent_exception": [],
    "version_check": [],
    "edit_file": [],
    "create_file": [],
    "replace_in_file": [],
    "delete_snippet": [],
    "delete_file": [],
    "run_shell_command": [],
    "load_model_config": [],
    "load_models_config": [],
    "load_prompt": [],
    "agent_reload": [],
    "custom_command": [],
    "custom_command_help": [],
    "file_permission": [],
    "pre_tool_call": [],
    "post_tool_call": [],
    "stream_event": [],
    "register_tools": [],
    "register_agents": [],
    "register_model_type": [],
    "get_model_system_prompt": [],
    "prepare_model_prompt": [],
    "agent_run_start": [],
    "agent_run_end": [],
    "agent_run_result": [],
    "register_mcp_catalog_servers": [],
    "register_browser_types": [],
    "register_model_providers": [],
    "message_history_processor_start": [],
    "message_history_processor_end": [],
    "on_message": [],
    "wrap_pydantic_agent": [],
    "agent_run_context": [],
    "agent_run_cancel": [],
    "should_skip_fallback_render": [],
    "pre_mcp_autostart": [],
    "interactive_turn_end": [],
    "interactive_turn_cancel": [],
    "agent_pause_requested": [],
}

logger = logging.getLogger(__name__)


def register_callback(phase: PhaseType, func: CallbackFunc) -> None:
    if phase not in _callbacks:
        raise ValueError(
            f"Unsupported phase: {phase}. Supported phases: {list(_callbacks.keys())}"
        )

    if not callable(func):
        raise TypeError(f"Callback must be callable, got {type(func)}")

    # Prevent duplicate registration of the same callback function
    # This can happen if plugins are accidentally loaded multiple times
    if func in _callbacks[phase]:
        logger.debug(
            f"Callback {func.__name__} already registered for phase '{phase}', skipping"
        )
        return

    _callbacks[phase].append(func)
    logger.debug(f"Registered async callback {func.__name__} for phase '{phase}'")


def unregister_callback(phase: PhaseType, func: CallbackFunc) -> bool:
    if phase not in _callbacks:
        return False

    try:
        _callbacks[phase].remove(func)
        logger.debug(
            f"Unregistered async callback {func.__name__} from phase '{phase}'"
        )
        return True
    except ValueError:
        return False


def clear_callbacks(phase: Optional[PhaseType] = None) -> None:
    if phase is None:
        for p in _callbacks:
            _callbacks[p].clear()
        logger.debug("Cleared all async callbacks")
    else:
        if phase in _callbacks:
            _callbacks[phase].clear()
            logger.debug(f"Cleared async callbacks for phase '{phase}'")


def get_callbacks(phase: PhaseType) -> List[CallbackFunc]:
    return _callbacks.get(phase, []).copy()


def count_callbacks(phase: Optional[PhaseType] = None) -> int:
    if phase is None:
        return sum(len(callbacks) for callbacks in _callbacks.values())
    return len(_callbacks.get(phase, []))


def _trigger_callbacks_sync(phase: PhaseType, *args, **kwargs) -> List[Any]:
    callbacks = get_callbacks(phase)
    if not callbacks:
        logger.debug(f"No callbacks registered for phase '{phase}'")
        return []

    results = []
    for callback in callbacks:
        try:
            result = callback(*args, **kwargs)
            # Handle async callbacks - if we get a coroutine, run it
            if asyncio.iscoroutine(result):
                # Try to get the running event loop
                try:
                    asyncio.get_running_loop()
                    # We're in an async context already - this shouldn't happen for sync triggers
                    # but if it does, we can't use run_until_complete
                    logger.warning(
                        f"Async callback {callback.__name__} called from async context in sync trigger"
                    )
                    results.append(None)
                    continue
                except RuntimeError:
                    # No running loop - we're in a sync/worker thread context
                    # Use asyncio.run() which is safe here since we're in an isolated thread
                    result = asyncio.run(result)
            results.append(result)
            logger.debug(f"Successfully executed callback {callback.__name__}")
        except Exception as e:
            logger.error(
                f"Callback {callback.__name__} failed in phase '{phase}': {e}\n"
                f"{traceback.format_exc()}"
            )
            results.append(None)

    return results


async def _trigger_callbacks(phase: PhaseType, *args, **kwargs) -> List[Any]:
    callbacks = get_callbacks(phase)

    if not callbacks:
        logger.debug(f"No callbacks registered for phase '{phase}'")
        return []

    logger.debug(f"Triggering {len(callbacks)} async callbacks for phase '{phase}'")

    results = []
    for callback in callbacks:
        try:
            result = callback(*args, **kwargs)
            if asyncio.iscoroutine(result):
                result = await result
            results.append(result)
            logger.debug(f"Successfully executed async callback {callback.__name__}")
        except Exception as e:
            logger.error(
                f"Async callback {callback.__name__} failed in phase '{phase}': {e}\n"
                f"{traceback.format_exc()}"
            )
            results.append(None)

    return results


async def on_startup() -> List[Any]:
    return await _trigger_callbacks("startup")


async def on_shutdown() -> List[Any]:
    return await _trigger_callbacks("shutdown")


async def on_invoke_agent(*args, **kwargs) -> List[Any]:
    return await _trigger_callbacks("invoke_agent", *args, **kwargs)


async def on_agent_exception(exception: Exception, *args, **kwargs) -> List[Any]:
    return await _trigger_callbacks("agent_exception", exception, *args, **kwargs)


async def on_version_check(*args, **kwargs) -> List[Any]:
    return await _trigger_callbacks("version_check", *args, **kwargs)


def on_load_model_config(*args, **kwargs) -> List[Any]:
    return _trigger_callbacks_sync("load_model_config", *args, **kwargs)


def on_load_models_config() -> List[Any]:
    """Trigger callbacks to load additional model configurations.

    Plugins can register callbacks that return a dict of model configurations
    to be merged with the built-in models.json. Plugin models override built-in
    models with the same name.

    Returns:
        List of model config dicts from all registered callbacks.
    """
    return _trigger_callbacks_sync("load_models_config")


def on_edit_file(*args, **kwargs) -> Any:
    return _trigger_callbacks_sync("edit_file", *args, **kwargs)


def on_create_file(*args, **kwargs) -> Any:
    return _trigger_callbacks_sync("create_file", *args, **kwargs)


def on_replace_in_file(*args, **kwargs) -> Any:
    return _trigger_callbacks_sync("replace_in_file", *args, **kwargs)


def on_delete_snippet(*args, **kwargs) -> Any:
    return _trigger_callbacks_sync("delete_snippet", *args, **kwargs)


def on_delete_file(*args, **kwargs) -> Any:
    return _trigger_callbacks_sync("delete_file", *args, **kwargs)


async def on_run_shell_command(*args, **kwargs) -> Any:
    return await _trigger_callbacks("run_shell_command", *args, **kwargs)


def on_agent_reload(*args, **kwargs) -> Any:
    return _trigger_callbacks_sync("agent_reload", *args, **kwargs)


def on_load_prompt():
    return _trigger_callbacks_sync("load_prompt")


def on_custom_command_help() -> List[Any]:
    """Collect custom command help entries from plugins.

    Each callback should return a list of tuples [(name, description), ...]
    or a single tuple, or None. We'll flatten and sanitize results.
    """
    return _trigger_callbacks_sync("custom_command_help")


def on_custom_command(command: str, name: str) -> List[Any]:
    """Trigger custom command callbacks.

    This allows plugins to register handlers for slash commands
    that are not built into the core command handler.

    Args:
        command: The full command string (e.g., "/foo bar baz").
        name: The primary command name without the leading slash (e.g., "foo").

    Returns:
        Implementations may return:
        - True if the command was handled (and no further action is needed)
        - A string to be processed as user input by the caller
        - None to indicate not handled
    """
    return _trigger_callbacks_sync("custom_command", command, name)


def on_file_permission(
    context: Any,
    file_path: str,
    operation: str,
    preview: str | None = None,
    message_group: str | None = None,
    operation_data: Any = None,
) -> List[Any]:
    """Trigger file permission callbacks.

    This allows plugins to register handlers for file permission checks
    before file operations are performed.

    Args:
        context: The operation context
        file_path: Path to the file being operated on
        operation: Description of the operation
        preview: Optional preview of changes (deprecated - use operation_data instead)
        message_group: Optional message group
        operation_data: Operation-specific data for preview generation (recommended)

    Returns:
        List of boolean results from permission handlers.
        Returns True if permission should be granted, False if denied.
    """
    # For backward compatibility, if operation_data is provided, prefer it over preview
    if operation_data is not None:
        preview = None
    return _trigger_callbacks_sync(
        "file_permission",
        context,
        file_path,
        operation,
        preview,
        message_group,
        operation_data,
    )


async def on_pre_tool_call(
    tool_name: str, tool_args: dict, context: Any = None
) -> List[Any]:
    """Trigger callbacks before a tool is called.

    This allows plugins to inspect, modify, or log tool calls before
    they are executed.

    Args:
        tool_name: Name of the tool being called
        tool_args: Arguments being passed to the tool
        context: Optional context data for the tool call

    Returns:
        List of results from registered callbacks.
    """
    return await _trigger_callbacks("pre_tool_call", tool_name, tool_args, context)


async def on_post_tool_call(
    tool_name: str,
    tool_args: dict,
    result: Any,
    duration_ms: float,
    context: Any = None,
) -> List[Any]:
    """Trigger callbacks after a tool completes.

    This allows plugins to inspect tool results, log execution times,
    or perform post-processing.

    Args:
        tool_name: Name of the tool that was called
        tool_args: Arguments that were passed to the tool
        result: The result returned by the tool
        duration_ms: Execution time in milliseconds
        context: Optional context data for the tool call

    Returns:
        List of results from registered callbacks.
    """
    return await _trigger_callbacks(
        "post_tool_call", tool_name, tool_args, result, duration_ms, context
    )


async def on_stream_event(
    event_type: str, event_data: Any, agent_session_id: str | None = None
) -> List[Any]:
    """Trigger callbacks for streaming events.

    This allows plugins to react to streaming events in real-time,
    such as tokens being generated, tool calls starting, etc.

    Args:
        event_type: Type of the streaming event
        event_data: Data associated with the event
        agent_session_id: Optional session ID of the agent emitting the event

    Returns:
        List of results from registered callbacks.
    """
    return await _trigger_callbacks(
        "stream_event", event_type, event_data, agent_session_id
    )


def on_register_tools() -> List[Dict[str, Any]]:
    """Collect custom tool registrations from plugins.

    Each callback should return a list of dicts with:
    - "name": str - the tool name
    - "register_func": callable - function that takes an agent and registers the tool

    Example return: [{"name": "my_tool", "register_func": register_my_tool}]
    """
    return _trigger_callbacks_sync("register_tools")


def on_register_agents() -> List[Dict[str, Any]]:
    """Collect custom agent registrations from plugins.

    Each callback should return a list of dicts with either:
    - "name": str, "class": Type[BaseAgent] - for Python agent classes
    - "name": str, "json_path": str - for JSON agent files

    Example return: [{"name": "my-agent", "class": MyAgentClass}]
    """
    return _trigger_callbacks_sync("register_agents")


def on_register_model_types() -> List[Dict[str, Any]]:
    """Collect custom model type registrations from plugins.

    This hook allows plugins to register custom model types that can be used
    in model configurations. Each callback should return a list of dicts with:
    - "type": str - the model type name (e.g., "claude_code")
    - "handler": callable - function(model_name, model_config, config) -> model instance

    The handler function receives:
    - model_name: str - the name of the model being created
    - model_config: dict - the model's configuration from models.json
    - config: dict - the full models configuration

    The handler should return a model instance or None if creation fails.

    Example callback:
        def register_my_model_types():
            return [{
                "type": "my_custom_type",
                "handler": create_my_custom_model,
            }]

    Example return: [{"type": "my_custom_type", "handler": create_my_custom_model}]
    """
    return _trigger_callbacks_sync("register_model_type")


def on_get_model_system_prompt(
    model_name: str, default_system_prompt: str, user_prompt: str
) -> List[Dict[str, Any]]:
    """Allow plugins to provide custom system prompts for specific model types.

    This hook allows plugins to override the system prompt handling for custom
    model types (like claude_code models). Each callback receives
    the model name and should return a dict if it handles that model type, or None.

    Args:
        model_name: The name of the model being used (e.g., "claude-code-sonnet")
        default_system_prompt: The default system prompt from the agent
        user_prompt: The user's prompt/message

    Each callback should return a dict with:
    - "instructions": str - the system prompt/instructions to use
    - "user_prompt": str - the (possibly modified) user prompt
    - "handled": bool - True if this callback handled the model

    Or return None if the callback doesn't handle this model type.

    Example callback:
        def get_my_model_system_prompt(model_name, default_system_prompt, user_prompt):
            if model_name.startswith("my-custom-"):
                return {
                    "instructions": "You are MyCustomBot.",
                    "user_prompt": f"{default_system_prompt}\n\n{user_prompt}",
                    "handled": True,
                }
            return None  # Not handled by this callback

    Returns:
        List of results from registered callbacks (dicts or None values).
    """
    return _trigger_callbacks_sync(
        "get_model_system_prompt", model_name, default_system_prompt, user_prompt
    )


def on_prepare_model_prompt(
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    prepend_system_to_user: bool = True,
) -> List[Optional[Dict[str, Any]]]:
    """Allow plugins to fully prepare the prompt (instructions + user prompt) for a model.

    This is the hook fired from ``model_utils.prepare_prompt_for_model`` to let
    plugins take over prompt preparation for specific model families (e.g.
    claude-code OAuth models which need a hard-coded instruction string and
    have the system prompt prepended to the user message).

    Unlike ``get_model_system_prompt`` (which is used by augmenting plugins like
    agent_skills), this hook is for plugins that want to *fully handle* the
    prompt prep for a given model. The first callback returning ``handled=True``
    wins; the rest are ignored.

    Args:
        model_name: The name of the model being used.
        system_prompt: The default system prompt from the agent.
        user_prompt: The user's prompt/message.
        prepend_system_to_user: Whether the caller wants system prompt prepended
            to the user prompt (only meaningful for plugins that manipulate the
            user prompt, like claude-code).

    Each callback should return a dict with:
        - ``"handled"``: bool — True if this callback fully prepared the prompt.
        - ``"instructions"``: str — the system prompt/instructions to use.
        - ``"user_prompt"``: str — the (possibly modified) user prompt.
        - ``"is_claude_code"``: bool — (optional) flag preserved on PreparedPrompt.

    Or return ``None`` to indicate "I don't handle this model".

    Returns:
        List of results (dicts or ``None``) from registered callbacks.
    """
    return _trigger_callbacks_sync(
        "prepare_model_prompt",
        model_name,
        system_prompt,
        user_prompt,
        prepend_system_to_user,
    )


async def on_agent_run_start(
    agent_name: str,
    model_name: str,
    session_id: str | None = None,
) -> List[Any]:
    """Trigger callbacks when an agent run starts.

    This fires at the beginning of run_with_mcp, before the agent task is created.
    Useful for:
    - Starting background tasks (like token refresh heartbeats)
    - Logging/analytics
    - Resource allocation

    Args:
        agent_name: Name of the agent starting
        model_name: Name of the model being used
        session_id: Optional session identifier

    Returns:
        List of results from registered callbacks.
    """
    return await _trigger_callbacks(
        "agent_run_start", agent_name, model_name, session_id
    )


async def on_agent_run_end(
    agent_name: str,
    model_name: str,
    session_id: str | None = None,
    success: bool = True,
    error: Exception | None = None,
    response_text: str | None = None,
    metadata: dict | None = None,
) -> List[Any]:
    """Trigger callbacks when an agent run ends.

    This fires at the end of run_with_mcp, in the finally block.
    Always fires regardless of success/failure/cancellation.

    Useful for:
    - Stopping background tasks (like token refresh heartbeats)
    - Workflow orchestration (like Ralph's autonomous loop)
    - Logging/analytics
    - Resource cleanup
    - Detecting completion signals in responses

    Args:
        agent_name: Name of the agent that finished
        model_name: Name of the model that was used
        session_id: Optional session identifier
        success: Whether the run completed successfully
        error: Exception if the run failed, None otherwise
        response_text: The final text response from the agent (if successful)
        metadata: Optional dict with additional context (tokens used, etc.)

    Returns:
        List of results from registered callbacks.
    """
    return await _trigger_callbacks(
        "agent_run_end",
        agent_name,
        model_name,
        session_id,
        success,
        error,
        response_text,
        metadata,
    )


async def on_agent_run_result(
    result: Any,
    agent_name: str,
    model_name: str,
) -> List[Any]:
    """Trigger callbacks after an agent run returns a result.

    Fires after ``pydantic_agent.run()`` completes successfully, **before**
    the result is handed back to the caller.  Plugins can inspect the result
    and request an automatic retry (e.g. when an upstream content-filter
    produced a false-positive refusal).

    Callback signature::

        async def my_callback(result, agent_name: str, model_name: str)
            -> dict | None

    To request a retry, return a dict with::

        {
            "retry": True,
            "prompt": "<message to send on retry>",
            "delay": 1.0,          # optional, seconds before retry
        }

    Return ``None`` (or omit a return) to let the result pass through.
    The first callback that returns a retry request wins; the agent
    replays at most a small fixed number of times to prevent runaway loops.

    Args:
        result: The ``RunResult`` returned by ``pydantic_agent.run()``.
        agent_name: Name of the agent that produced the result.
        model_name: Name of the model that was used.

    Returns:
        List of results from registered callbacks.
    """
    return await _trigger_callbacks("agent_run_result", result, agent_name, model_name)


def on_register_mcp_catalog_servers() -> List[Any]:
    """Trigger callbacks to register additional MCP catalog servers.

    Plugins can register callbacks that return List[MCPServerTemplate] to add
    servers to the MCP catalog/marketplace.

    Returns:
        List of results from all registered callbacks (each should be a list of MCPServerTemplate).
    """
    return _trigger_callbacks_sync("register_mcp_catalog_servers")


async def on_pre_mcp_autostart(agent_name: str, server_names: List[str]) -> List[Any]:
    """Fire ``pre_mcp_autostart`` callbacks before bound MCP servers auto-start.

    Plugins use this to refresh tokens, mint credentials, or do any other
    one-shot prep work *before* the autostart loop calls
    ``manager.start_server`` on each bound server. Errors in callbacks are
    logged but do **not** abort autostart (matches existing convention).

    Args:
        agent_name: The agent whose bindings are about to be auto-started.
        server_names: Names of servers (with ``auto_start=True``) about to start.
            Lets the plugin short-circuit if it has nothing to do.
    """
    return await _trigger_callbacks("pre_mcp_autostart", agent_name, server_names)


def on_pre_mcp_autostart_sync(agent_name: str, server_names: List[str]) -> List[Any]:
    """Sync variant of :func:`on_pre_mcp_autostart` for non-async callers.

    Coroutine callbacks are still awaited via ``asyncio.run`` when no loop
    is currently running (see ``_trigger_callbacks_sync``).
    """
    return _trigger_callbacks_sync("pre_mcp_autostart", agent_name, server_names)


def on_register_browser_types() -> List[Any]:
    """Trigger callbacks to register custom browser types/providers.

    Plugins can register callbacks that return a dict mapping browser type names
    to initialization functions. This allows plugins to provide custom browser
    implementations (like Camoufox for stealth browsing).

    Each callback should return a dict with:
    - key: str - the browser type name (e.g., "camoufox", "firefox-stealth")
    - value: callable - async initialization function that takes (manager, **kwargs)
                        and sets up the browser on the manager instance

    Example callback:
        def register_my_browser_types():
            return {
                "camoufox": initialize_camoufox,
                "my-stealth-browser": initialize_my_stealth,
            }

    Returns:
        List of dicts from all registered callbacks.
    """
    return _trigger_callbacks_sync("register_browser_types")


def on_register_model_providers() -> List[Any]:
    """Trigger callbacks to register custom model provider classes.

    Plugins can register callbacks that return a dict mapping provider names
    to model classes. Example: {"walmart_gemini": WalmartGeminiModel}

    Returns:
        List of dicts from all registered callbacks.
    """
    return _trigger_callbacks_sync("register_model_providers")


def on_message_history_processor_start(
    agent_name: str,
    session_id: str | None,
    message_history: List[Any],
    incoming_messages: List[Any],
) -> List[Any]:
    """Trigger callbacks at the start of message history processing.

    This hook fires at the beginning of the message_history_accumulator,
    before any deduplication or processing occurs. Useful for:
    - Logging/debugging message flow
    - Observing raw incoming messages
    - Analytics on message history growth

    Args:
        agent_name: Name of the agent processing messages
        session_id: Optional session identifier
        message_history: Current message history (before processing)
        incoming_messages: New messages being added

    Returns:
        List of results from registered callbacks.
    """
    return _trigger_callbacks_sync(
        "message_history_processor_start",
        agent_name,
        session_id,
        message_history,
        incoming_messages,
    )


def on_message_history_processor_end(
    agent_name: str,
    session_id: str | None,
    message_history: List[Any],
    messages_added: int,
    messages_filtered: int,
) -> List[Any]:
    """Trigger callbacks at the end of message history processing.

    This hook fires at the end of the message_history_accumulator,
    after deduplication and filtering has been applied. Useful for:
    - Logging/debugging final message state
    - Analytics on deduplication effectiveness
    - Observing what was actually added to history

    Args:
        agent_name: Name of the agent processing messages
        session_id: Optional session identifier
        message_history: Final message history (after processing)
        messages_added: Count of new messages that were added
        messages_filtered: Count of messages that were filtered out (dupes/empty)

    Returns:
        List of results from registered callbacks.
    """
    return _trigger_callbacks_sync(
        "message_history_processor_end",
        agent_name,
        session_id,
        message_history,
        messages_added,
        messages_filtered,
    )


async def on_message(message_id: str, message: Any) -> List[Any]:
    """Trigger callbacks when a message is emitted.

    This is the global observation hook for the messaging system.
    For per-message interception with pattern matching, use
    messaging.interceptors.register_interceptor() instead.

    This hook is for observation (logging, analytics, WebSocket forwarding),
    while interceptors are for control (silencing, replacing, redirecting).

    Args:
        message_id: The well-known message identifier (e.g., "tool:edit_file:complete")
        message: The full Pydantic BaseMessage model (or UIMessage for legacy)

    Returns:
        List of results from registered callbacks.
    """
    return await _trigger_callbacks("on_message", message_id, message)


def on_wrap_pydantic_agent(
    agent,
    pydantic_agent,
    *,
    event_stream_handler=None,
    message_group=None,
    kind: str = "main",
):
    """Allow plugins to wrap the constructed pydantic agent.

    Each callback receives ``(agent, pydantic_agent, event_stream_handler=...,
    message_group=..., kind=...)``. ``kind`` is one of ``"main"`` (top-level
    agent build) or ``"subagent"`` (invoke_agent tool). Plugins return a
    wrapped agent (any object exposing the same ``.run()`` / ``.iter()``
    interface) or ``None`` to leave the agent unchanged. The last non-``None``
    result wins.

    Returns the (possibly wrapped) agent. Always returns something — falls
    back to the input ``pydantic_agent`` if no plugin handled it.
    """
    results = _trigger_callbacks_sync(
        "wrap_pydantic_agent",
        agent,
        pydantic_agent,
        event_stream_handler=event_stream_handler,
        message_group=message_group,
        kind=kind,
    )
    for r in reversed(results):
        if r is not None:
            return r
    return pydantic_agent


def on_agent_run_context(agent, pydantic_agent, group_id, mcp_servers) -> List[Any]:
    """Collect async context managers that should wrap the ``pydantic_agent.run()`` call.

    Each callback returns an async CM (with ``__aenter__``/``__aexit__``) or
    ``None``. The caller composes all non-``None`` results via
    ``contextlib.AsyncExitStack``.

    Returns a list of async context managers (may be empty).
    """
    results = _trigger_callbacks_sync(
        "agent_run_context", agent, pydantic_agent, group_id, mcp_servers
    )
    return [r for r in results if r is not None]


async def on_agent_run_cancel(group_id: str) -> List[Any]:
    """Fired when an agent run is cancelled or interrupted.

    Plugins use this to cancel any external workflow tracking the run.
    """
    return await _trigger_callbacks("agent_run_cancel", group_id)


def on_should_skip_fallback_render(agent) -> bool:
    """Return True if any plugin requests skipping the non-streaming fallback render."""
    results = _trigger_callbacks_sync("should_skip_fallback_render", agent)
    return any(r is True for r in results)


async def on_interactive_turn_end(
    agent,
    prompt: str,
    result: Any = None,
    *,
    success: bool = True,
    error: Optional[BaseException] = None,
) -> List[Any]:
    """Fired after an interactive prompt run completes.

    Plugins may return a continuation request dict, for example::

        {"prompt": "retry the task", "clear_context": True, "delay": 0.5}

    The CLI owns execution; plugins own policy. Nice and not-gross.
    """
    return await _trigger_callbacks(
        "interactive_turn_end",
        agent,
        prompt,
        result,
        success=success,
        error=error,
    )


async def on_interactive_turn_cancel(
    prompt: str, *, reason: str = "cancelled"
) -> List[Any]:
    """Fired when the active interactive prompt/loop is cancelled."""
    return await _trigger_callbacks(
        "interactive_turn_cancel",
        prompt,
        reason=reason,
    )


async def on_agent_pause_requested() -> List[Any]:
    """Fired when the user presses the pause key while the agent is running.

    Plugins are expected to handle the pause UX (collect steering input,
    send ``PauseAgentCommand`` → ``SteerAgentCommand`` → ``ResumeAgentCommand``
    via the message bus). Core does not provide a fallback UI; if no plugin
    is registered, pressing the pause key is a no-op.
    """
    return await _trigger_callbacks("agent_pause_requested")
