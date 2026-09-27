"""Test doubles shared by plugin tests.

These mirror the slice of pydantic-ai's public contract that plugins register
against. Keep them faithful to pydantic-ai, not to one plugin's current usage:
hand-rolled fakes that only accepted ``@agent.tool`` broke the moment plugins
started passing ``@agent.tool(metadata=...)``, and contexts carrying a made-up
``agent_name`` field hid that ``RunContext`` exposes the agent as ``ctx.agent``.
"""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any


class FakeAgent:
    """Captures functions registered via ``@agent.tool`` or ``@agent.tool(**options)``."""

    def __init__(self, name: str = "code-puppy") -> None:
        self.name = name
        self.registered: dict[str, Callable[..., Any]] = {}
        self.tool_options: dict[str, dict[str, Any]] = {}

    def tool(self, fn: Callable[..., Any] | None = None, /, **options: Any):
        def register(func: Callable[..., Any]) -> Callable[..., Any]:
            self.registered[func.__name__] = func
            self.tool_options[func.__name__] = options
            return func

        return register(fn) if fn is not None else register


def fake_run_context(agent_name: str | None = "code-puppy", deps: Any = None) -> Any:
    """A ``RunContext`` stand-in: the running agent (and its name) is ``ctx.agent``."""
    agent = SimpleNamespace(name=agent_name) if agent_name is not None else None
    return SimpleNamespace(agent=agent, deps=deps)
