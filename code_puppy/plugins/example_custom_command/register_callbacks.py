from code_puppy.callbacks import register_callback
from code_puppy.messaging import emit_info

# Optional dependency on the sibling ``customizable_commands`` plugin.
# Returning a ``MarkdownCommandResult`` from a custom command tells the
# dispatcher to forward the wrapped content to the agent as a prompt
# (see ``code_puppy.command_line.command_handler.handle_command``).
# If the sibling plugin is ever absent we fall back to display-only
# behavior rather than fail the whole plugin load.
try:
    from code_puppy.plugins.customizable_commands.register_callbacks import (
        MarkdownCommandResult,
    )
except ImportError:  # pragma: no cover - defensive fallback
    MarkdownCommandResult = None


def _custom_help():
    return [
        ("ask", "Send an example prompt to the agent"),
        ("echo", "Echo back your text (display only)"),
    ]


def _handle_custom_command(command: str, name: str):
    """Handle a demo custom command.

    Custom commands registered via the ``custom_command`` callback may return:

    - ``None``                  -- not our command, let other plugins try.
    - ``True``                  -- fully handled, no further action.
    - ``str``                   -- display-only message; the dispatcher emits
                                   it and stops (the agent is NOT invoked).
    - ``MarkdownCommandResult`` -- the wrapped ``.content`` is forwarded to
                                   the agent as a user prompt.

    Supports:
    - /ask [text]    -> sends a prompt to the agent (defaults to a coding tip)
    - /echo <text>   -> displays the text (no agent round-trip)
    """
    if not name:
        return None

    if name == "ask":
        parts = command.split(maxsplit=1)
        prompt = parts[1] if len(parts) == 2 else "Tell me a concise coding tip"
        emit_info(f"🫧 Mist is sending prompt: {prompt}")
        # Forward to the agent when possible; otherwise degrade gracefully
        # to display-only so the user at least sees the echoed prompt.
        if MarkdownCommandResult is not None:
            return MarkdownCommandResult(prompt)
        return prompt

    if name == "echo":
        # Display-only: return the text after the command name and let the
        # dispatcher's ``str`` branch emit it.
        rest = command.split(maxsplit=1)
        if len(rest) == 2:
            text = rest[1]
            emit_info(f"example plugin echo -> {text}")
            return text
        emit_info("example plugin echo (empty)")
        return ""

    return None


register_callback("custom_command_help", _custom_help)
register_callback("custom_command", _handle_custom_command)
