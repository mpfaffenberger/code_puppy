"""Screenshot capture functionality."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path
from tempfile import gettempdir, mkdtemp

from code_puppy.messaging import emit_error, emit_info

from ..dependencies import PIL_AVAILABLE, PYAUTOGUI_AVAILABLE
from ..platform import IS_MACOS

if PYAUTOGUI_AVAILABLE:
    import pyautogui
else:
    pyautogui = None

if PIL_AVAILABLE:
    from PIL import Image, ImageGrab
else:
    Image = None
    ImageGrab = None

from ..constants import (
    DEFAULT_GRID_SPACING,
    ERROR_PILLOW_MISSING,
    ERROR_PYAUTOGUI_MISSING,
)
from ..result_types import ScreenshotResult
from .image_utils import add_coordinate_grid

_TEMP_SCREENSHOT_ROOT = Path(
    mkdtemp(prefix="code_puppy_rpa_screenshots_", dir=gettempdir())
)


def _safe_screenshot(region: tuple[int, int, int, int] | None = None):
    """
    Thread-safe screenshot capture.

    CRITICAL: On macOS, pyautogui.screenshot() uses tkinter internally,
    which crashes with "NSWindow should only be instantiated on the main thread!"
    when called from background threads.

    Solution: Use PIL's ImageGrab.grab() on macOS (thread-safe CoreGraphics),
    and pyautogui.screenshot() on other platforms.

    Args:
        region: Optional tuple (x, y, width, height) in physical pixels

    Returns:
        PIL Image object

    Raises:
        RuntimeError: If PIL is not available on macOS (required for thread safety)
    """
    if IS_MACOS:
        # macOS: MUST use thread-safe PIL ImageGrab (CoreGraphics-based)
        if not PIL_AVAILABLE or ImageGrab is None:
            raise RuntimeError(
                "PIL/Pillow is required for thread-safe screenshots on macOS. "
                "Install with: uv pip install Pillow --index-url https://pypi.ci.artifacts.walmart.com/artifactory/api/pypi/external-pypi/simple --allow-insecure-host pypi.ci.artifacts.walmart.com"
            )

        if region:
            x, y, w, h = region
            # CRITICAL BUG FIX: ImageGrab.grab() on macOS expects LOGICAL coordinates (points),
            # not physical pixels! The region parameter passed to this function is in physical pixels,
            # so we must divide by the scale factor to convert to logical coordinates.
            from ..platform import get_screen_scale_factor

            scale_factor = get_screen_scale_factor()

            # Convert physical pixels to logical points for ImageGrab
            logical_x = int(x / scale_factor)
            logical_y = int(y / scale_factor)
            logical_w = int(w / scale_factor)
            logical_h = int(h / scale_factor)

            # ImageGrab.grab expects (left, top, right, bottom) in LOGICAL coordinates
            return ImageGrab.grab(
                bbox=(
                    logical_x,
                    logical_y,
                    logical_x + logical_w,
                    logical_y + logical_h,
                )
            )
        else:
            return ImageGrab.grab()
    else:
        # Windows/Linux: Use pyautogui (works fine on non-macOS)
        if not PYAUTOGUI_AVAILABLE:
            raise RuntimeError(
                "pyautogui is required for screenshots. "
                "Install with: uv pip install pyautogui --index-url https://pypi.ci.artifacts.walmart.com/artifactory/api/pypi/external-pypi/simple --allow-insecure-host pypi.ci.artifacts.walmart.com"
            )

        if region:
            return pyautogui.screenshot(region=region)
        else:
            return pyautogui.screenshot()


def build_screenshot_path(timestamp: str) -> Path:
    """Return the target path for a screenshot using a shared temp directory."""
    filename = f"desktop_screenshot_{timestamp}.png"
    return _TEMP_SCREENSHOT_ROOT / filename


def capture_screen(
    region: tuple[int, int, int, int] | None = None,
    save_screenshot: bool = True,
    add_grid: bool = False,
    grid_spacing: int = DEFAULT_GRID_SPACING,
    include_image: bool = False,
) -> ScreenshotResult:
    """
    Capture a screenshot of the desktop.

    DELEGATION PATTERN:
    By default, images are saved to disk but NOT included in the result
    as base64. This saves massive amounts of tokens while preserving
    the full-quality image for debugging.

    Args:
        region: Optional tuple (x, y, width, height) to capture specific region
        save_screenshot: Whether to save the screenshot to disk
        add_grid: Whether to add coordinate grid overlay
        grid_spacing: Distance between grid lines in pixels
        include_image: Include base64 image in result (default: False)

    Returns:
        ScreenshotResult containing screenshot info and optionally image bytes

    Token Impact:
        - include_image=False (default): ~50-100 tokens (metadata only)
        - include_image=True: ~120,000 tokens (base64 PNG)
        - Savings: 99.9%+
    """
    if not PYAUTOGUI_AVAILABLE:
        return ScreenshotResult(
            success=False, error=f"{ERROR_PYAUTOGUI_MISSING} and {ERROR_PILLOW_MISSING}"
        )

    from ..platform import get_screen_scale_factor

    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        scale_factor = get_screen_scale_factor()

        # Log screenshot capture details
        if region:
            x, y, w, h = region
            # Convert logical coordinates to physical pixels for pyautogui
            # pyautogui.screenshot() expects physical pixels on Retina displays
            phys_x = int(x * scale_factor)
            phys_y = int(y * scale_factor)
            phys_w = int(w * scale_factor)
            phys_h = int(h * scale_factor)

            emit_info(
                f"[cyan]📸 CAPTURING SCREENSHOT[/cyan]\n"
                f"[dim]   Mode: Region capture[/dim]\n"
                f"[dim]   Region (logical): ({x}, {y}) size {w}x{h}[/dim]\n"
                f"[dim]   Region (physical): ({phys_x}, {phys_y}) size {phys_w}x{phys_h}[/dim]\n"
                f"[dim]   Grid overlay: {'Yes' if add_grid else 'No'}[/dim]"
            )
            screenshot = _safe_screenshot(region=(phys_x, phys_y, phys_w, phys_h))
        else:
            emit_info(
                f"[cyan]📸 CAPTURING SCREENSHOT[/cyan]\n"
                f"[dim]   Mode: Full screen[/dim]\n"
                f"[dim]   Grid overlay: {'Yes' if add_grid else 'No'}[/dim]"
            )
            screenshot = _safe_screenshot()

        # Add coordinate grid if requested
        if add_grid:
            emit_info(
                f"[dim]🏛️  Adding coordinate grid (spacing: {grid_spacing}px)[/dim]"
            )
            screenshot = add_coordinate_grid(screenshot, grid_spacing=grid_spacing)

        # Convert to bytes
        img_bytes = BytesIO()
        screenshot.save(img_bytes, format="PNG")
        img_bytes.seek(0)
        screenshot_data = img_bytes.getvalue()

        file_size_mb = len(screenshot_data) / 1_000_000

        result = ScreenshotResult(
            success=True,
            screenshot_data=screenshot_data,
            timestamp=timestamp,
            width=screenshot.width,
            height=screenshot.height,
            format="PNG",  # capture_screen always saves as PNG
        )

        if save_screenshot:
            screenshot_path = build_screenshot_path(timestamp)
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            screenshot.save(screenshot_path)
            result.screenshot_path = str(screenshot_path)

            # DEBUG: Copy to CWD if debug mode enabled
            from ..config_manager import get_debug_screenshots_enabled

            if get_debug_screenshots_enabled():
                cwd_path = Path.cwd() / screenshot_path.name
                screenshot.save(cwd_path)
                emit_info(
                    f"[yellow]🐛 DEBUG: Screenshot copied to CWD: {cwd_path}[/yellow]"
                )

            emit_info(
                f"[green]✅ SCREENSHOT CAPTURED[/green]\n"
                f"[dim]   Size: {screenshot.width}x{screenshot.height} pixels ({file_size_mb:.2f} MB)[/dim]\n"
                f"[dim]   Saved: {screenshot_path}[/dim]"
            )
        else:
            emit_info(
                f"[green]✅ SCREENSHOT CAPTURED[/green]\n"
                f"[dim]   Size: {screenshot.width}x{screenshot.height} pixels ({file_size_mb:.2f} MB)[/dim]\n"
                f"[dim]   (Not saved to disk)[/dim]"
            )

        # Add base64 image if requested (delegation pattern - excluded by default)
        if include_image:
            import base64

            result.image_base64 = base64.b64encode(screenshot_data).decode("utf-8")
            emit_info(
                f"[yellow]⚠️  Image included in result (~{file_size_mb:.2f} MB base64)[/yellow]\n"
                f"[dim]   Token cost: ~{int(file_size_mb * 100_000)} tokens[/dim]\n"
                f"[dim]   Consider using include_image=False for 99%+ token savings[/dim]"
            )

        return result

    except Exception as e:
        emit_error(
            f"[red]❌ SCREENSHOT FAILED[/red]\n"
            f"[dim]   Error: {e}[/dim]\n"
            f"[dim]   Region: {region if region else 'Full screen'}[/dim]"
        )
        return ScreenshotResult(success=False, error=str(e))


def screenshot(
    x: int | None = None,
    y: int | None = None,
    width: int | None = None,
    height: int | None = None,
    window_title: str | None = None,
    mode: str = "active_window",
    save_path: str | None = None,
    add_grid: bool = False,
    grid_spacing: int = DEFAULT_GRID_SPACING,
    include_image: bool = False,
) -> ScreenshotResult:
    """
    Unified screenshot capture function.

    Combines functionality from:
    - capture_screen() - Base capture
    - desktop_screenshot() - Parameter conversion
    - Window detection logic from VQA functions

    DELEGATION PATTERN:
    Screenshots are saved to disk by default but NOT included in results
    as base64 unless explicitly requested. This achieves 99%+ token savings.

    Args:
        x, y, width, height: Region coordinates (all must be provided together)
        window_title: Focus and capture specific window
        mode: "active_window" (default), "full_screen", "region"
        save_path: Custom save path (None = auto temp path)
        add_grid: Add coordinate grid overlay
        grid_spacing: Grid line spacing in pixels
        include_image: Include base64 image in result (default: False)

    Returns:
        ScreenshotResult with path, bytes, dimensions

    Examples:
        # Full screen
        screenshot(mode="full_screen")

        # Active window (default)
        screenshot()

        # Specific window
        screenshot(window_title="Terminal")


    Tiered Strategy Benefits:
    - Active window captures reduce noise and focus on relevant content
    - Automatic fallback prevents screenshot failures
    - Explicit coordinates override for precise control
    - Graceful degradation ensures screenshots always succeed
    """
    from pathlib import Path

    # TIERED LOCATION STRATEGY:
    # 1. Explicit coordinates (if all provided)
    # 2. Active window bounds (default, most focused)
    # 3. Full screen (fallback if window detection fails)

    region = None
    capture_strategy = None

    # TIER 1: Explicit coordinates (highest priority - user knows what they want)
    if x is not None and y is not None and width is not None and height is not None:
        region = (x, y, width, height)
        capture_strategy = "region"
        mode = "region"  # Override mode

    # TIER 2: Window-based capture (try active window or specific window)
    elif mode != "full_screen":
        from ..window_control import _focus_window_impl, _get_active_window_bounds_impl
        import time

        # If window title provided, focus it first
        if window_title:
            focus_result = _focus_window_impl(window_title)
            if focus_result.success:
                time.sleep(0.3)  # Wait for window to focus

        # Try to get active window bounds
        bounds_result = _get_active_window_bounds_impl()
        if bounds_result.success and bounds_result.x is not None:
            region = (
                bounds_result.x,
                bounds_result.y,
                bounds_result.width,
                bounds_result.height,
            )
            capture_strategy = (
                f"active_window ({bounds_result.window_title or 'unknown'})"
            )
        else:
            # TIER 3: Fallback to full screen if window detection fails
            emit_info(
                "⚠️ Could not detect active window, falling back to full screen capture"
            )
            region = None
            capture_strategy = "full_screen (fallback)"
    else:
        # TIER 3: Explicit full screen mode
        region = None
        capture_strategy = "full_screen (explicit)"

    # Log capture strategy for debugging
    if capture_strategy:
        emit_info(f"📸 Screenshot strategy: {capture_strategy}")

    # Determine if we should save to disk
    # - Always save if user provided custom save_path
    # - Save focused captures (active_window, region) by default
    # - Don't save full_screen by default (large files, less useful)
    should_save = save_path is not None or mode != "full_screen"

    # Capture the screenshot using existing capture_screen
    result = capture_screen(
        region=region,
        save_screenshot=should_save,
        add_grid=add_grid,
        grid_spacing=grid_spacing,
        include_image=include_image,  # Pass through delegation parameter
    )

    # Add metadata about capture strategy to result
    if result.success and capture_strategy:
        result.capture_strategy = capture_strategy

    # If custom save path provided, move the file
    if save_path and result.success and result.screenshot_path:
        import shutil

        dest_path = Path(save_path).resolve()
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        shutil.move(result.screenshot_path, str(dest_path))
        result.screenshot_path = str(dest_path)

    return result
