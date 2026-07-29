"""Callback registration for the destructive command guardrails plugin.

Hooks into the run_shell_command phase to intercept destructive shell commands
before they can cause data loss or other irreversible side effects.
"""

from code_puppy.callbacks import register_callback
from code_puppy.plugins.destructive_command_guard.detector import (
    detect_destructive_command,
)
from code_puppy.plugins.guard_framework import GuardSpec, make_shell_guard

_DESTRUCTIVE_GUARD_SPEC = GuardSpec(
    title="Destructive Command Guardrails",
    detected_label="Destructive command detected: ",
    consequence="This command could cause irreversible data loss or system damage.",
    block_advice=(
        "If you really need to run this command, run it in your own terminal "
        "after double-checking the target."
    ),
    detect=detect_destructive_command,
    allow_disable_guard=True,
)


destructive_command_callback = make_shell_guard(_DESTRUCTIVE_GUARD_SPEC)


def register() -> None:
    register_callback("run_shell_command", destructive_command_callback)


register()
