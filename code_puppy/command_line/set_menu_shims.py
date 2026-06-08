"""Effective-value shims for ``/set`` menu settings.

Some settings have their default values inlined at the call site rather
than wrapped in a typed accessor. The catalog in
:mod:`set_menu_settings` needs a callable to plug into the ``Setting``'s
``effective_getter``, so this module exposes a tiny shim per such key
that mirrors the inline default exactly.

Each shim is documented with the file/symbol whose behaviour it mirrors.
The proper fix is to add typed accessors to the relevant module and
delete the shim -- tracked as follow-up work, not in scope here.
"""

from __future__ import annotations

from code_puppy.config import get_value


def get_max_pause_seconds_effective() -> float:
    """Mirrors ``float(get_value('max_pause_seconds') or 180.0)`` at
    ``code_puppy/agents/event_stream_handler.py``."""
    val = get_value("max_pause_seconds")
    try:
        return float(val) if val else 180.0
    except (TypeError, ValueError):
        return 180.0


def get_goal_max_iterations_effective() -> int:
    """Mirrors :func:`code_puppy.plugins.wiggum.register_callbacks._get_goal_max_iterations`."""
    val = get_value("goal_max_iterations")
    try:
        n = int(val) if val else 10  # GOAL_MAX_ITERATIONS_DEFAULT
    except (TypeError, ValueError):
        n = 10
    return max(1, min(n, 1000))


def get_disable_mcp_servers_effective() -> bool:
    """Mirrors the inline check at ``tools/subagent_invocation.py``.

    There is no typed accessor in :mod:`code_puppy.config` for this key
    -- call sites parse the string themselves. This shim normalises the
    same way so the menu shows the runtime-effective bool.
    """
    val = get_value("disable_mcp_servers")
    if val is None:
        return False
    return str(val).strip().lower() in {"1", "true", "yes", "on"}
