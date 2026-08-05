"""Wire the paw-sign plugin into the runtime.

Hooks ``pre_tool_call`` and mutates the ``agent_run_shell_command`` args in
place, appending a puppy signature to ``git commit -m`` messages composed by
code-puppy. Never blocks a tool call; failures are swallowed so a bad rewrite
can never crash the agent.
"""

import logging
from typing import Any, Dict, Optional

from code_puppy.callbacks import register_callback
from code_puppy.plugins.paw_sign.detector import paw_sign_command

logger = logging.getLogger(__name__)

_SHELL_TOOL = "agent_run_shell_command"


def _on_pre_tool_call(
    tool_name: str, tool_args: Dict[str, Any], context: Any = None
) -> Optional[Dict[str, Any]]:
    """Append the paw-sign to qualifying ``git commit`` shell commands.

    Mutates ``tool_args["command"]`` in place (the same pattern the emoji_filter
    plugin uses). Returns ``None`` always -- this is a silent, non-blocking
    rewrite.
    """
    if tool_name != _SHELL_TOOL or not isinstance(tool_args, dict):
        return None

    command = tool_args.get("command")
    if not isinstance(command, str):
        return None

    try:
        signed = paw_sign_command(command)
    except Exception as exc:  # never break tool execution over a signature
        logger.debug("paw_sign pre_tool_call failed: %s", exc)
        return None

    if signed is not None:
        tool_args["command"] = signed

    return None


def register() -> None:
    """Register the paw-sign pre_tool_call callback."""
    register_callback("pre_tool_call", _on_pre_tool_call)


# Auto-register when this module is imported by the plugin loader.
register()
