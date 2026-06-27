"""Slash-command handling for the chat WebSocket."""

from __future__ import annotations

import logging
from io import StringIO
from typing import Any

from rich.console import Console

from code_puppy.api.ws.schemas import ServerCommandResult

logger = logging.getLogger(__name__)


async def handle_command_message(
    *,
    msg: dict[str, Any],
    session_id: str,
    send_typed: Any,
) -> bool:
    """Handle a websocket ``type=command`` payload."""
    if msg.get("type") != "command":
        return False

    command_str = msg.get("command", "")
    logger.debug("Command requested: %s", command_str)

    try:
        from code_puppy.command_line.command_handler import (
            get_commands_help,
            handle_command,
        )

        output = None
        captured_messages = []

        cmd_name = (
            command_str.strip().lstrip("/").split()[0] if command_str.strip() else ""
        )
        if cmd_name in ("help", "h"):
            help_text = get_commands_help()
            output_buffer = StringIO()
            console = Console(
                file=output_buffer,
                force_terminal=False,
                width=100,
                no_color=True,
            )
            console.print(help_text)
            output = output_buffer.getvalue().strip()
            result = True
        else:
            result = handle_command(command_str)
            if isinstance(result, str):
                output = result
                result = True

        await send_typed(
            ServerCommandResult(
                command=command_str,
                success=result is True,
                output=output,
                messages=captured_messages,
                result=str(result) if result and result is not True else None,
                session_id=session_id,
            )
        )
        logger.debug(
            "Command executed: %s -> success=%s, output_len=%s",
            command_str,
            result is True,
            len(output) if output else 0,
        )
    except Exception as cmd_error:
        import traceback

        error_details = traceback.format_exc()
        logger.error("Command error: %s", cmd_error)
        logger.error("Traceback: %s", error_details)
        await send_typed(
            ServerCommandResult(
                command=command_str,
                success=False,
                error=str(cmd_error),
                session_id=session_id,
            )
        )

    return True


__all__ = ["handle_command_message"]
