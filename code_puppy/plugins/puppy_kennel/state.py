"""Runtime state for the puppy_kennel plugin.

Single source of truth for whether the kennel is on. Flipped by the
``/kennel enable`` and ``/kennel disable`` slash commands. Persisted in
``mist.cfg`` under the key ``kennel_enabled`` so the front end can read
and write the same value.

Default is **enabled** -- a missing key, blank value, or garbage value
all leave the kennel on. Only the explicit-falsy tokens
``{"false", "0", "no", "off"}`` (case-insensitive) turn it off. That
asymmetry is on purpose: on a default-on system, a typo like
``kennel_enabled = noep`` must not silently kill memory. In the face of
ambiguity, refuse to guess.

Reads and writes go through ``code_puppy.config.get_value`` /
``set_config_value``, the same helpers every other plugin (statusline,
prompt_newline, ...) uses for mist.cfg interop.
"""

from __future__ import annotations

from code_puppy.config import get_value, set_config_value

_CFG_KEY = "kennel_enabled"
_FALSY = frozenset({"false", "0", "no", "off"})

DISABLED_TOOL_ERROR = (
    "Mist Memory memory is currently disabled. "
    "Ask the user to run `/kennel enable` to turn it back on."
)


def is_enabled() -> bool:
    """Return True if the kennel is on.

    Defaults to True when the key is missing, blank, or set to anything
    that isn't one of the explicit-falsy tokens. Evaluated on every call
    so flipping the toggle takes effect immediately -- no relaunch
    required.
    """
    raw = get_value(_CFG_KEY)
    if raw is None:
        return True
    return str(raw).strip().lower() not in _FALSY


def set_enabled(value: bool) -> None:
    """Persist the kennel enable flag to mist.cfg (positive sense).

    Writes the literal string ``"true"`` or ``"false"`` so the on-disk
    representation is stable and any future FE consumer can parse the
    cfg directly without going through this helper.
    """
    set_config_value(_CFG_KEY, "true" if value else "false")
