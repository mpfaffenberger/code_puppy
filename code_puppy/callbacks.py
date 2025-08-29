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
}

logger = logging.getLogger(__name__)


def register_callback(phase: PhaseType, func: CallbackFunc) -> None:
    if phase not in _callbacks:
        raise ValueError(
            f"Unsupported phase: {phase}. Supported phases: {list(_callbacks.keys())}"
        )

    if not callable(func):
        raise TypeError(f"Callback must be callable, got {type(func)}")

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
            results.append(result)
            logger.debug(f"Successfully executed async callback {callback.__name__}")
        except Exception as e:
            logger.error(
                f"Async callback {callback.__name__} failed in phase '{phase}': {e}\n"
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


def on_run_shell_command(*args, **kwargs) -> Any:
    return _trigger_callbacks_sync("run_shell_command", *args, **kwargs)


def on_agent_reload(*args, **kwargs) -> Any:
    return _trigger_callbacks_sync("agent_reload", *args, **kwargs)


def on_load_prompt():
    return _trigger_callbacks_sync("load_prompt")
