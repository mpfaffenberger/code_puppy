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
from contextvars import ContextVar, Token
from typing import Generator, Optional

__all__ = [
    "subagent_context",
    "is_subagent",
    "get_subagent_name",
    "get_subagent_chain",
    "get_subagent_depth",
    "get_subagent_model_name",
    "set_conversation_root_id",
    "reset_conversation_root_id",
    "get_conversation_root_id",
]

# Track sub-agent depth (0 = main agent, 1+ = sub-agent)
_subagent_depth: ContextVar[int] = ContextVar("subagent_depth", default=0)

# Track current sub-agent name (None = main agent)
_subagent_name: ContextVar[str | None] = ContextVar("subagent_name", default=None)
_subagent_model_name: ContextVar[str | None] = ContextVar(
    "subagent_model_name", default=None
)

# Full sub-agent name chain as an immutable tuple (cheap per-push snapshot):
# empty for main agent; ``("A", "B")`` for code-puppy -> A -> B.
_subagent_chain: ContextVar[tuple[str, ...]] = ContextVar("subagent_chain", default=())

# Identifies the top-level conversation this tree belongs to (ACP session id,
# or None for the CLI). Deliberately a plain ContextVar, NOT the message-bus's
# shared, per-task-unsafe session context: it copies into child tasks, so
# siblings stay independent and nested A→B inherits the SAME root value (stable
# "once per conversation" dedup). Set by ACP's prompt handler; never subagent_context.
_conversation_root_id: ContextVar[Optional[str]] = ContextVar(
    "conversation_root_id", default=None
)


@contextmanager
def subagent_context(
    agent_name: str, model_name: str | None = None
) -> Generator[None, None, None]:
    """Context manager for tracking sub-agent execution.

    Increments the sub-agent depth and sets the current agent name on entry,
    then restores the previous state on exit. Uses token-based reset for
    proper async isolation and exception safety.

    Args:
        agent_name: Name of the sub-agent being executed (e.g., "retriever", "code-puppy")

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
    current_chain = _subagent_chain.get()

    # Set new values and save tokens for restoration
    depth_token = _subagent_depth.set(current_depth + 1)
    name_token = _subagent_name.set(agent_name)
    model_token = _subagent_model_name.set(model_name)
    chain_token = _subagent_chain.set(current_chain + (agent_name,))

    try:
        yield
    finally:
        # Use token-based reset for proper async isolation
        # This ensures the context is restored even if an exception occurs
        _subagent_depth.reset(depth_token)
        _subagent_name.reset(name_token)
        _subagent_model_name.reset(model_token)
        _subagent_chain.reset(chain_token)


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
        >>> with subagent_context("code-puppy"):
        ...     get_subagent_name()
        'code-puppy'
    """
    return _subagent_name.get()


def get_subagent_model_name() -> str | None:
    """Return the model running the current sub-agent."""
    return _subagent_model_name.get()


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


def get_subagent_chain() -> tuple[str, ...]:
    """Return the full sub-agent invocation chain, outermost first.

    The main agent is not part of the chain — it is implicit. Use this
    when you need to know the *immediate* parent sub-agent rather than
    just the current name.

    This is used to attribute token spend to the agent that actually
    initiated the call vs. the one one level up the call stack.

    Returns:
        An immutable tuple of sub-agent names, deepest last. ``()`` when
        running in the main agent context.

    Example:
        >>> get_subagent_chain()
        ()
        >>> with subagent_context("retriever"):
        ...     get_subagent_chain()
        ('retriever',)
        ...     with subagent_context("terrier"):
            ...         get_subagent_chain()
        ('retriever', 'terrier')
    """
    return _subagent_chain.get()


def set_conversation_root_id(value: Optional[str]) -> Token:
    """Mark the current asyncio task as belonging to conversation ``value``.

    Call once at the true root of a conversation (e.g. an ACP session's
    prompt handler) -- NOT inside ``subagent_context``, so nested sub-agent
    invocations inherit the same root rather than each minting their own.

    Returns a token; pass it to :func:`reset_conversation_root_id` to restore
    the previous value (typically in a ``finally`` block).
    """
    return _conversation_root_id.set(value)


def reset_conversation_root_id(token: Token) -> None:
    """Restore the conversation root id to its value before ``set``."""
    _conversation_root_id.reset(token)


def get_conversation_root_id() -> Optional[str]:
    """Return the current task's conversation root id, or ``None``.

    ``None`` both for the CLI (which never sets this -- single conversation
    per process, matching its existing ``/clear``-driven reset model) and
    for any code path that runs outside a ``set_conversation_root_id``
    scope.
    """
    return _conversation_root_id.get()
