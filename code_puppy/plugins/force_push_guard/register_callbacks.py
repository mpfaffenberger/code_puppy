"""Callback registration for the force push guardrails plugin.

Hooks into the run_shell_command phase to intercept git force push commands
before they can rewrite remote history or destroy others' work.
"""

from code_puppy.callbacks import register_callback
from code_puppy.plugins.force_push_guard.detector import detect_force_push
from code_puppy.plugins.guard_framework import GuardSpec, make_shell_guard

_FORCE_PUSH_GUARD_SPEC = GuardSpec(
    title="Force Push Guardrails",
    detected_label="Force push detected: ",
    consequence="Force pushing rewrites remote history and can destroy others' work.",
    block_advice=(
        "If you really need to force push, run the exact command in your own "
        "terminal after double-checking the target branch."
    ),
    detect=detect_force_push,
)


force_push_callback = make_shell_guard(_FORCE_PUSH_GUARD_SPEC)


def register() -> None:
    register_callback("run_shell_command", force_push_callback)


register()
