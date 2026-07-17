"""Route unrecognized or compound shell commands through core approval."""

from __future__ import annotations

import json
from typing import Any

from code_puppy.callbacks import register_callback
from code_puppy.command_line.set_menu_schema import Setting, SettingsCategory

from .classifier import PrefixKind, classify_command
from .config import get_safe_prefixes, is_enforcement_enabled


def shell_prefix_policy(
    context: Any,
    command: str,
    cwd: str | None = None,
    timeout: int = 60,
) -> dict[str, Any] | None:
    """Auto-allow configured simple prefixes; ask for every other command.

    Dormant unless ``shell_prefix_enforcement`` is enabled. When off (the
    default), this never forces a prompt — approval is left to
    ``permission_mode`` so ``auto`` behaves like a true no-prompt mode.
    """
    del context, cwd, timeout
    if not is_enforcement_enabled():
        return None
    verdict = classify_command(command)
    if (
        verdict.kind is PrefixKind.PREFIX
        and verdict.prefix
        and verdict.prefix.lower() in get_safe_prefixes()
    ):
        return None
    return {
        "requires_approval": True,
        "classification": verdict.kind.value,
        "prefix": verdict.prefix,
        "reason": verdict.reason,
    }


def _settings():
    return SettingsCategory(
        name="Safety",
        settings=(
            Setting(
                key="shell_prefix_enforcement",
                display_name="Shell Prefix Enforcement",
                description=(
                    "When ON, only allowlisted simple command prefixes run without a "
                    "prompt and everything else asks. OFF (default) defers shell "
                    "approval to permission_mode, so auto runs without prompting."
                ),
                type_hint="choice",
                valid_values=("off", "on"),
                effective_getter=lambda: "on" if is_enforcement_enabled() else "off",
            ),
            Setting(
                key="shell_safe_prefixes",
                display_name="Safe Shell Prefixes",
                description="JSON list of deterministic command prefixes allowed without prompting (only when enforcement is ON).",
                type_hint="string",
                effective_getter=lambda: json.dumps(sorted(get_safe_prefixes())),
            ),
        ),
    )


register_callback("run_shell_command", shell_prefix_policy)
register_callback("register_settings", _settings)
