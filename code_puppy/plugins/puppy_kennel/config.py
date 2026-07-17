"""Configuration for Mist's local-memory plugin.

Single source of truth for paths, defaults, and tunable knobs. The
on/off toggle lives in ``state.py`` and is persisted in ``mist.cfg``
under ``kennel_enabled`` -- see that module.
"""

from __future__ import annotations

import os
from pathlib import Path


def _env(primary: str, legacy: str, default: str | Path) -> str:
    """Read a Mist setting while preserving the previous environment key."""
    return os.environ.get(primary, os.environ.get(legacy, str(default)))


# Root directory for the kennel on disk.
KENNEL_ROOT = Path(
    _env("MIST_MEMORY_ROOT", "PUPPY_KENNEL_ROOT", Path.home() / ".mist" / "kennel")
)

# The SQLite database file lives inside the kennel root.
DB_PATH = KENNEL_ROOT / "kennel.db"

# --------------------------------------------------------------------------- #
# Prompt-packing budget — how much of the system prompt we get to fill.
# --------------------------------------------------------------------------- #
# Total token budget for the recall block. A token is roughly 4 chars for
# Anglo-Saxon text; we use that ratio everywhere as a zero-dep estimator.
PROMPT_BUDGET_TOKENS = int(
    _env("MIST_MEMORY_PROMPT_BUDGET", "PUPPY_KENNEL_PROMPT_BUDGET", "1500")
)
CHARS_PER_TOKEN = 4
PROMPT_BUDGET_CHARS = PROMPT_BUDGET_TOKENS * CHARS_PER_TOKEN

# Per-class quotas. The remainder goes to recent context (P2).
USER_PREFS_QUOTA = float(
    _env("MIST_MEMORY_USER_PREFS_QUOTA", "PUPPY_KENNEL_USER_PREFS_QUOTA", "0.30")
)
STICKY_QUOTA = float(
    _env("MIST_MEMORY_STICKY_QUOTA", "PUPPY_KENNEL_STICKY_QUOTA", "0.30")
)

# Drawers shorter than this are noise — skip them in the recall block.
MIN_DRAWER_CHARS = int(
    _env("MIST_MEMORY_MIN_DRAWER_CHARS", "PUPPY_KENNEL_MIN_DRAWER_CHARS", "80")
)

# Cap on stored drawer text length (chars). Keeps SQLite happy and FTS indexes
# from getting comically large. Truncation is fine — verbatim within reason.
MAX_DRAWER_CHARS = int(
    _env("MIST_MEMORY_MAX_DRAWER_CHARS", "PUPPY_KENNEL_MAX_DRAWER_CHARS", "32000")
)
