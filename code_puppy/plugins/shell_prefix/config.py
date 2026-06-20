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
