"""
Hook Creator Plugin - Simple command that injects MCP prompt
"""

from code_puppy.callbacks import register_callback
from code_puppy.mcp_prompts.hook_creator import HOOK_CREATION_PROMPT
from code_puppy.messaging import emit_info


def _custom_help():
    """Help entries for create-hook commands."""
    return [
        ("create-hook", "Get help creating Code Puppy hooks"),
    ]


def _handle_custom_command(command: str, name: str):
    """Handle /create-hook command.

    Displays hook creation documentation and sends to model with context.
    """
    if name != "create-hook":
        return None

    emit_info(HOOK_CREATION_PROMPT)

    # Send the prompt to the model with the hook docs as context
    return "I need help creating a hook for Code Puppy. Here's the documentation above. Can you help me?"


# Register the custom command
register_callback("custom_command_help", _custom_help)
register_callback("custom_command", _handle_custom_command)
