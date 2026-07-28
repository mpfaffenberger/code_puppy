"""Register the macOS computer-use tools as an optional builtin plugin."""

from __future__ import annotations

import sys
from typing import Any

from code_puppy.callbacks import register_callback

_TOOL_NAMES = (
    "computer_get_app_state",
    "computer_snapshot",
    "computer_click",
    "computer_set_value",
    "computer_perform_action",
    "computer_select_text",
    "computer_press_key",
    "computer_type_text",
    "computer_scroll",
    "computer_drag",
    "computer_screenshot",
    "computer_use_batch",
)


def _available() -> bool:
    return sys.platform == "darwin"


def _register_tools() -> list[dict[str, Any]]:
    if not _available():
        return []

    from .tools import REGISTRARS

    return [{"name": name, "register_func": REGISTRARS[name]} for name in _TOOL_NAMES]


def _register_agent_tools(agent_name: str | None = None) -> list[str]:
    del agent_name
    return list(_TOOL_NAMES) if _available() else []


def _load_prompt() -> str | None:
    if not _available():
        return None
    return (
        "macOS Computer Use requires persisted one-time user consent. If a tool "
        "reports that consent is unset or disabled, show its exact slash command "
        "to the user and do not work around it. Slash commands are not visible in "
        "conversation history, so never repeat an old consent error from memory. "
        "When the user repeats the request, always call the appropriate Computer "
        "Use state tool again; the tool's current result is authoritative. Once "
        "enabled, do not ask for per-application approval. Prefer "
        "computer_get_app_state and element IDs over screen coordinates. Every "
        "standalone mutation needs its current state_revision; guarded batches "
        "return fresh state after deterministic UI settling. For pixel-based "
        "focus-and-type workflows, use one guarded batch instead of guessing across "
        "separate revisions. Verify the returned state and recover until the "
        "requested outcome is visibly complete. Do not stop merely because the user "
        "moves the pointer or types. The emergency stop and hard macOS "
        "security-process denylist remain enforced."
    )


def _custom_help():
    from .commands import command_help

    return command_help()


def _custom_command(command: str, name: str):
    from .commands import handle_command

    return handle_command(command, name)


register_callback("register_tools", _register_tools)
register_callback("register_agent_tools", _register_agent_tools)
register_callback("load_prompt", _load_prompt)
register_callback("custom_command_help", _custom_help)
register_callback("custom_command", _custom_command)
