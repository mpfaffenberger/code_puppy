"""Shared fixtures + message-construction helpers for the /prune test suite.

Split out of the original mega-file ``tests/plugins/test_prune_plugin.py``
so each test module stays under the 600-line cap mandated by CONTRIBUTING.md
without duplicating the same constructor boilerplate everywhere.
"""

from __future__ import annotations

import importlib
from types import SimpleNamespace
from unittest.mock import MagicMock

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

try:
    from pydantic_ai.messages import ThinkingPart  # type: ignore
except ImportError:  # pragma: no cover — older pydantic-ai versions
    ThinkingPart = None  # type: ignore[assignment]

try:
    from pydantic_ai.messages import RetryPromptPart  # type: ignore
except ImportError:  # pragma: no cover
    RetryPromptPart = None  # type: ignore[assignment]


# ── plugin module access ────────────────────────────────────────────────────


def _plugin_module():
    return importlib.import_module("code_puppy.plugins.prune.register_callbacks")


def _agent_manager_module(agent: MagicMock) -> SimpleNamespace:
    return SimpleNamespace(get_current_agent=lambda: agent)


# ── pydantic-ai message constructors ────────────────────────────────────────


def _system_msg() -> ModelRequest:
    return ModelRequest(parts=[SystemPromptPart(content="you are a puppy")])


def _system_plus_user_msg(
    system: str = "you are a puppy", user: str = "first turn"
) -> ModelRequest:
    """How pydantic-ai actually bundles history[0]: system + first user."""
    return ModelRequest(
        parts=[
            SystemPromptPart(content=system),
            UserPromptPart(content=user),
        ]
    )


def _user_msg(text: str = "hi") -> ModelRequest:
    return ModelRequest(parts=[UserPromptPart(content=text)])


def _assistant_text(text: str = "hello human") -> ModelResponse:
    return ModelResponse(parts=[TextPart(content=text)])


def _assistant_with_thinking(
    text: str = "final answer", thinking: str = "let me think..."
) -> ModelResponse:
    """Build an assistant response with both a thinking part and a text part.

    Skips the test cleanly if the installed pydantic-ai is too old to ship
    ``ThinkingPart`` so the suite remains forwards-compatible.
    """
    if ThinkingPart is None:  # pragma: no cover
        import pytest

        pytest.skip("pydantic-ai version lacks ThinkingPart")
    return ModelResponse(parts=[ThinkingPart(content=thinking), TextPart(content=text)])


def _assistant_with_tool(
    *, text: str | None, tool_name: str, tool_call_id: str, args: str = "{}"
) -> ModelResponse:
    parts = []
    if text is not None:
        parts.append(TextPart(content=text))
    parts.append(
        ToolCallPart(tool_name=tool_name, args=args, tool_call_id=tool_call_id)
    )
    return ModelResponse(parts=parts)


def _tool_return(tool_call_id: str, content: str = "ok") -> ModelRequest:
    return ModelRequest(
        parts=[
            ToolReturnPart(tool_name="t", content=content, tool_call_id=tool_call_id)
        ]
    )


# ── menu fixture used by both render-smoke and menu-state suites ───────────


def _menu_with_history():
    """Build a PruneMenu over a small but representative history.

    Used by ``test_prune_menu`` and ``test_prune_render`` (smoke renders).
    Imported lazily so this helpers module stays free of plugin-import side
    effects at collection time.
    """
    from code_puppy.plugins.prune.prune_menu import PruneMenu
    from code_puppy.plugins.prune.prune_model import build_message_entries

    history = [
        _system_msg(),
        _user_msg("step 1"),
        _assistant_with_tool(
            text="running tests",
            tool_name="agent_run_shell_command",
            tool_call_id="tc1",
            args='{"command": "pytest"}',
        ),
        _tool_return("tc1"),
        _user_msg("step 2"),
        _assistant_with_tool(
            text="writing file",
            tool_name="create_file",
            tool_call_id="tc2",
            args='{"file_path": "x.py"}',
        ),
        _tool_return("tc2"),
    ]
    entries = build_message_entries(history)
    return PruneMenu(entries=entries), entries, history
