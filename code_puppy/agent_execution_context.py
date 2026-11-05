"""Async-safe access to the agent instance owning the current model run.

The agent manager tracks the user's globally selected agent. That is not enough
inside plugins: concurrent ACP sessions and sub-agent tasks may execute distinct
agent instances at the same time. This module provides a narrow ContextVar seam
for run-scoped behavior without coupling plugins to runtime internals. It lives
at the top level (not under ``agents/``) so importing it pulls no runtime
side effects.

The value propagates to coroutines, tasks, and ``asyncio.to_thread`` workers,
but not to ``loop.run_in_executor`` pools (they do not copy the context).
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, Generator

if TYPE_CHECKING:
    from code_puppy.agents.base_agent import BaseAgent

__all__ = [
    "executing_agent_context",
    "get_executing_agent",
    "get_execution_output_type",
]

_executing_agent: ContextVar[Any | None] = ContextVar("executing_agent", default=None)
_execution_output_type: ContextVar[Any] = ContextVar(
    "execution_output_type", default=str
)


@contextmanager
def executing_agent_context(
    agent: Any, *, output_type: Any = str
) -> Generator[None, None, None]:
    """Expose the agent and invocation output contract to async-safe hooks."""
    token = _executing_agent.set(agent)
    output_token = _execution_output_type.set(output_type)
    try:
        yield
    finally:
        _execution_output_type.reset(output_token)
        _executing_agent.reset(token)


def get_executing_agent() -> "BaseAgent | None":
    """Return the agent owning this execution context, if there is one."""
    return _executing_agent.get()


def get_execution_output_type() -> Any:
    """Return the invocation's output contract, or ``str`` outside a run."""
    return _execution_output_type.get()
