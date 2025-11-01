"""Global task factory to intercept and track all asyncio task creation."""

import asyncio
from typing import Any, Callable, Optional

from code_puppy.task_registry import can_create_tasks, track_agent_task

_original_task_factory: Optional[Callable] = None


def task_factory(
    loop: asyncio.AbstractEventLoop, coro: Any, *, context: Optional[Any] = None
) -> asyncio.Task:
    """Global task factory that automatically tracks all created tasks."""

    # Check if task creation is allowed
    if not can_create_tasks():
        # Don't create tasks at all during cancellation to prevent hangs
        raise asyncio.CancelledError("Task creation blocked during cancellation")

    # Create the task using the original factory
    if _original_task_factory:
        task = _original_task_factory(loop, coro, context=context)
    else:
        task = asyncio.Task(coro, loop=loop, context=context)

    # Try to get the current task for parent relationship
    try:
        current_task = asyncio.current_task(loop=loop)
        track_agent_task(task, current_task)
    except (RuntimeError, Exception):
        # If we can't get current task, track without parent
        try:
            track_agent_task(task, None)
        except Exception:
            # If tracking fails, continue without tracking
            pass

    return task


def install_global_task_factory() -> None:
    """Install the global task factory to intercept all task creation."""
    global _original_task_factory

    try:
        loop = asyncio.get_running_loop()
        _original_task_factory = loop.get_task_factory()
        loop.set_task_factory(task_factory)
    except RuntimeError:
        # No running loop, will be installed when loop starts
        pass


def uninstall_global_task_factory() -> None:
    """Uninstall the global task factory and restore the original."""
    global _original_task_factory

    try:
        loop = asyncio.get_running_loop()
        if _original_task_factory:
            loop.set_task_factory(_original_task_factory)
        else:
            loop.set_task_factory(None)
    except RuntimeError:
        # No running loop
        pass


def ensure_task_factory_installed() -> None:
    """Ensure the task factory is installed on the current event loop."""
    try:
        loop = asyncio.get_running_loop()
        if loop.get_task_factory() != task_factory:
            install_global_task_factory()
    except RuntimeError:
        # No running loop yet
        pass
