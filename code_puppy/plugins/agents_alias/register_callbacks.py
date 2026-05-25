"""Alias ``/agents`` → ``/agent``.

The built-in ``/agent`` command already advertises a ``/a`` short alias. Plenty
of docs and muscle memory reach for the plural ``/agents`` form though, so this
tiny plugin wires that up without touching ``code_puppy/command_line/`` (per
contributing rules).

Implementation is intentionally boring: when the user types ``/agents [args]``
we rewrite the command string to ``/agent [args]`` and hand it straight to the
registered handler. No logic duplication, no drift.
"""

from __future__ import annotations

from typing import Optional

from code_puppy.callbacks import register_callback

# The canonical command we're aliasing to.
_TARGET = "agent"
# Names this plugin owns.
_ALIASES = ("agents",)


def _handle_agents_alias(command: str, name: str) -> Optional[object]:
    """Delegate ``/agents ...`` to the registered ``/agent`` handler."""
    if name not in _ALIASES:
        return None  # Not our command — let other plugins / fallthrough handle it.

    # Lazy import: keeps plugin load cheap and avoids circular import risk.
    from code_puppy.command_line.command_registry import get_command

    cmd_info = get_command(_TARGET)
    if cmd_info is None:
        # Shouldn't happen — /agent is a built-in — but fail gracefully.
        return None

    # Rewrite "/agents [rest]" → "/agent [rest]" preserving arguments exactly.
    # Split on the first whitespace run so quoted args (if any) stay intact.
    parts = command.split(None, 1)
    rewritten = f"/{_TARGET}" + (f" {parts[1]}" if len(parts) > 1 else "")
    return cmd_info.handler(rewritten)


def _handle_help() -> list:
    return [
        ("agents", "Alias for /agent — switch or list agents"),
    ]


register_callback("custom_command", _handle_agents_alias)
register_callback("custom_command_help", _handle_help)
