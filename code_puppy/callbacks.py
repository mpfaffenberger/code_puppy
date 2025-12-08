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
    "delete_file",
    "run_shell_command",
    "load_model_config",
    "load_prompt",
    "agent_reload",
    "custom_command",
    "custom_command_help",
    "file_permission",
]
CallbackFunc = Callable[..., Any]

_callbacks: Dict[PhaseType, List[CallbackFunc]] = {
    "startup": [],
    "shutdown": [],
    "invoke_agent": [],
    "agent_exception": [],
    "version_check": [],
    "edit_file": [],
    "delete_file": [],
    "run_shell_command": [],
    "load_model_config": [],
    "load_prompt": [],
    "agent_reload": [],
    "custom_command": [],
    "custom_command_help": [],
    "file_permission": [],
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


def on_edit_file(*args, **kwargs) -> Any:
    return _trigger_callbacks_sync("edit_file", *args, **kwargs)


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
