"""Configuration for the yantrik_memory plugin.

Single source of truth for paths, defaults, and opt-out flags. All knobs are
environment-overridable so the plugin can be relocated / tuned without code
edits.
"""

from __future__ import annotations

import os
from pathlib import Path

# Root directory for the memory store on disk.
YANTRIK_MEM_ROOT = Path(
    os.environ.get(
        "YANTRIK_MEMORY_ROOT", Path.home() / ".code_puppy" / "yantrik_memory"
    )
)

# The YantrikDB store lives inside the root. ``load_engine`` treats this as the
# DB path (it manages its own file/dir layout underneath).
DB_PATH = YANTRIK_MEM_ROOT / "memory"

# Hard kill-switch: prevent the plugin from registering callbacks at all.
DISABLED = os.environ.get("YANTRIK_MEMORY_DISABLED", "").lower() in {
    "1",
    "true",
    "yes",
}

# --------------------------------------------------------------------------- #
# Embedder — YantrikDB picks the embedding engine off this env var. We default
# to the production ONNX MiniLM (384-dim) which is what the working-memory
# substrate was tuned against. ``substrate`` sets this before importing the
# engine so the choice actually takes effect.
# --------------------------------------------------------------------------- #
EMBEDDER = os.environ.get("YANTRIK_MEMORY_EMBEDDER", "onnx")

# --------------------------------------------------------------------------- #
# Distiller — local Ollama model that extracts durable facts from raw turns.
# Set YANTRIK_MEMORY_DISTILL=0 to log episodic turns only (no fact extraction).
# --------------------------------------------------------------------------- #
DISTILLER_ENABLED = os.environ.get("YANTRIK_MEMORY_DISTILL", "1").lower() not in {
    "0",
    "false",
    "no",
}
DISTILLER_MODEL = os.environ.get("YANTRIK_MEMORY_DISTILL_MODEL", "qwen3.5:4b-nothink")
DISTILLER_URL = os.environ.get(
    "YANTRIK_MEMORY_OLLAMA_URL", "http://localhost:11434/api/chat"
)
DISTILLER_TIMEOUT = float(os.environ.get("YANTRIK_MEMORY_DISTILL_TIMEOUT", "120"))

# --------------------------------------------------------------------------- #
# Recall packing knobs.
# --------------------------------------------------------------------------- #
# Size of the always-on "current" band (highest-importance durable facts).
PREFS_BAND_SIZE = int(os.environ.get("YANTRIK_MEMORY_PREFS_BAND", "8"))
# How many query-relevant history items to surface alongside.
HISTORY_TOP_K = int(os.environ.get("YANTRIK_MEMORY_HISTORY_TOP_K", "5"))
# Cap on how many known semantic facts we feed the distiller as update context.
MAX_KNOWN_FACTS = int(os.environ.get("YANTRIK_MEMORY_MAX_KNOWN_FACTS", "60"))
