"""Route unrecognized or compound shell commands through core approval."""

from __future__ import annotations

import json
from typing import Any

from code_puppy.callbacks import register_callback
from code_puppy.command_line.set_menu_schema import Setting, SettingsCategory

from .classifier import PrefixKind, classify_command
from .config import get_safe_prefixes


def shell_prefix_policy(
    context: Any,
    command: str,
    cwd: str | None = None,
    timeout: int = 60,
) -> dict[str, Any] | None:
    """Auto-allow configured simple prefixes; ask for every other command."""
    del context, cwd, timeout
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
                key="shell_safe_prefixes",
                display_name="Safe Shell Prefixes",
                description="JSON list of deterministic command prefixes allowed without prompting.",
                type_hint="string",
                effective_getter=lambda: json.dumps(sorted(get_safe_prefixes())),
            ),
        ),
    )


register_callback("run_shell_command", shell_prefix_policy)
register_callback("register_settings", _settings)
