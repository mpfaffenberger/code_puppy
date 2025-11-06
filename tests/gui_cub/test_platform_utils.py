"""Unit tests for platform utilities: detection, scaling, conversions, and display info.
We mock pyautogui to avoid real OS calls.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch


import code_puppy.tools.gui_cub.platform as platform


@patch("sys.platform", "darwin")
def test_get_platform_and_display_name_macos():
    import importlib
    import code_puppy.tools.gui_cub.platform as platform_local

    importlib.reload(platform_local)
    assert platform_local.get_platform().name == "MACOS"
    assert platform_local.get_platform_display_name() == "macOS"


@patch("sys.platform", "win32")
def test_get_platform_and_display_name_windows():
    import importlib
    import code_puppy.tools.gui_cub.platform as platform_local

    importlib.reload(platform_local)
    assert platform_local.get_platform().name == "WINDOWS"
    assert platform_local.get_platform_display_name() == "Windows"


def test_convert_screenshot_to_screen_coords_uses_scale(monkeypatch):
    monkeypatch.setattr(platform, "get_screen_scale_factor", lambda: 2.0)
    x, y = platform.convert_screenshot_to_screen_coords(200, 100)
    assert (x, y) == (100, 50)


def test_get_screen_scale_factor_robust(monkeypatch):
    # Inject pyautogui with controlled size and screenshot
    class DummyImage:
        def __init__(self, w: int, h: int):
            self.size = (w, h)

    import sys

    sys.modules["pyautogui"] = SimpleNamespace(
        size=lambda: (100, 50), screenshot=lambda: DummyImage(200, 100)
    )
    import importlib
    import code_puppy.tools.gui_cub.platform as platform_local

    importlib.reload(platform_local)
    scale = platform_local.get_screen_scale_factor()
    assert scale == 2.0
    scale = platform.get_screen_scale_factor()
    assert scale == 2.0


@patch("sys.platform", "darwin")
def test_check_macos_accessibility_permission_handles_missing(monkeypatch):
    # Simulate failure by raising exception to produce helpful error message
    def crash():
        raise RuntimeError("nope")

    import sys
    import importlib

    sys.modules["pyautogui"] = SimpleNamespace(
        position=crash,
        size=lambda: (100, 50),
        screenshot=lambda: SimpleNamespace(size=(100, 50)),
    )
    import code_puppy.tools.gui_cub.platform as platform_local

    importlib.reload(platform_local)
    ok, msg = platform_local.check_macos_accessibility_permission()
    assert ok is False
    assert isinstance(msg, str) and "Accessibility" in msg


def test_get_display_info(monkeypatch):
    # Stub pyautogui calls safely
    class DummyImage:
        def __init__(self, w: int, h: int):
            self.size = (w, h)

    import sys
    import importlib

    sys.modules["pyautogui"] = SimpleNamespace(
        size=lambda: (120, 80), screenshot=lambda: DummyImage(240, 160)
    )
    import code_puppy.tools.gui_cub.platform as platform_local

    importlib.reload(platform_local)
    platform_local.check_macos_accessibility_permission = lambda: (True, None)

    info = platform_local.get_display_info()
    assert info["logical_width"] == 120
    assert info["physical_height"] in (160, int(80 * info["scale_factor"]))
    assert "display_type" in info
