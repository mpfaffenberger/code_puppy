"""Pydantic models for desktop automation tool return types."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class BaseAutomationResult(BaseModel):
    """Base result type for all desktop automation operations."""

    success: bool
    error: str | None = None


class MouseActionResult(BaseAutomationResult):
    """Result from mouse operations (move, click, drag, scroll)."""

    x: int | None = None
    y: int | None = None
    button: Literal["left", "right", "middle"] | None = None
    clicks: int | None = None


class MousePositionResult(BaseModel):
    """Result from getting mouse position."""

    x: int
    y: int


class MouseDragResult(BaseAutomationResult):
    """Result from mouse drag operation."""

    start_x: int | None = None
    start_y: int | None = None
    end_x: int | None = None
    end_y: int | None = None
    button: Literal["left", "right", "middle"] | None = None


class MouseScrollResult(BaseAutomationResult):
    """Result from mouse scroll operation."""

    clicks: int | None = None
    direction: Literal["up", "down"] | None = None


class KeyboardActionResult(BaseAutomationResult):
    """Result from keyboard operations (type, press, hotkey)."""

    text_length: int | None = None
    preview: str | None = None
    key: str | None = None
    presses: int | None = None
    hotkey: str | None = None
    keys: list[str] | None = None
    status: Literal["held", "released"] | None = None
    platform: str | None = (
        None  # Platform-specific shortcut used (macOS, Windows, Linux)
    )


class ScreenSizeResult(BaseModel):
    """Result from getting screen size."""

    width: int
    height: int


class ScreenshotInfo(BaseModel):
    """Information about a screenshot with DPI/downscale metadata."""

    path: str | None = None
    size: int | None = None  # bytes (after any downscaling)
    timestamp: str | None = None
    width: int | None = None  # physical bitmap width
    height: int | None = None  # physical bitmap height
    logical_width: int | None = None  # OS-reported screen width (logical points)
    logical_height: int | None = None  # OS-reported screen height (logical points)
    scale_x: float | None = None  # screen scale factor (physical/logical)
    scale_y: float | None = None
    original_width: int | None = None  # original bitmap width before VQA downscale
    original_height: int | None = None  # original bitmap height before VQA downscale
    vqa_width: int | None = None  # resized width for VQA API (if downscaled)
    vqa_height: int | None = None  # resized height for VQA API (if downscaled)
    vqa_scale_x: float | None = None  # vqa_width/original_width
    vqa_scale_y: float | None = None  # vqa_height/original_height
    region: list[int] | None = Field(
        None,
        description="Region as [x, y, width, height] in logical screen coordinates",
        json_schema_extra={"items": {"type": "integer"}, "minItems": 4, "maxItems": 4},
    )


class ScreenshotResult(BaseAutomationResult):
    """Result from screenshot operation."""

    screenshot_path: str | None = None
    timestamp: str | None = None
    width: int | None = None
    height: int | None = None
    screenshot_data: bytes | None = Field(default=None, exclude=True)  # Don't serialize
    format: str = "PNG"  # Image format: 'PNG' or 'JPEG'


class VQAResult(BaseAutomationResult):
    """Result from visual question answering.

    Uses success-conditional compaction:
    - On success: Returns answer, confidence, screenshot path only
    - On failure: Returns full screenshot metadata for debugging
    """

    question: str
    answer: str | None = None
    confidence: float | None = None

    # Compact field (always included)
    screenshot_path: str | None = None

    # Verbose fields (only on failure)
    observations: str | None = None
    screenshot_info: ScreenshotInfo | None = None
    window_bounds: WindowBoundsResult | None = None
    coordinate_system: Literal["window_relative", "screen_absolute"] = "window_relative"


class ElementInfo(BaseModel):
    """Information about a UI element."""

    role: str | None = None
    title: str | None = None
    description: str | None = None
    x: int | None = None
    y: int | None = None
    width: int | None = None
    height: int | None = None
    center_x: int | None = None
    center_y: int | None = None
    # Platform-specific
    control_type: str | None = None  # Windows
    class_name: str | None = None  # Windows
    auto_id: str | None = None  # Windows


class ElementSearchResult(BaseAutomationResult):
    """Result from element search operation."""

    found: bool = False
    count: int | None = None
    matches: list[ElementInfo] | None = None
    best_match: ElementInfo | None = None


class ElementClickResult(BaseAutomationResult):
    """Result from element click operation."""

    clicked: bool = False
    method: Literal["ax_press", "mouse_click", "native_click"] | None = None
    element: str | None = None
    role: str | None = None
    x: int | None = None
    y: int | None = None


class ElementListResult(BaseAutomationResult):
    """Result from listing elements.

    Uses success-conditional compaction:
    - On success: Returns filtered actionable elements only
    - On failure/empty: Returns full tree for debugging
    """

    total_elements: int = 0
    filtered_count: int = 0  # Number of actionable elements in compact mode
    summary: str = ""  # Brief description of elements found

    # Compact fields (actionable elements only)
    elements: list[dict[str, Any]] | None = None
    roles: list[str] | None = None
    types: list[str] | None = None

    # Verbose fields (full tree - only on failure or when explicitly requested)
    by_role: dict[str, list[dict[str, Any]]] | None = None
    by_type: dict[str, list[dict[str, Any]]] | None = None


class WindowFocusResult(BaseAutomationResult):
    """Result from window focus operation."""

    focused_app: str | None = None
    window: str | None = None


class WindowListResult(BaseAutomationResult):
    """Result from listing windows."""

    count: int = 0
    windows: list[dict[str, Any]] | None = None


class AlertResult(BaseAutomationResult):
    """Result from alert/confirm/prompt dialogs."""

    response: str | None = None
    cancelled: bool | None = None


class ImageLocationResult(BaseAutomationResult):
    """Result from image location operation."""

    found: bool = False
    left: int | None = None
    top: int | None = None
    width: int | None = None
    height: int | None = None
    center_x: int | None = None
    center_y: int | None = None


class SleepResult(BaseAutomationResult):
    """Result from sleep operation."""

    seconds: float | None = None


class MonitorInfo(BaseModel):
    """Information about a monitor/display."""

    index: int
    x: int
    y: int
    width: int
    height: int
    is_primary: bool = False


class MonitorsResult(BaseAutomationResult):
    """Result from getting monitor information."""

    count: int = 0
    monitors: list[MonitorInfo] | None = None
    primary_index: int | None = None


class MultiImageLocationResult(BaseAutomationResult):
    """Result from locating multiple instances of an image."""

    found: bool = False
    count: int = 0
    locations: list[dict[str, int]] | None = None


class PixelColorResult(BaseAutomationResult):
    """Result from pixel color check."""

    matches: bool = False
    expected: list[int] | None = Field(
        None,
        description="Expected RGB color as [r, g, b]",
        json_schema_extra={"items": {"type": "integer"}, "minItems": 3, "maxItems": 3},
    )
    actual: list[int] | None = Field(
        None,
        description="Actual RGB color as [r, g, b]",
        json_schema_extra={"items": {"type": "integer"}, "minItems": 3, "maxItems": 3},
    )
    position: dict[str, int] | None = None
    tolerance: int | None = None


class WindowBoundsResult(BaseAutomationResult):
    """Result from getting active window bounds."""

    x: int | None = None
    y: int | None = None
    width: int | None = None
    height: int | None = None
    app_name: str | None = None
    window_title: str | None = None
