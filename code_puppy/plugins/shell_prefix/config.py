"""Configuration for deterministic shell-prefix allowlisting."""

from __future__ import annotations

import json

from code_puppy.config import get_value

DEFAULT_SAFE_PREFIXES = frozenset(
    {
        "cat",
        "echo",
        "git diff",
        "git log",
        "git rev-parse",
        "git show",
        "git status",
        "head",
        "ls",
        "pwd",
        "rg",
        "tail",
        "wc",
        "which",
    }
)


_TRUTHY = frozenset({"1", "true", "on", "yes", "enabled", "enforce"})


def is_enforcement_enabled() -> bool:
    """Whether the prefix gate force-prompts non-allowlisted commands.

    Dormant by default: when off, the plugin never forces a shell prompt and
    command approval is governed solely by ``permission_mode`` (so ``auto``
    means auto). Turn it on with ``/set shell_prefix_enforcement=on`` to
    restore allowlist-only auto-running.
    """
    raw = get_value("shell_prefix_enforcement")
    if raw is None or str(raw).strip() == "":
        return False
    return str(raw).strip().lower() in _TRUTHY


def get_safe_prefixes() -> frozenset[str]:
    """Return a replacement allowlist from JSON or comma-separated config."""
    raw = get_value("shell_safe_prefixes")
    if not raw:
        return DEFAULT_SAFE_PREFIXES
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        parsed = [item.strip() for item in str(raw).split(",")]
    if not isinstance(parsed, list):
        return DEFAULT_SAFE_PREFIXES
    normalized = frozenset(
        str(item).strip().lower() for item in parsed if str(item).strip()
    )
    return normalized or DEFAULT_SAFE_PREFIXES
