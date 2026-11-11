"""Task-local hook identity, isolated from mutable callback metadata."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Iterator


@dataclass(frozen=True)
class ToolIdentity:
    tool_call_id: str | None
    outcome: str | None


_current: ContextVar[ToolIdentity | None] = ContextVar(
    "tool_hook_identity", default=None
)


def current_tool_identity() -> ToolIdentity | None:
    """Return captured identity, or None outside a hook dispatch."""
    return _current.get()


@contextmanager
def tool_call_identity(context: Any) -> Iterator[None]:
    """Restore the enclosing identity after success, error or cancellation."""
    value = context.get("tool_call_id") if isinstance(context, dict) else None
    outcome = context.get("outcome") if isinstance(context, dict) else None
    token = _current.set(
        ToolIdentity(
            value if isinstance(value, str) and value else None,
            outcome if isinstance(outcome, str) else None,
        )
    )
    try:
        yield
    finally:
        _current.reset(token)
