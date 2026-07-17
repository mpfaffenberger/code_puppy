"""Plan-mode tool and shell policy callbacks."""

from __future__ import annotations

from typing import Any

from .state import AgentMode, get_agent_mode

MUTATING_TOOLS = frozenset(
    {
        "create_file",
        "edit_file",
        "replace_in_file",
        "delete_file",
        "delete_snippet",
    }
)


def guard_tool_call(
    tool_name: str, tool_args: dict[str, Any], context: Any = None
) -> dict[str, Any] | None:
    """Deny direct file mutation while Plan mode is active."""
    del tool_args, context
    if get_agent_mode() is AgentMode.PLAN and tool_name in MUTATING_TOOLS:
        return {
            "blocked": True,
            "reason": (
                f"[BLOCKED] {tool_name} is unavailable in Plan mode. "
                "Continue with read-only analysis or ask the user to switch to Build mode."
            ),
        }
    return None


def require_shell_approval(
    context: Any,
    command: str,
    cwd: str | None = None,
    timeout: int = 60,
) -> dict[str, Any] | None:
    """Require a human decision for every shell command in Plan mode."""
    del context, command, cwd, timeout
    if get_agent_mode() is AgentMode.PLAN:
        return {
            "requires_approval": True,
            "reason": "Plan mode requires approval before shell execution.",
        }
    return None


def mode_prompt() -> str:
    """Add the active overlay to dynamic prompt context."""
    if get_agent_mode() is AgentMode.PLAN:
        return (
            "ACTIVE MODE: PLAN. Explore and reason read-only. File mutation tools are "
            "blocked and every shell command requires explicit user approval."
        )
    return "ACTIVE MODE: BUILD. Normal tool and permission policies apply."
