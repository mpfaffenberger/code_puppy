"""Facade for the ``/set`` menu's setting registry.

The actual data lives in :mod:`set_menu_catalog`. This module is a
thin re-export so existing call sites can keep importing ``Setting``,
``SettingsCategory``, ``SETTINGS_CATEGORIES``, and
``iter_curated_settings`` from a single place.
"""

from __future__ import annotations

from code_puppy.command_line.set_menu_catalog import SETTINGS_CATEGORIES
from code_puppy.command_line.set_menu_schema import Setting, SettingsCategory

__all__ = [
    "Setting",
    "SettingsCategory",
    "SETTINGS_CATEGORIES",
    "iter_curated_settings",
]


def iter_curated_settings():
    """Yield ``(category, setting)`` pairs for every curated setting."""
    for category in SETTINGS_CATEGORIES:
        for setting in category.settings:
            yield category, setting
