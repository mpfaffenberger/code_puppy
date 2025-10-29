"""Unit tests for coordinate conversion utilities with mocked window bounds."""

from __future__ import annotations

from types import SimpleNamespace
import pytest

from code_puppy.tools.rpa.coordinates import window_to_screen_coords, screen_to_window_coords
from code_puppy.tools.rpa.result_types import WindowBoundsResult


def make_bounds(x: int, y: int) -> WindowBoundsResult:
    return WindowBoundsResult(success=True, x=x, y=y, width=400, height=300)


def test_window_to_screen_coords_with_provided_bounds():
    bounds = make_bounds(100, 50)
    sx, sy = window_to_screen_coords(200, 150, bounds)
    assert (sx, sy) == (300, 200)


def test_screen_to_window_coords_with_provided_bounds():
    bounds = make_bounds(100, 50)
    wx, wy = screen_to_window_coords(300, 200, bounds)
    assert (wx, wy) == (200, 150)


def test_window_to_screen_coords_raises_when_no_bounds(monkeypatch):
    # Patch provider in window_control where the function lives
    import code_puppy.tools.rpa.window_control as wc
    monkeypatch.setattr(wc, "_get_active_window_bounds_impl", lambda: WindowBoundsResult(success=False, error="nope"))
    with pytest.raises(ValueError):
        window_to_screen_coords(10, 10, None)


def test_screen_to_window_coords_raises_when_no_bounds(monkeypatch):
    import code_puppy.tools.rpa.window_control as wc
    monkeypatch.setattr(wc, "_get_active_window_bounds_impl", lambda: WindowBoundsResult(success=False, error="nope"))
    with pytest.raises(ValueError):
        screen_to_window_coords(10, 10, None)
