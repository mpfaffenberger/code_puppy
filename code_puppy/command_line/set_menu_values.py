"""Helpers for resolving and displaying setting values in the ``/set`` menu.

Two responsibilities, both tiny:

* :func:`get_effective_setting_value` — answer "what value should I show
  the user for this setting?" honoring the typed getter when one exists
  and falling back to the raw ``config.get_value`` otherwise.
* :func:`mask_value` — partially redact sensitive values (e.g. API tokens)
  so the menu can render them without giving away the whole secret.
"""

from __future__ import annotations

from typing import Any, Optional

from code_puppy.command_line.set_menu_settings import (
    SETTINGS_CATEGORIES,
    Setting,
)
from code_puppy.config import get_value

_MASK_KEEP_CHARS = 4
_MASK_ELLIPSIS = "..."


def _sensitive_keys() -> frozenset[str]:
    """Set of curated keys flagged ``sensitive=True``.

    Deliberately not cached: tests monkey-patch the categories registry,
    and the cost is negligible at the curated-setting scale (~20 keys).
    """
    return frozenset(
        setting.key
        for category in SETTINGS_CATEGORIES
        for setting in category.settings
        if setting.sensitive
    )


def is_sensitive_key(key: str) -> bool:
    """Return True if ``key`` is curated as a sensitive setting.

    Used by the slash-command path to decide whether to mask values in
    success messages without needing the full :class:`Setting` object.
    """
    return key in _sensitive_keys()


def is_default_value(setting: Setting) -> bool:
    """Return True when ``setting``'s displayed value comes from a default.

    Definition: a value is "from a default" iff the user has NOT written
    a non-empty value to puppy.cfg AND the typed ``effective_getter``
    nevertheless returns something. That's exactly the case the
    ``(Default)`` prefix is meant to flag.

    Settings with no ``effective_getter`` (the Dynamic section and a
    few aspirational curated keys) never report as default -- they're
    either explicitly set or render as ``(not set)``.
    """
    if setting.effective_getter is None:
        return False
    raw = get_value(setting.key)
    if raw is not None and raw != "":
        return False
    return get_effective_setting_value(setting) is not None


def _format_value(value: Any) -> str:
    """Render a Python value as a short, menu-friendly string."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        # Strip trailing zeros without losing precision; keep "0" as "0".
        text = f"{value:g}"
        return text
    return str(value)


def get_effective_setting_value(setting: Setting) -> Optional[str]:
    """Return the value the menu should display for ``setting``.

    Order of resolution:
      1. ``setting.effective_getter()`` if one is registered.
      2. Raw ``config.get_value(setting.key)``.

    Returns ``None`` only when both resolutions yield ``None``.
    """
    if setting.effective_getter is not None:
        try:
            value = setting.effective_getter()
        except Exception:
            # A misbehaving getter must not crash the menu.
            value = None
        if value is None:
            return None
        return _format_value(value)

    raw = get_value(setting.key)
    if raw is None:
        return None
    return _format_value(raw)


def mask_value(value: str) -> str:
    """Mask a sensitive value, keeping a small prefix/suffix for recognition.

    * 0-chars       -> ``""``
    * 1-8 chars     -> all ``*``s (still convey length)
    * 9+ chars      -> ``abcd...wxyz`` (first/last :data:`_MASK_KEEP_CHARS`)
    """
    if not value:
        return ""
    if len(value) <= _MASK_KEEP_CHARS * 2:
        return "*" * len(value)
    return f"{value[:_MASK_KEEP_CHARS]}{_MASK_ELLIPSIS}{value[-_MASK_KEEP_CHARS:]}"


def display_value(setting: Setting) -> Optional[str]:
    """Convenience: effective value, masked when ``setting.sensitive``."""
    value = get_effective_setting_value(setting)
    if value is None:
        return None
    if setting.sensitive:
        return mask_value(value)
    return value
