"""Plugin-local config for the emoji_filter plugin."""

from __future__ import annotations

from code_puppy.config import get_value, set_config_value

_CONFIG_KEY = "emoji_filter"
_FALSY = ("false", "0", "no", "off")


def is_enabled() -> bool:
    """Return True if emoji filtering is enabled. Default: True.

    Explicit ``false/0/no/off`` disables. Anything else (including unset
    or an unparseable value) keeps the filter on. In the face of ambiguity,
    refuse the temptation to leak emojis.
    """
    cfg_val = get_value(_CONFIG_KEY)
    if cfg_val is None:
        return True
    return str(cfg_val).strip().lower() not in _FALSY


def set_enabled(enabled: bool) -> None:
    """Persist the on/off switch to mist.cfg."""
    set_config_value(_CONFIG_KEY, "true" if enabled else "false")
