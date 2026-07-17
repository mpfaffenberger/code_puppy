"""Require approval when a configured sandbox cannot be used."""

from typing import Any

from code_puppy.callbacks import register_callback
from code_puppy.command_line.set_menu_schema import Setting, SettingsCategory
from code_puppy.sandbox import get_sandbox_backend


def sandbox_availability_policy(
    context: Any,
    command: str,
    cwd: str | None = None,
    timeout: int = 60,
):
    del context, command, cwd, timeout
    try:
        backend = get_sandbox_backend()
    except ValueError as exc:
        return {"blocked": True, "error_message": str(exc)}
    if backend.name != "none" and not backend.available():
        return {
            "requires_approval": True,
            "sandbox_fallback": True,
            "reason": (
                f"Configured sandbox {backend.name!r} is unavailable; "
                "approval is required for unsandboxed execution."
            ),
        }
    return None


def _settings():
    return SettingsCategory(
        name="Safety",
        settings=(
            Setting(
                key="sandbox_backend",
                display_name="Shell Sandbox",
                description="Contain shell and background commands; none preserves host execution.",
                type_hint="choice",
                valid_values=(
                    "none",
                    "auto",
                    "bubblewrap",
                    "sandbox_exec",
                    "container",
                ),
                effective_getter=lambda: get_sandbox_backend().name,
            ),
        ),
    )


register_callback("run_shell_command", sandbox_availability_policy)
register_callback("register_settings", _settings)
