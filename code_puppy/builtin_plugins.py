"""Plugins Code Puppy ships on top of pydantic-clai2's own.

Each entry is a clai2 plugin declaration. ``distribution`` appends them to
clai2's built-in set, so ``/plugins`` lists them as shipped and
``/plugins remove`` restores their defaults.
"""

from __future__ import annotations

from pydantic_clai2.config import PluginSettings

PUPPY_PLUGINS: tuple[PluginSettings, ...] = (
    PluginSettings(
        id="legacy_plugins", factory="code_puppy.compat.bridge:LegacyPlugins"
    ),
)
