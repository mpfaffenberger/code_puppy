"""Configuration for the statusline plugin (persisted in mist.cfg)."""

from __future__ import annotations

import logging

from code_puppy.config import get_value, set_value

logger = logging.getLogger(__name__)

KEY_ENABLED = "statusline_enabled"
KEY_COMMAND = "statusline_command"
KEY_TIMEOUT = "statusline_timeout_ms"
KEY_REFRESH = "statusline_refresh_ms"
KEY_MODE = "statusline_mode"

DEFAULT_TIMEOUT_MS = 1000
DEFAULT_REFRESH_MS = 1000
DEFAULT_MODE = "replace"
_VALID_MODES = ("replace", "above", "newline")


def _get_int(key: str, default: int) -> int:
    raw = get_value(key)
    if raw is None or raw == "":
        return default
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default


def is_enabled() -> bool:
    raw = get_value(KEY_ENABLED)
    if raw is None or raw == "":
        return False
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def set_enabled(value: bool) -> None:
    set_value(KEY_ENABLED, "true" if value else "false")


def get_command() -> str:
    return (get_value(KEY_COMMAND) or "").strip()


def set_command(command: str) -> None:
    set_value(KEY_COMMAND, command or "")


def get_timeout_ms() -> int:
    return max(100, _get_int(KEY_TIMEOUT, DEFAULT_TIMEOUT_MS))


def get_refresh_ms() -> int:
    return max(200, _get_int(KEY_REFRESH, DEFAULT_REFRESH_MS))


def get_mode() -> str:
    raw = (get_value(KEY_MODE) or "").strip().lower()
    return raw if raw in _VALID_MODES else DEFAULT_MODE


def set_mode(mode: str) -> None:
    mode = (mode or "").strip().lower()
    if mode in _VALID_MODES:
        set_value(KEY_MODE, mode)
