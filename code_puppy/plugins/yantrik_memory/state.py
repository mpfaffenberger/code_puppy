"""Runtime state for the yantrik_memory plugin.

A tiny JSON file at ``<YANTRIK_MEM_ROOT>/state.json`` records whether memory
is currently enabled. The slash commands ``/yantrik enable`` and
``/yantrik disable`` flip this flag; reads (recorder/retriever/tools) consult
``is_enabled()`` on every call so the toggle is live.

IMPORTANT — this plugin is **opt-in**. Unlike the puppy_kennel (which defaults
ON), ``is_enabled()`` returns ``False`` when no state file exists. A user must
explicitly run ``/yantrik enable`` to turn it on.

The env var ``YANTRIK_MEMORY_DISABLED=1`` is a separate, harder kill: it
prevents the plugin from registering callbacks at all. That's handled in
``register_callbacks``, not here.
"""

from __future__ import annotations

import json

from .config import YANTRIK_MEM_ROOT

STATE_PATH = YANTRIK_MEM_ROOT / "state.json"

DISABLED_TOOL_ERROR = (
    "Yantrik memory is currently disabled. "
    "Ask the user to run `/yantrik enable` to turn it on."
)


def is_enabled() -> bool:
    """Read the persisted enabled flag. Defaults to ``False`` (opt-in)."""
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False
    return bool(payload.get("enabled", False))


def set_enabled(value: bool) -> None:
    """Persist the enabled flag to the state file. Best-effort."""
    YANTRIK_MEM_ROOT.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps({"enabled": bool(value)}, indent=2), encoding="utf-8"
    )
