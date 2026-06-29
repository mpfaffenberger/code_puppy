"""Metadata resolution for loaded plugins.

Surfaces metadata the plugin system tracks but never displayed: the plugin's
module docstring (as a description), its on-disk path, and the lifecycle hook
phases it registers callbacks for. Kept separate from ``plugins_menu`` so the
TUI stays focused on rendering.
"""

from __future__ import annotations

import sys
from typing import List, Optional, get_args

# Module-name templates per tier, mirroring how the plugin loader registers
# each tier in ``sys.modules`` (see code_puppy/plugins/__init__.py).
_MODULE_TEMPLATES = {
    "builtin": "code_puppy.plugins.{name}.register_callbacks",
    "user": "{name}.register_callbacks",
    "project": "project_plugins.{name}.register_callbacks",
}


def _resolve_module(name: str, tier: str):
    """Return the loaded ``register_callbacks`` module for *name*/*tier*.

    Returns ``None`` if the module can't be found in ``sys.modules`` (e.g. a
    plugin that loaded via a bare ``__init__.py`` fallback).
    """
    template = _MODULE_TEMPLATES.get(tier)
    if not template:
        return None
    return sys.modules.get(template.format(name=name))


def get_description(name: str, tier: str) -> Optional[str]:
    """Return the first paragraph of the plugin's module docstring, or ``None``."""
    module = _resolve_module(name, tier)
    doc = getattr(module, "__doc__", None) if module else None
    if not doc:
        return None
    first_para = doc.strip().split("\n\n", 1)[0]
    return " ".join(line.strip() for line in first_para.splitlines()).strip() or None


def get_file_path(name: str, tier: str) -> Optional[str]:
    """Return the on-disk path of the plugin's ``register_callbacks`` module."""
    module = _resolve_module(name, tier)
    return getattr(module, "__file__", None) if module else None


def get_hooks(name: str) -> List[str]:
    """Return the sorted lifecycle phases *name* registered callbacks for.

    Disabled plugins still appear (``include_disabled=True``), so the preview
    shows what a plugin would hook into once re-enabled.
    """
    from code_puppy.callbacks import PhaseType, get_callback_owner, get_callbacks

    phases = [
        phase
        for phase in get_args(PhaseType)
        if any(
            get_callback_owner(func) == name
            for func in get_callbacks(phase, include_disabled=True)
        )
    ]
    return sorted(phases)
