"""Tool concurrency gates for multi-session safety.

Serializes write and shell tool executions across concurrent ACP
sessions to prevent race conditions (e.g. two sessions editing the
same file simultaneously, or two shell commands clobbering each
other's working directory).

Read-only tools run without restriction.  Write-class and execute-class
tools are each gated by their own asyncio.Semaphore(1), ensuring at
most one concurrent write or shell operation across all sessions.

Usage::

    from code_puppy.plugins.acp_gateway.tool_concurrency import gate

    @gate
    async def write_file(...):
        ...

Or applied programmatically during gateway startup::

    from code_puppy.plugins.acp_gateway.tool_concurrency import install_gates
    install_gates()
"""

from __future__ import annotations

import asyncio
import functools
import logging
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

# Tool classification sets — mirrors the sets in agent.py
_WRITE_TOOLS = frozenset({
    "write_file", "edit_file", "create_file", "delete_file",
    "apply_diff", "patch_file", "rename_file", "move_file",
})

_EXECUTE_TOOLS = frozenset({
    "run_terminal_cmd", "run_command", "execute_command",
    "bash", "shell", "terminal",
})

# Lazy semaphores — created on first access so they belong to the
# correct event loop.  Using sem=1 serializes operations.
_write_sem: asyncio.Semaphore | None = None
_shell_sem: asyncio.Semaphore | None = None


def _get_write_sem() -> asyncio.Semaphore:
    """Return (or lazily create) the write semaphore."""
    global _write_sem
    if _write_sem is None:
        _write_sem = asyncio.Semaphore(1)
    return _write_sem


def _get_shell_sem() -> asyncio.Semaphore:
    """Return (or lazily create) the shell semaphore."""
    global _shell_sem
    if _shell_sem is None:
        _shell_sem = asyncio.Semaphore(1)
    return _shell_sem


def _sem_for_tool(tool_name: str) -> asyncio.Semaphore | None:
    """Return the appropriate semaphore for a tool, or None for reads."""
    if tool_name in _WRITE_TOOLS:
        return _get_write_sem()
    if tool_name in _EXECUTE_TOOLS:
        return _get_shell_sem()
    return None  # read tools — no gate


def gate(
    func: Callable[..., Coroutine[Any, Any, Any]] | None = None,
    *,
    tool_name: str | None = None,
) -> Any:
    """Decorator that gates an async tool function with the appropriate semaphore.

    Can be used as:
        @gate
        async def write_file(...): ...

        @gate(tool_name="write_file")
        async def my_custom_writer(...): ...

    If ``tool_name`` is not provided, the function's ``__name__`` is used
    for classification.
    """
    def decorator(fn: Callable[..., Coroutine[Any, Any, Any]]) -> Callable[..., Coroutine[Any, Any, Any]]:
        effective_name = tool_name or fn.__name__

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            sem = _sem_for_tool(effective_name)
            if sem is None:
                return await fn(*args, **kwargs)
            async with sem:
                logger.debug("gate acquired for %s", effective_name)
                return await fn(*args, **kwargs)

        return wrapper

    if func is not None:
        # @gate without arguments
        return decorator(func)
    # @gate(tool_name="...") with arguments
    return decorator


def install_gates() -> None:
    """Apply concurrency gates to Code Puppy's tool functions.

    Wraps async tool functions in ``file_modifications`` and
    ``command_runner`` with the appropriate semaphore gate.

    Called once during ACP gateway startup.  Safe to call multiple
    times (idempotent — checks for ``_gated`` marker).
    """
    import importlib

    _gate_targets = {
        "code_puppy.tools.file_modifications": [
            "write_file", "edit_file", "create_file", "delete_file",
            "apply_diff",
        ],
        "code_puppy.tools.command_runner": [
            "run_terminal_cmd",
        ],
    }

    for mod_name, func_names in _gate_targets.items():
        try:
            mod = importlib.import_module(mod_name)
        except ImportError:
            logger.debug("Cannot import %s for gating", mod_name)
            continue

        for fname in func_names:
            fn = getattr(mod, fname, None)
            if fn is None or getattr(fn, "_gated", False):
                continue
            gated = gate(fn, tool_name=fname)
            gated._gated = True  # type: ignore[attr-defined]
            setattr(mod, fname, gated)
            logger.debug("Gated tool: %s.%s", mod_name, fname)
