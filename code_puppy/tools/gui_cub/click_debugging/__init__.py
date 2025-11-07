"""Click debugging tools for verifying clicks and coordinates."""

from __future__ import annotations

from .result_types import (
    ClickDebugResult,
    CoordinateVerifyResult,
    HoverVerifyResult,
    SmartClickResult,
)
from .tools import register_click_debugging_tools
from .visualization import draw_pixel_grid

__all__ = [
    "ClickDebugResult",
    "CoordinateVerifyResult",
    "HoverVerifyResult",
    "SmartClickResult",
    "draw_pixel_grid",
    "register_click_debugging_tools",
]
