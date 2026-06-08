"""Schema types for the ``/set`` config menu catalog.

Kept in its own tiny module so the catalog file
(:mod:`set_menu_settings`) can stay focused on the actual setting
definitions without also bearing the dataclass declarations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Tuple


@dataclass(frozen=True)
class Setting:
    """Single config knob exposed to the menu."""

    key: str
    display_name: str
    description: str
    type_hint: str  # "bool" | "int" | "float" | "string" | "choice"
    valid_values: Tuple[str, ...] = ()
    effective_getter: Optional[Callable[[], Any]] = None
    sensitive: bool = False
    requires_restart: bool = False


@dataclass(frozen=True)
class SettingsCategory:
    """Named group of settings, rendered as a section header in the menu."""

    name: str
    settings: Tuple[Setting, ...] = field(default_factory=tuple)
