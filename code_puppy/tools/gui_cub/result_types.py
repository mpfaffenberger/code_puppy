"""Pydantic models for desktop automation tool return types."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class BaseAutomationResult(BaseModel):
    """Base result type for all desktop automation operations."""

    success: bool
    error: str | None = None


class CompactSummary(BaseModel):
    """Standardized summary for gui-cub compaction results.

    Provides consistent, machine-readable metadata about data compaction
    applied to results from OCR, accessibility, VQA, and other gui-cub tools.

    This enables:
    - Agents to understand what was filtered and why
    - Clear path to accessing full data when needed
    - Token budget awareness and optimization
    - Debugging and troubleshooting
    """

    # === Core Metadata ===
    tool: str  # "ocr_extract", "accessibility_tree", "vqa", "ocr_find"
    success: bool
    timestamp: str | None = None

    # === Data Counts ===
    found_count: int  # Total elements/items found before filtering
    returned_count: int  # Elements returned after compaction
    filtered_count: int  # Elements filtered out (found - returned)

    # === Human-Readable ===
    one_line: str  # Brief summary: "Found 150 text elements, showing top 10"
    top_items: list[str] | None = None  # Preview: ["Submit", "Cancel", "OK"]

    # === Compaction Metrics ===
    compaction_ratio: float  # Ratio kept: 0.067 = 6.7% kept, 93.3% filtered
    estimated_tokens_full: int | None = None  # Estimated original size
    estimated_tokens_compact: int | None = None  # Estimated compacted size
    tokens_saved: int | None = None  # Estimated savings

    # === Filtering Details ===
    filters_applied: list[str] | None = None  # ["confidence > 0.7", "top 10"]
    thresholds: dict[str, Any] | None = None  # {"confidence": 0.7, "max_elements": 10}

    # === Quality Metrics (tool-specific) ===
    confidence_stats: dict[str, float] | None = (
        None  # {"min": 0.7, "max": 0.98, "avg": 0.87}
    )
    element_types: dict[str, int] | None = None  # {"AXButton": 8, "AXTextField": 4}

    # === Debug Access ===
    detail_hint: str | None = None  # "Use _internal=True for full data"
    full_data_available: bool = True  # Can get uncompacted version?
    progressive_hints: list[str] | None = None  # Step-by-step help

    # === Tool-Specific Extensions ===
    extra: dict[str, Any] | None = None  # Extensible for tool-specific metadata


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
    platform: str | None = None  # Platform-specific shortcut used (macOS, Windows)


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
    """Result from screenshot operation.

    Delegation Pattern:
    By default, screenshot data is NOT included in results (only path).
    Images are always saved to disk for debugging, but excluded from
    agent context to save tokens.

    Token Impact:
    - With image: ~120,000 tokens (1920x1080 PNG)
    - Without image: ~50-100 tokens (metadata only)
    - Savings: 99.9%+
    """

    screenshot_path: str | None = None
    timestamp: str | None = None
    width: int | None = None
    height: int | None = None
    screenshot_data: bytes | None = Field(default=None, exclude=True)  # Don't serialize
    image_base64: str | None = None  # Only included if include_image=True
    format: str = "PNG"  # Image format: 'PNG' or 'JPEG'
    capture_strategy: str | None = (
        None  # Tier used: "region", "active_window", "full_screen", etc.
    )


class VQAResult(BaseAutomationResult):
    """Result from visual question answering.

    Uses success-conditional compaction AND delegation pattern:
    - On success: Returns answer, confidence, screenshot path only (no image)
    - On failure: Returns full screenshot metadata for debugging
    - Image only included if explicitly requested via include_image=True

    Delegation Pattern:
    The screenshot is analyzed in a SEPARATE agent context (vision model),
    and only the text analysis is returned to the main agent. This achieves
    99%+ token savings while maintaining full-quality image analysis.

    Token Impact:
    - With image: ~120,000 tokens (base64 encoded PNG)
    - Without image: ~200-500 tokens (text analysis only)
    - Savings: 99.6%+ 🚀
    """

    question: str
    answer: str | None = None
    confidence: float | None = None

    # Compact fields (always included)
    screenshot_path: str | None = None  # File path for debugging
    summary: str | dict | None = None  # NEW: Optional CompactSummary

    # Image field (delegation pattern - excluded by default)
    image_base64: str | None = None  # Only included if include_image=True

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

    # NEW: Comprehensive searchable attributes
    value: str | None = None  # Current value
    placeholder: str | None = None  # Placeholder text (text fields)
    help: str | None = None  # Help/tooltip text
    role_description: str | None = None  # Human-readable role
    identifier: str | None = None  # AXIdentifier (macOS) / AutomationId (Windows)
    subrole: str | None = None  # AXSubrole (macOS)

    # Platform-specific (Windows)
    control_type: str | None = None  # Windows
    class_name: str | None = None  # Windows
    auto_id: str | None = None  # Windows (alias for identifier)

    # Matching/search confidence
    confidence: float | None = None  # Match confidence score (0.0-1.0)


class ElementSearchResult(BaseAutomationResult):
    """Result from element search operation."""

    found: bool = False
    count: int | None = None
    matches: list[ElementInfo] | None = None
    best_match: ElementInfo | None = None


class ElementClickResult(BaseAutomationResult):
    """Result from element click operation."""

    clicked: bool = False
    element_found: bool = False  # For VQA - whether element was detected
    method: Literal["ax_press", "mouse_click", "native_click", "vqa_click"] | None = (
        None
    )
    element: str | None = None
    role: str | None = None
    click_x: int | None = None  # For VQA - clicked coordinates
    click_y: int | None = None  # For VQA - clicked coordinates
    x: int | None = None  # Alias for click_x (backward compat)
    y: int | None = None  # Alias for click_y (backward compat)
    confidence: float | None = None  # For VQA - detection confidence


class ElementListResult(BaseAutomationResult):
    """Result from listing elements.

    Uses success-conditional compaction:
    - On success: Returns filtered actionable elements only
    - On failure/empty: Returns full tree for debugging
    """

    total_elements: int = 0
    filtered_count: int = 0  # Number of actionable elements in compact mode
    summary: str | dict = ""  # Brief description (can be CompactSummary dict or string)

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
    scale_factor: float = 1.0  # HiDPI scale (2.0 for Retina, 1.0 for standard)
    scale_factor_detected: bool = False  # True if scale was detected via native API


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


class AppLaunchResult(BaseAutomationResult):
    """Result from launching macOS application."""

    app_name: str | None = None
    method: Literal["open_command", "applescript"] | None = None
    pid: int | None = None
