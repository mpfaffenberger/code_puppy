"""Configuration for the puppy_kennel plugin.

Single source of truth for paths, defaults, and tunable knobs. The
on/off toggle lives in ``state.py`` and is persisted in ``puppy.cfg``
under ``kennel_enabled`` -- see that module.
"""

from __future__ import annotations

import os
from pathlib import Path

# Root directory for the kennel on disk.
KENNEL_ROOT = Path(
    os.environ.get("PUPPY_KENNEL_ROOT", Path.home() / ".code_puppy" / "kennel")
)

# The SQLite database file lives inside the kennel root.
DB_PATH = KENNEL_ROOT / "kennel.db"

# --------------------------------------------------------------------------- #
# Prompt-packing budget — how much of the system prompt we get to fill.
# --------------------------------------------------------------------------- #
# Total token budget for the recall block. A token is roughly 4 chars for
# Anglo-Saxon text; we use that ratio everywhere as a zero-dep estimator.
PROMPT_BUDGET_TOKENS = int(os.environ.get("PUPPY_KENNEL_PROMPT_BUDGET", "1500"))
CHARS_PER_TOKEN = 4
PROMPT_BUDGET_CHARS = PROMPT_BUDGET_TOKENS * CHARS_PER_TOKEN

# Per-class quotas. The remainder goes to recent context (P2).
USER_PREFS_QUOTA = float(os.environ.get("PUPPY_KENNEL_USER_PREFS_QUOTA", "0.30"))
STICKY_QUOTA = float(os.environ.get("PUPPY_KENNEL_STICKY_QUOTA", "0.30"))

# Drawers shorter than this are noise — skip them in the recall block.
MIN_DRAWER_CHARS = int(os.environ.get("PUPPY_KENNEL_MIN_DRAWER_CHARS", "80"))

# Cap on stored drawer text length (chars). Keeps SQLite happy and FTS indexes
# from getting comically large. Truncation is fine — verbatim within reason.
MAX_DRAWER_CHARS = int(os.environ.get("PUPPY_KENNEL_MAX_DRAWER_CHARS", "32000"))
