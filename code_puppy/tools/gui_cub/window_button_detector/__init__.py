"""Window button detection."""

from __future__ import annotations

from .detector import find_window_button
from .types import (
    ButtonLocation,
    MacOSTrafficLightOffsets,
    WindowButton,
    WindowsControlOffsets,
)

__all__ = [
    "ButtonLocation",
    "MacOSTrafficLightOffsets",
    "WindowButton",
    "WindowsControlOffsets",
    "find_window_button",
]
