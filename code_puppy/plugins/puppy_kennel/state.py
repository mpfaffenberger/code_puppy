"""Runtime state for the puppy_kennel plugin.

A tiny JSON file at ``<KENNEL_ROOT>/state.json`` records whether memory
is currently enabled. The slash commands ``/kennel enable`` and
``/kennel disable`` flip this flag; reads (recorder/retriever/tools)
consult ``is_enabled()`` on every call so the toggle is live.

The env var ``PUPPY_KENNEL_DISABLED=1`` is a separate, harder kill: it
prevents the plugin from registering callbacks at all. That's handled in
``register_callbacks``, not here.
"""

from __future__ import annotations

import json

from .config import KENNEL_ROOT

STATE_PATH = KENNEL_ROOT / "state.json"

DISABLED_TOOL_ERROR = (
    "Puppy Kennel memory is currently disabled. "
    "Ask the user to run `/kennel enable` to turn it back on."
)


def is_enabled() -> bool:
    """Read the persisted enabled flag. Defaults to True if no state file."""
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return True
    value = payload.get("enabled", True)
    return bool(value)


def set_enabled(value: bool) -> None:
    """Persist the enabled flag to the state file. Best-effort."""
    KENNEL_ROOT.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps({"enabled": bool(value)}, indent=2), encoding="utf-8"
    )
