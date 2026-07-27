"""Compatibility shim for the relocated token-usage module.

Token accounting moved from this plugin into the core module
``code_puppy.token_usage`` so that more than one consumer (the
``context_indicator`` plugin, the ``statusline`` plugin, and the ``herdr``
integration) can share it without cross-plugin imports.

This module remains as a thin re-export so existing import sites and tests
that reference ``code_puppy.plugins.context_indicator.usage`` keep working
and observe the *same* objects as the core module (identity is preserved).
New code should import from :mod:`code_puppy.token_usage` directly.
"""

from __future__ import annotations

from code_puppy.token_usage import (
    GREEN_CIRCLE,
    GREEN_THRESHOLD,
    RED_CIRCLE,
    YELLOW_CIRCLE,
    YELLOW_THRESHOLD,
    ContextUsage,
    OverheadBreakdown,
    compute_overhead_breakdown,
    get_current_usage,
    pick_indicator,
)

__all__ = [
    "ContextUsage",
    "OverheadBreakdown",
    "get_current_usage",
    "compute_overhead_breakdown",
    "pick_indicator",
    "GREEN_THRESHOLD",
    "YELLOW_THRESHOLD",
    "GREEN_CIRCLE",
    "YELLOW_CIRCLE",
    "RED_CIRCLE",
]
