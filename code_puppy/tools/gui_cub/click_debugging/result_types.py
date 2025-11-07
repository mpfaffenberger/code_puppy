"""Click debugging and coordinate verification tools for desktop automation."""

from __future__ import annotations


try:
    import pyautogui
    from PIL import Image, ImageDraw

    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    pyautogui = None
    Image = None
    ImageDraw = None

from pydantic import Field


from ..result_types import BaseAutomationResult


class ClickDebugResult(BaseAutomationResult):
    """Result from click debugging operations."""

    x: int = 0
    y: int = 0
    screen_color: list[int] | None = Field(
        None,
        description="RGB color as [r, g, b]",
        json_schema_extra={"items": {"type": "integer"}, "minItems": 3, "maxItems": 3},
    )
    screenshot_path: str | None = None
    message: str = ""


class CoordinateVerifyResult(BaseAutomationResult):
    """Result from coordinate verification."""

    x: int = 0
    y: int = 0
    is_valid: bool = False
    screen_width: int = 0
    screen_height: int = 0
    distance_from_edge: dict[str, int] | None = None


class HoverVerifyResult(BaseAutomationResult):
    """Result from hover verification (cursor position check)."""

    target_x: int = 0
    target_y: int = 0
    actual_x: int = 0
    actual_y: int = 0
    offset_x: int = 0
    offset_y: int = 0
    screenshot_path: str | None = None
    cursor_visible: bool = False
    message: str = ""


class SmartClickResult(BaseAutomationResult):
    """Result from smart click with retry logic."""

    target_x: int = 0
    target_y: int = 0
    actual_click_x: int = 0
    actual_click_y: int = 0
    attempts: int = 0
    successful_offset: tuple[int, int] | None = None
    verification_method: str = ""
    verification_passed: bool = False
    attempt_log: list[str] = Field(default_factory=list)
