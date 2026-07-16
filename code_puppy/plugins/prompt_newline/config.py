"""Plugin-local config for the prompt_newline plugin."""

from __future__ import annotations

from code_puppy.config import get_value, set_config_value

_CONFIG_KEY = "prompt_newline"
_TRUTHY = ("true", "1", "yes", "on")


def is_enabled() -> bool:
    """Return True if the prompt_newline hack is enabled. Default: False."""
    cfg_val = get_value(_CONFIG_KEY)
    if cfg_val is None:
        return False
    return str(cfg_val).strip().lower() in _TRUTHY


def set_enabled(enabled: bool) -> None:
    """Persist the on/off switch to puppy.cfg."""
    set_config_value(_CONFIG_KEY, "true" if enabled else "false")
