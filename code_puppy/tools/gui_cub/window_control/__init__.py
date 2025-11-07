"""Window control utilities."""

from __future__ import annotations

from .core import _get_active_window_bounds_impl, focus_window, get_active_window_bounds
from .tools import register_window_control_tools

__all__ = [
    "_get_active_window_bounds_impl",
    "focus_window",
    "get_active_window_bounds",
    "register_window_control_tools",
]
