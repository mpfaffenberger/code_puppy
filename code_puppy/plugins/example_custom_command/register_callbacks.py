from code_puppy.callbacks import register_callback
from code_puppy.messaging import emit_info


def _custom_help():
    return [
        ("woof", "Emit a playful woof message (no model)"),
        ("echo", "Echo back your text (display only)"),
    ]


def _handle_custom_command(command: str, name: str):
    """Handle a demo custom command.

    Policy: custom commands must NOT invoke the model. They should emit
    messages or return True to indicate handling. Returning a string is
    treated as a display-only message by the command handler.

    Supports:
    - /woof          → emits a fun message and returns True
    - /echo <text>   → emits the text (display-only)
    """
    if not name:
        return None

    if name == "woof":
        # If extra text is provided, pass it as a prompt; otherwise, send a fun default
        parts = command.split(maxsplit=1)
        if len(parts) == 2:
            text = parts[1]
            emit_info(f"🐶 Woof! sending prompt: {text}")
            return text
        emit_info("🐶 Woof! sending prompt: Tell me a dog fact")
        return "Tell me a dog fact"

    if name == "echo":
        # Return the rest of the command (after the name) to be treated as input
        # Example: "/echo Hello" → returns "Hello"
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
