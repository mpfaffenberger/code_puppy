"""Sub-agent context management with async-safe state tracking.

This module provides context-aware tracking of sub-agent execution state using
Python's contextvars for async-safe isolation. This ensures that sub-agent state
is properly isolated across different async tasks and execution contexts.

## Why ContextVars?

ContextVars provide automatic context isolation in async environments:
- Each async task gets its own copy of the context
- State changes in one task don't affect others
- Perfect for tracking execution depth in nested agent calls
- Token-based reset ensures proper cleanup even with exceptions

## Usage Example:

```python
from code_puppy.tools.subagent_context import subagent_context, is_subagent

# Main agent
print(is_subagent())  # False

async def run_subagent():
    with subagent_context("retriever"):
        print(is_subagent())  # True
        print(get_subagent_name())  # "retriever"
        print(get_subagent_depth())  # 1

        # Nested sub-agent
        with subagent_context("terrier"):
            print(get_subagent_depth())  # 2
            print(get_subagent_name())  # "terrier"

        # Back to parent sub-agent
        print(get_subagent_name())  # "retriever"
        print(get_subagent_depth())  # 1

# After context exits
print(is_subagent())  # False
```

## Benefits:

1. **Async Safety**: Multiple sub-agents can run concurrently without interference
2. **Nested Support**: Properly handles sub-agents calling other sub-agents
3. **Clean Restoration**: Token-based reset ensures state is restored even on errors
4. **Zero Overhead**: When not in a sub-agent context, minimal performance impact
"""

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Generator

__all__ = [
    "subagent_context",
    "is_subagent",
    "get_subagent_name",
    "get_subagent_depth",
]

# Track sub-agent depth (0 = main agent, 1+ = sub-agent)
_subagent_depth: ContextVar[int] = ContextVar("subagent_depth", default=0)

# Track current sub-agent name (None = main agent)
_subagent_name: ContextVar[str | None] = ContextVar("subagent_name", default=None)


@contextmanager
def subagent_context(agent_name: str) -> Generator[None, None, None]:
    """Context manager for tracking sub-agent execution.

    Increments the sub-agent depth and sets the current agent name on entry,
    then restores the previous state on exit. Uses token-based reset for
    proper async isolation and exception safety.

    Args:
        agent_name: Name of the sub-agent being executed (e.g., "retriever", "husky")

    Yields:
        None

    Example:
        >>> with subagent_context("retriever"):
        ...     assert is_subagent() is True
        ...     assert get_subagent_name() == "retriever"
        >>> assert is_subagent() is False

    Note:
        Token-based reset ensures that even if an exception occurs, the context
        is properly restored. This is especially important in async environments
        where multiple tasks may be running concurrently.
    """
    # Get current depth for incrementing
    current_depth = _subagent_depth.get()

    # Set new values and save tokens for restoration
    depth_token = _subagent_depth.set(current_depth + 1)
    name_token = _subagent_name.set(agent_name)

    try:
        yield
    finally:
        # Use token-based reset for proper async isolation
        # This ensures the context is restored even if an exception occurs
        _subagent_depth.reset(depth_token)
        _subagent_name.reset(name_token)


def is_subagent() -> bool:
    """Check if currently executing within a sub-agent context.

    Returns:
        True if depth > 0 (inside a sub-agent), False otherwise (main agent)

    Example:
        >>> is_subagent()
        False
        >>> with subagent_context("retriever"):
        ...     is_subagent()
        True
    """
    return _subagent_depth.get() > 0


def get_subagent_name() -> str | None:
    """Get the name of the current sub-agent.

    Returns:
        Current sub-agent name, or None if in main agent context

    Example:
        >>> get_subagent_name()
        None
        >>> with subagent_context("husky"):
        ...     get_subagent_name()
        'husky'
    """
    return _subagent_name.get()


def get_subagent_depth() -> int:
    """Get the current sub-agent nesting depth.

    Returns:
        Current depth level (0 = main agent, 1 = first-level sub-agent,
        2 = nested sub-agent, etc.)

    Example:
        >>> get_subagent_depth()
        0
        >>> with subagent_context("retriever"):
        ...     get_subagent_depth()
        1
        ...     with subagent_context("terrier"):
        ...         get_subagent_depth()
        2
    """
    return _subagent_depth.get()
