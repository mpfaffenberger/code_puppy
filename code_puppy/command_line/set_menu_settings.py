"""Facade for the ``/set`` menu's setting registry.

The core data lives in :mod:`set_menu_catalog`; plugins add their own via
the ``register_settings`` hook. This module merges the two so every call
site sees one registry through :func:`iter_curated_settings`.
"""

from __future__ import annotations

from typing import Dict, Iterator, List, Tuple

from code_puppy.command_line.set_menu_catalog import SETTINGS_CATEGORIES
from code_puppy.command_line.set_menu_schema import Setting, SettingsCategory

__all__ = [
    "Setting",
    "SettingsCategory",
    "SETTINGS_CATEGORIES",
    "iter_curated_settings",
]


def _merged_categories() -> List[SettingsCategory]:
    """Core categories, then plugin ones; same-named categories merge in place."""
    from code_puppy.callbacks import on_register_settings

    merged: Dict[str, List[Setting]] = {}
    for category in (*SETTINGS_CATEGORIES, *on_register_settings()):
        merged.setdefault(category.name, []).extend(category.settings)
    return [SettingsCategory(name, tuple(items)) for name, items in merged.items()]


def iter_curated_settings() -> Iterator[Tuple[SettingsCategory, Setting]]:
    """Yield ``(category, setting)`` pairs for core and plugin settings.

    Keys are unique: core claims first, then plugins in load order, so a
    plugin can never shadow (or duplicate) a setting core already owns.
    """
    seen: set[str] = set()
    for category in _merged_categories():
        for setting in category.settings:
            if setting.key not in seen:
                seen.add(setting.key)
                yield category, setting
