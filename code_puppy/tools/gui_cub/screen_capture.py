"""Screen capture and visual analysis for desktop automation."""

from __future__ import annotations

import asyncio
from datetime import datetime
from io import BytesIO
from pathlib import Path
from tempfile import gettempdir, mkdtemp

try:
    import pyautogui
    from PIL import Image

    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    pyautogui = None
    Image = None

from pydantic_ai import RunContext

from code_puppy.messaging import emit_error, emit_info, emit_warning
from code_puppy.tools.common import generate_group_id

from .constants import (
    DEFAULT_GRID_SPACING,
    ERROR_PILLOW_MISSING,
    ERROR_PYAUTOGUI_MISSING,
    GRID_LINE_COLOR,
    GRID_LINE_WIDTH,
    GRID_TEXT_COLOR,
)
from .result_types import ScreenshotInfo, ScreenshotResult, VQAResult
from .vqa_desktop import run_desktop_vqa_analysis

_TEMP_SCREENSHOT_ROOT = Path(
    mkdtemp(prefix="code_puppy_rpa_screenshots_", dir=gettempdir())
)

# VQA image size limit (Claude API has 5MB max, use 4.5MB for safety margin)
VQA_MAX_IMAGE_SIZE_BYTES = 4_500_000  # 4.5 MB
VQA_MAX_RESOLUTION = (1920, 1200)  # Max resolution for downscaling


def _build_screenshot_path(timestamp: str) -> Path:
    """Return the target path for a screenshot using a shared temp directory."""
    filename = f"desktop_screenshot_{timestamp}.png"
    return _TEMP_SCREENSHOT_ROOT / filename


def _resize_image_if_needed(
    image_bytes: bytes,
    max_size_bytes: int = VQA_MAX_IMAGE_SIZE_BYTES,
    max_resolution: tuple[int, int] = VQA_MAX_RESOLUTION,
) -> tuple[bytes, float, str]:
    """
    Resize image if it exceeds size limit, maintaining aspect ratio.

    This function uses a progressive compression strategy:
    1. First tries PNG optimization
    2. Then tries JPEG with progressively lower quality
    3. Finally resizes if needed with iterative quality reduction

    Args:
        image_bytes: Original PNG image bytes
        max_size_bytes: Maximum allowed file size in bytes
        max_resolution: Maximum (width, height) for downscaling

    Returns:
        Tuple of (resized_image_bytes, scale_factor, format)
        scale_factor is 1.0 if no resize needed, < 1.0 if downscaled
        format is 'PNG' or 'JPEG' indicating the output format
    """
    if not PYAUTOGUI_AVAILABLE:
        return image_bytes, 1.0, "PNG"

    # Check if resize needed
    if len(image_bytes) <= max_size_bytes:
        return image_bytes, 1.0, "PNG"

    # Load image
    img = Image.open(BytesIO(image_bytes))
    original_size = img.size

    # Convert RGBA to RGB if needed (JPEG doesn't support transparency)
    if img.mode == "RGBA":
        rgb_img = Image.new("RGB", img.size, (255, 255, 255))
        rgb_img.paste(img, mask=img.split()[3])  # Use alpha channel as mask
        img = rgb_img
    elif img.mode != "RGB":
        img = img.convert("RGB")

    # Strategy 1: Try PNG optimization first
    output = BytesIO()
    img.save(output, format="PNG", optimize=True)
    output.seek(0)
    compressed_bytes = output.getvalue()
    if len(compressed_bytes) <= max_size_bytes:
        return compressed_bytes, 1.0, "PNG"

    # Strategy 2: Try JPEG compression with progressively lower quality
    for quality in [95, 85, 75, 65, 55]:
        output = BytesIO()
        img.save(output, format="JPEG", quality=quality, optimize=True)
        output.seek(0)
        jpeg_bytes = output.getvalue()
        if len(jpeg_bytes) <= max_size_bytes:
            return jpeg_bytes, 1.0, "JPEG"

    # Strategy 3: Calculate scaling to fit within max_resolution
    width_scale = max_resolution[0] / original_size[0]
    height_scale = max_resolution[1] / original_size[1]
    scale_factor = min(width_scale, height_scale, 1.0)  # Don't upscale

    # If scale_factor is still 1.0 (image is within resolution limits),
    # we need to force downscaling since compression alone didn't work
    if scale_factor >= 1.0:
        # Calculate required scale based on file size ratio (with some buffer)
        size_ratio = max_size_bytes / len(image_bytes)
        # Use square root since area scales quadratically with linear dimensions
        scale_factor = min(0.8, (size_ratio * 0.9) ** 0.5)  # 90% of target for safety

    # Resize image with calculated scale factor
    new_size = (
        max(1, int(original_size[0] * scale_factor)),
        max(1, int(original_size[1] * scale_factor)),
    )
    resized_img = img.resize(new_size, Image.Resampling.LANCZOS)

    # Try JPEG compression on resized image with progressive quality reduction
    for quality in [95, 85, 75, 65, 55, 45]:
        output = BytesIO()
        resized_img.save(output, format="JPEG", quality=quality, optimize=True)
        output.seek(0)
        resized_bytes = output.getvalue()
        if len(resized_bytes) <= max_size_bytes:
            return resized_bytes, scale_factor, "JPEG"

    # Last resort: aggressive downscaling
    # If we're still too large, scale down further
    while len(resized_bytes) > max_size_bytes and scale_factor > 0.1:
        scale_factor *= 0.8
        new_size = (
            max(1, int(original_size[0] * scale_factor)),
            max(1, int(original_size[1] * scale_factor)),
        )
        resized_img = img.resize(new_size, Image.Resampling.LANCZOS)
        output = BytesIO()
        resized_img.save(output, format="JPEG", quality=55, optimize=True)
        output.seek(0)
        resized_bytes = output.getvalue()

    return resized_bytes, scale_factor, "JPEG"


def add_coordinate_grid(
    image: "Image.Image",
    grid_spacing: int = DEFAULT_GRID_SPACING,
    line_color: tuple[int, int, int, int] = GRID_LINE_COLOR,
    text_color: tuple[int, int, int] = GRID_TEXT_COLOR,
    line_width: int = GRID_LINE_WIDTH,
) -> "Image.Image":
    """
    Add a coordinate grid overlay to an image for VQA reference.

    Args:
        image: PIL Image to add grid to
        grid_spacing: Distance between grid lines in pixels
        line_color: RGBA color for grid lines
        text_color: RGB color for coordinate labels
        line_width: Width of grid lines in pixels

    Returns:
        New PIL Image with grid overlay
    """
    if not PYAUTOGUI_AVAILABLE:
        return image

    from PIL import ImageDraw, ImageFont

    # Create a copy to avoid modifying original
    img_with_grid = image.copy()
    draw = ImageDraw.Draw(img_with_grid, "RGBA")

    width, height = image.size

    # Try to load a font, fall back to default if not available
    try:
        # Try to use a system font
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
    except (OSError, AttributeError):
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16
            )
        except (OSError, AttributeError):
            # Fall back to default PIL font
            font = ImageFont.load_default()

    # Draw vertical grid lines
    for x in range(0, width, grid_spacing):
        draw.line([(x, 0), (x, height)], fill=line_color, width=line_width)
        # Add x-coordinate label at top
        label = str(x)
        # Draw text with background for visibility
        bbox = draw.textbbox((x + 2, 2), label, font=font)
        draw.rectangle(bbox, fill=(255, 255, 255, 200))  # White background
        draw.text((x + 2, 2), label, fill=text_color, font=font)

    # Draw horizontal grid lines
    for y in range(0, height, grid_spacing):
        draw.line([(0, y), (width, y)], fill=line_color, width=line_width)
        # Add y-coordinate label on left
        label = str(y)
        bbox = draw.textbbox((2, y + 2), label, font=font)
        draw.rectangle(bbox, fill=(255, 255, 255, 200))  # White background
        draw.text((2, y + 2), label, fill=text_color, font=font)

    return img_with_grid


def capture_screen(
    region: tuple[int, int, int, int] | None = None,
    save_screenshot: bool = True,
    add_grid: bool = False,
    grid_spacing: int = DEFAULT_GRID_SPACING,
) -> ScreenshotResult:
    """
    Capture a screenshot of the desktop.

    Args:
        region: Optional tuple (x, y, width, height) to capture specific region
        save_screenshot: Whether to save the screenshot to disk
        add_grid: Whether to add coordinate grid overlay
        grid_spacing: Distance between grid lines in pixels

    Returns:
        ScreenshotResult containing screenshot info and image bytes
    """
    if not PYAUTOGUI_AVAILABLE:
        return ScreenshotResult(
            success=False, error=f"{ERROR_PYAUTOGUI_MISSING} and {ERROR_PILLOW_MISSING}"
        )

    from code_puppy.messaging import emit_info, emit_error
    from .platform import get_screen_scale_factor

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
            screenshot = pyautogui.screenshot(region=(phys_x, phys_y, phys_w, phys_h))
        else:
            emit_info(
                f"[cyan]📸 CAPTURING SCREENSHOT[/cyan]\n"
                f"[dim]   Mode: Full screen[/dim]\n"
                f"[dim]   Grid overlay: {'Yes' if add_grid else 'No'}[/dim]"
            )
            screenshot = pyautogui.screenshot()

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
            screenshot_path = _build_screenshot_path(timestamp)
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            screenshot.save(screenshot_path)
            result.screenshot_path = str(screenshot_path)

            # DEBUG: Copy to CWD if debug mode enabled
            from .config_manager import get_debug_screenshots_enabled

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
) -> ScreenshotResult:
    """
    Unified screenshot capture function.

    Combines functionality from:
    - capture_screen() - Base capture
    - desktop_screenshot() - Parameter conversion
    - Window detection logic from VQA functions

    Args:
        x, y, width, height: Region coordinates (all must be provided together)
        window_title: Focus and capture specific window
        mode: "active_window" (default), "full_screen", "region"
        save_path: Custom save path (None = auto temp path)
        add_grid: Add coordinate grid overlay
        grid_spacing: Grid line spacing in pixels

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
    from code_puppy.messaging import emit_info

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
        from .window_control import _focus_window_impl, _get_active_window_bounds_impl
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
        from code_puppy.messaging import emit_info

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


async def screenshot_analyze(
    question: str | None = None,
    x: int | None = None,
    y: int | None = None,
    width: int | None = None,
    height: int | None = None,
    window_title: str | None = None,
    mode: str = "active_window",
    save_path: str | None = None,
    add_grid: bool = False,
    grid_spacing: int = DEFAULT_GRID_SPACING,
    confidence_threshold: float = 0.85,
    auto_refine: bool = False,
    language: str = "eng",
) -> dict:
    """
    Unified screenshot + analysis function.

    Combines functionality from:
    - take_desktop_screenshot_and_analyze() - VQA core
    - desktop_screenshot_analyze() - VQA wrapper
    - desktop_extract_text() - OCR analysis
    - desktop_screenshot_with_confidence() - Grid refinement

    Args:
        question: VQA question. If None, runs OCR instead.
        x, y, width, height: Region coordinates (all must be provided together)
        window_title: Focus and capture specific window
        mode: "active_window" (default), "full_screen", "region"
        save_path: Custom save path (None = auto temp path)
        add_grid: Add coordinate grid overlay
        grid_spacing: Grid line spacing in pixels
        confidence_threshold: Min confidence for auto-refine
        auto_refine: Automatically add grid if confidence low
        language: Tesseract language code (OCR only)

    Returns:
        Unified analysis result:
        {
            "success": bool,
            "screenshot_path": str,
            "analysis_type": "ocr" | "vqa",

            # OCR fields (if question=None)
            "full_text": str,
            "text_elements": list,
            "word_count": int,

            # VQA fields (if question provided)
            "question": str,
            "answer": str,
            "confidence": float,
            "observations": str,
        }

    Examples:
        # OCR analysis (default)
        result = await screenshot_analyze()
        print(result["full_text"])

        # VQA analysis
        result = await screenshot_analyze(
            question="Where is the Submit button?"
        )
        print(result["answer"])

        # VQA with auto grid refinement
        result = await screenshot_analyze(
            question="Find the OK button",
            auto_refine=True,
            confidence_threshold=0.9
        )
    """
    from .ocr_tools import extract_text_from_image
    from .vqa_desktop import run_desktop_vqa_analysis
    from PIL import Image
    import os

    # Determine if OCR or VQA mode
    is_ocr = question is None

    # Initial capture (without grid if auto_refine is enabled)
    initial_grid = add_grid if not auto_refine else False

    # Capture screenshot using unified screenshot() function
    screenshot_result = screenshot(
        x=x,
        y=y,
        width=width,
        height=height,
        window_title=window_title,
        mode=mode,
        save_path=save_path,
        add_grid=initial_grid,
        grid_spacing=grid_spacing,
    )

    if not screenshot_result.success:
        return {
            "success": False,
            "error": screenshot_result.error,
            "analysis_type": "ocr" if is_ocr else "vqa",
        }

    result = {
        "success": True,
        "screenshot_path": screenshot_result.screenshot_path,
    }

    if is_ocr:
        # OCR MODE
        # Load screenshot image
        screenshot_path = screenshot_result.screenshot_path
        if not screenshot_path or not os.path.exists(screenshot_path):
            return {
                "success": False,
                "error": "Screenshot file not found for OCR analysis",
                "analysis_type": "ocr",
            }

        image = Image.open(screenshot_path)
        ocr_result = extract_text_from_image(image, language=language)

        result["analysis_type"] = "ocr"
        result["full_text"] = ocr_result.full_text if ocr_result.success else ""
        result["text_elements"] = ocr_result.text_elements if ocr_result.success else []
        result["word_count"] = (
            len(result["full_text"].split()) if result["full_text"] else 0
        )

        if not ocr_result.success:
            result["success"] = False
            result["error"] = ocr_result.error

    else:
        # VQA MODE
        # Load screenshot image for VQA
        screenshot_path = screenshot_result.screenshot_path
        if not screenshot_path or not os.path.exists(screenshot_path):
            return {
                "success": False,
                "error": "Screenshot file not found for VQA analysis",
                "analysis_type": "vqa",
            }

        with open(screenshot_path, "rb") as f:
            image_bytes = f.read()

        # Run VQA analysis
        vqa_result = run_desktop_vqa_analysis(
            question=question,
            image_bytes=image_bytes,
            media_type="image/png",
        )

        result["analysis_type"] = "vqa"
        result["question"] = question
        result["answer"] = vqa_result.answer
        result["confidence"] = vqa_result.confidence
        result["observations"] = vqa_result.observations

        # Auto-refine logic: if confidence low, retry with grid
        if auto_refine and vqa_result.confidence < confidence_threshold:
            from code_puppy.messaging import emit_info

            emit_info(
                f"🔄 Confidence {vqa_result.confidence:.2f} below threshold {confidence_threshold:.2f}, "
                f"retrying with grid overlay"
            )

            # Retry with grid at increasing densities
            grid_densities = [
                ("low", 100),
                ("medium", 50),
                ("high", 25),
            ]

            for density_name, spacing in grid_densities:
                # Recapture with grid
                screenshot_result_grid = screenshot(
                    x=x,
                    y=y,
                    width=width,
                    height=height,
                    window_title=window_title,
                    mode=mode,
                    add_grid=True,
                    grid_spacing=spacing,
                )

                if screenshot_result_grid.success:
                    with open(screenshot_result_grid.screenshot_path, "rb") as f:
                        image_bytes_grid = f.read()

                    vqa_result_grid = run_desktop_vqa_analysis(
                        question=question,
                        image_bytes=image_bytes_grid,
                        media_type="image/png",
                    )

                    emit_info(
                        f"📊 Grid density '{density_name}' ({spacing}px): "
                        f"confidence {vqa_result_grid.confidence:.2f}"
                    )

                    # If confidence improved, use this result
                    if vqa_result_grid.confidence >= confidence_threshold:
                        result["answer"] = vqa_result_grid.answer
                        result["confidence"] = vqa_result_grid.confidence
                        result["observations"] = vqa_result_grid.observations
                        result["screenshot_path"] = (
                            screenshot_result_grid.screenshot_path
                        )
                        result["grid_refined"] = True
                        result["grid_density"] = density_name
                        break

                    # If last iteration, use best result even if below threshold
                    if spacing == 25:  # Last iteration
                        if vqa_result_grid.confidence > vqa_result.confidence:
                            result["answer"] = vqa_result_grid.answer
                            result["confidence"] = vqa_result_grid.confidence
                            result["observations"] = vqa_result_grid.observations
                            result["screenshot_path"] = (
                                screenshot_result_grid.screenshot_path
                            )
                            result["grid_refined"] = True
                            result["grid_density"] = density_name

    return result


def _compact_vqa_result(
    full_result: "VQAResult", truncate_answer: bool = True, max_answer_length: int = 500
) -> "VQAResult":
    """
    Compress VQA result to minimal data.

    Strategy:
    - Keep question, answer, confidence
    - Truncate answer to max_answer_length (default: 500 chars)
    - Keep screenshot path only (strip full metadata)
    - Remove verbose screenshot_info details

    Args:
        full_result: Full VQA result with all metadata
        truncate_answer: Whether to truncate long answers (default: True)
        max_answer_length: Maximum answer length in chars (default: 500)

    Returns:
        Compact VQA result with essentials only
    """
    from .result_types import VQAResult

    # Truncate answer if needed
    answer = full_result.answer
    if truncate_answer and answer and len(answer) > max_answer_length:
        answer = (
            answer[:max_answer_length]
            + "... (truncated. Use truncate_answer=False for full response)"
        )

    return VQAResult(
        success=full_result.success,
        question=full_result.question,
        answer=answer,
        confidence=full_result.confidence,
        screenshot_path=full_result.screenshot_info.path
        if full_result.screenshot_info
        else None,
        error=full_result.error,
        # Explicitly exclude verbose fields
        observations=None,
        screenshot_info=None,
        window_bounds=None,
        coordinate_system=full_result.coordinate_system,
    )


async def take_desktop_screenshot_and_analyze(
    question: str,
    region: tuple[int, int, int, int] | None = None,
    window_title: str | None = None,
    capture_mode: str = "active_window",
    save_screenshot: bool = True,
    use_grid: bool = False,  # Changed from True to False for cleaner UI
    grid_spacing: int = DEFAULT_GRID_SPACING,
    max_vqa_resolution: tuple[int, int] | None = None,
    truncate_answer: bool = True,  # NEW: Truncate answers by default
) -> VQAResult:
    """
    Take a desktop screenshot and analyze it using visual understanding.

    **DEFAULT: Captures active window only (not full screen).**
    This reduces image size, improves accuracy, and avoids VQA size limits.

    **HIGH-DPI DISPLAY HANDLING:**
    Screenshots from high-resolution displays (Retina, 4K, 5K) may exceed the VQA API's
    5MB image size limit. This function automatically downscales images > 4.5MB to a
    maximum resolution (default: 1920x1200) while maintaining aspect ratio. The original
    full-resolution screenshot is still saved to disk.

    Args:
        question: The specific question to ask about the screenshot
        region: Optional (x, y, width, height) tuple to capture specific region
                (overrides window_title and capture_mode if provided)
        window_title: Optional window/app name to focus and capture
                     If None, captures current active window
        capture_mode: "active_window" (default), "full_screen", or "region"
        save_screenshot: Whether to save the screenshot to disk
        use_grid: Whether to add coordinate grid (default: False for clarity)
        grid_spacing: Distance between grid lines in pixels
        max_vqa_resolution: Max (width, height) for VQA image downscaling (default: 1920x1200)

    Returns:
        VQAResult containing analysis results and screenshot info

    Examples:
        # Capture active window (default)
        >>> vqa = await desktop_screenshot_analyze(
        ...     question="Where is the Submit button?"
        ... )

        # Capture specific app window
        >>> vqa = await desktop_screenshot_analyze(
        ...     question="Find the OK button",
        ...     window_title="TextEdit"
        ... )

        # Full screen (old behavior)
        >>> vqa = await desktop_screenshot_analyze(
        ...     question="What's on screen?",
        ...     capture_mode="full_screen"
        ... )
    """
    # Determine target region and capture info
    target_region = None
    window_bounds = None
    coordinate_system = "screen_absolute"

    # If region explicitly provided, use it (backward compatibility)
    if region:
        target_region = region
        target = f"region({region[0]},{region[1]},{region[2]},{region[3]})"

    # If full screen requested, use None region
    elif capture_mode == "full_screen":
        target_region = None
        target = "full_screen"

    # Default: capture active window
    else:
        # Focus window if title provided
        if window_title:
            from .window_control import _focus_window_impl

            focus_result = _focus_window_impl(window_title)
            if not focus_result.success:
                emit_warning(
                    f"[yellow]Could not focus window '{window_title}', using current active window[/yellow]"
                )
            # Let window focus settle
            await asyncio.sleep(0.3)

        # Get active window bounds
        from .window_control import _get_active_window_bounds_impl

        bounds_result = _get_active_window_bounds_impl()

        if not bounds_result.success:
            emit_warning(
                "[yellow]Could not get window bounds, falling back to full screen[/yellow]"
            )
            target_region = None
            target = "full_screen_fallback"
        else:
            window_bounds = bounds_result
            target_region = (
                bounds_result.x,
                bounds_result.y,
                bounds_result.width,
                bounds_result.height,
            )
            target = f"window({bounds_result.window_title or bounds_result.app_name or 'active'})"
            coordinate_system = "window_relative"

    group_id = generate_group_id(
        "desktop_screenshot_analyze", f"{question[:50]}_{target}"
    )
    emit_info(
        f"[bold white on blue] DESKTOP SCREENSHOT ANALYZE [/bold white on blue] 📷 question='{question[:100]}{'...' if len(question) > 100 else ''}' target={target}",
        message_group=group_id,
    )

    try:
        # Take screenshot (with optional grid overlay)
        screenshot_result = capture_screen(
            region=target_region,
            save_screenshot=save_screenshot,
            add_grid=use_grid,
            grid_spacing=grid_spacing,
        )

        if not screenshot_result.success:
            error_message = screenshot_result.error or "Screenshot failed"
            emit_error(
                f"[red]Screenshot capture failed: {error_message}[/red]",
                message_group=group_id,
            )
            return VQAResult(success=False, error=error_message, question=question)

        if save_screenshot:
            emit_info(
                f"[green]Screenshot saved: {screenshot_result.screenshot_path}[/green]",
                message_group=group_id,
            )

        screenshot_bytes = screenshot_result.screenshot_data
        if not screenshot_bytes:
            emit_error(
                "[red]Screenshot captured but pixel data missing; cannot run visual analysis.[/red]",
                message_group=group_id,
            )
            return VQAResult(
                success=False,
                error="Screenshot captured but no image bytes available for analysis.",
                question=question,
            )

        # Collect display scale info
        try:
            import pyautogui

            logical_w, logical_h = pyautogui.size()
            from .platform import get_screen_scale_factor

            screen_scale = get_screen_scale_factor()
        except Exception:
            logical_w, logical_h, screen_scale = None, None, None

        # Check image size and downscale if needed for VQA API limits
        original_size_mb = len(screenshot_bytes) / 1_000_000
        original_w = screenshot_result.width
        original_h = screenshot_result.height
        vqa_w = original_w
        vqa_h = original_h
        vqa_scale = 1.0
        vqa_format = "PNG"
        if len(screenshot_bytes) > VQA_MAX_IMAGE_SIZE_BYTES:
            target_resolution = max_vqa_resolution or VQA_MAX_RESOLUTION
            emit_warning(
                f"[yellow]Screenshot size ({original_size_mb:.2f} MB) exceeds VQA limit. "
                f"Downscaling to max {target_resolution[0]}x{target_resolution[1]}...[/yellow]",
                message_group=group_id,
            )
            screenshot_bytes, vqa_scale, vqa_format = _resize_image_if_needed(
                screenshot_bytes, max_resolution=target_resolution
            )
            # Update vqa size by reading resized image bytes
            try:
                from PIL import Image

                img = Image.open(BytesIO(screenshot_bytes))
                vqa_w, vqa_h = img.size
            except Exception:
                vqa_w, vqa_h = None, None
            new_size_mb = len(screenshot_bytes) / 1_000_000
            format_change = (
                f" (converted to {vqa_format})" if vqa_format != "PNG" else ""
            )
            emit_info(
                f"[green]Image resized: {original_size_mb:.2f} MB → {new_size_mb:.2f} MB "
                f"(scale factor: {vqa_scale:.2f}){format_change}[/green]",
                message_group=group_id,
            )

        # Sanity: check logical*scale ≈ physical screenshot size
        if logical_w and logical_h and screen_scale and original_w and original_h:
            expected_w = int(logical_w * screen_scale)
            expected_h = int(logical_h * screen_scale)
            if abs(expected_w - original_w) > 5 or abs(expected_h - original_h) > 5:
                emit_warning(
                    f"[yellow]Scale mismatch: logical({logical_w}x{logical_h}) * {screen_scale} ≠ screenshot({original_w}x{original_h}). Auto-correcting scale to {original_w / logical_w:.2f}x[/yellow]",
                    message_group=group_id,
                )
                try:
                    screen_scale = original_w / logical_w
                except Exception:
                    pass

        try:
            # Enhance question with grid context if grid is enabled
            enhanced_question = (
                "POLICY: Do not generate click coordinates. If providing any location, use the grid labels only. "
                "Coordinates for clicking must be derived via OCR/AX with proper scaling.\n\n"
            ) + question
            if use_grid:
                enhanced_question = (
                    f"NOTE: This screenshot has a coordinate grid overlay. "
                    f"Red lines are drawn every {grid_spacing} pixels with coordinate labels. "
                    f"Use these grid references to provide more precise location information.\n\n"
                    + enhanced_question
                )

            # Determine correct media type based on format (PNG or JPEG)
            media_type = f"image/{vqa_format.lower()}"  # 'image/png' or 'image/jpeg'

            vqa_result = await asyncio.to_thread(
                run_desktop_vqa_analysis,
                enhanced_question,
                screenshot_bytes,
                media_type,
            )
        except Exception as exc:
            emit_error(
                f"[red]Visual question answering failed: {exc}[/red]",
                message_group=group_id,
            )
            return VQAResult(
                success=False,
                error=f"Visual analysis failed: {exc}",
                question=question,
                screenshot_info=ScreenshotInfo(
                    path=screenshot_result.screenshot_path,
                    timestamp=screenshot_result.timestamp,
                    width=original_w,
                    height=original_h,
                    logical_width=logical_w,
                    logical_height=logical_h,
                    scale_x=screen_scale,
                    scale_y=screen_scale,
                    original_width=original_w,
                    original_height=original_h,
                    vqa_width=vqa_w,
                    vqa_height=vqa_h,
                    vqa_scale_x=vqa_scale if (original_w and vqa_w) else None,
                    vqa_scale_y=vqa_scale if (original_h and vqa_h) else None,
                    region=list(region) if region else None,
                ),
                window_bounds=window_bounds,
                coordinate_system=coordinate_system,
            )

        emit_info(
            f"[green]Visual analysis answer: {vqa_result.answer}[/green]",
            message_group=group_id,
        )
        emit_info(
            f"[dim]Observations: {vqa_result.observations}[/dim]",
            message_group=group_id,
        )

        # Build full VQA result
        full_result = VQAResult(
            success=True,
            question=question,
            answer=vqa_result.answer,
            confidence=vqa_result.confidence,
            observations=vqa_result.observations,
            screenshot_path=screenshot_result.screenshot_path,
            screenshot_info=ScreenshotInfo(
                path=screenshot_result.screenshot_path,
                size=len(screenshot_bytes),
                timestamp=screenshot_result.timestamp,
                width=original_w,
                height=original_h,
                logical_width=logical_w,
                logical_height=logical_h,
                scale_x=screen_scale,
                scale_y=screen_scale,
                original_width=original_w,
                original_height=original_h,
                vqa_width=vqa_w,
                vqa_height=vqa_h,
                vqa_scale_x=vqa_scale if (original_w and vqa_w) else None,
                vqa_scale_y=vqa_scale if (original_h and vqa_h) else None,
                region=list(region) if region else None,
            ),
            window_bounds=window_bounds,
            coordinate_system=coordinate_system,
        )

        # Success-conditional compaction: Return compact result
        compact_result = _compact_vqa_result(
            full_result, truncate_answer=truncate_answer
        )
        truncate_msg = "answer truncated" if truncate_answer else "full answer"
        emit_info(
            f"[dim]💾 Compacted VQA result: screenshot metadata stripped, {truncate_msg}[/dim]",
            message_group=group_id,
        )
        return compact_result

    except Exception as e:
        emit_error(
            f"[red]Screenshot analysis failed: {str(e)}[/red]", message_group=group_id
        )
        return VQAResult(success=False, error=str(e), question=question)


def register_desktop_screenshot_tools(agent):
    """Register desktop screenshot and analysis tools."""

    @agent.tool
    def desktop_convert_screenshot_to_screen_coords(
        context: RunContext,
        screenshot_x: int,
        screenshot_y: int,
    ) -> dict[str, int | float]:
        """
        Convert screenshot (physical pixel) coordinates to screen (logical) coordinates.

        **CRITICAL for HiDPI/Retina displays!** On 2x displays, screenshots are 2x larger
        than the screen coordinates that mouse operations use.

        Use this when:
        - You used OCR to find text in a screenshot
        - You used VQA to locate an element in a screenshot
        - You need to click at a position found in a screenshot

        Args:
            screenshot_x: X coordinate from screenshot analysis (physical pixels)
            screenshot_y: Y coordinate from screenshot analysis (physical pixels)

        Returns:
            Dictionary with screen_x, screen_y (logical coordinates for mouse),
            and the scale_factor used

        Example:
            >>> # On 2x Retina display
            >>> # OCR found "Submit" at (940, 250) in screenshot
            >>> coords = desktop_convert_screenshot_to_screen_coords(940, 250)
            >>> # coords = {"screen_x": 470, "screen_y": 125, "scale_factor": 2.0}
            >>> # Now click at the converted coordinates:
            >>> desktop_mouse_click(x=coords["screen_x"], y=coords["screen_y"])
        """
        from .platform import (
            convert_screenshot_to_screen_coords,
            get_screen_scale_factor,
        )

        scale_factor = get_screen_scale_factor()
        screen_x, screen_y = convert_screenshot_to_screen_coords(
            screenshot_x, screenshot_y, scale_factor
        )

        return {
            "screenshot_x": screenshot_x,
            "screenshot_y": screenshot_y,
            "screen_x": screen_x,
            "screen_y": screen_y,
            "scale_factor": scale_factor,
            "note": (
                f"Converted from screenshot space to screen space using scale factor {scale_factor}x. "
                "Use screen_x/screen_y for mouse operations."
            ),
        }

    @agent.tool
    def desktop_get_screen_size(context: RunContext) -> dict[str, int | float | str]:
        """
        Get the current screen resolution (logical points) and scale metadata.

        Returns:
            Dict with width, height (logical), scale_x/y, physical_width/height, and coordinate_space

        Example:
            - desktop_get_screen_size() -> {"width": 1728, "height": 1117, "scale_x": 2.0, "physical_width": 3456, ...}
        """
        if not PYAUTOGUI_AVAILABLE:
            return {"error": ERROR_PYAUTOGUI_MISSING}

        width, height = pyautogui.size()
        try:
            from .platform import get_screen_scale_factor

            scale = get_screen_scale_factor()
        except Exception:
            scale = 1.0
        physical_width = int(width * scale)
        physical_height = int(height * scale)
        return {
            "width": width,
            "height": height,
            "logical_width": width,
            "logical_height": height,
            "scale_x": scale,
            "scale_y": scale,
            "physical_width": physical_width,
            "physical_height": physical_height,
            "coordinate_space": "logical_points",
        }

    @agent.tool
    def desktop_get_screen_scale(context: RunContext) -> dict[str, int | float | str]:
        """
        Get screen DPI scale and coordinate space metadata (computed via screenshot).

        Returns:
            Dict with scale_x/y, logical (OS) size, physical (screenshot) size, and notes.
        """
        if not PYAUTOGUI_AVAILABLE:
            return {"error": ERROR_PYAUTOGUI_MISSING}
        logical_w, logical_h = pyautogui.size()
        shot = pyautogui.screenshot()
        physical_w, physical_h = shot.size
        scale = round((physical_w / logical_w) * 4) / 4 if logical_w else 1.0
        return {
            "logical_width": logical_w,
            "logical_height": logical_h,
            "physical_width": physical_w,
            "physical_height": physical_h,
            "scale_x": scale,
            "scale_y": scale,
            "coordinate_space": "logical_points",
            "note": "Mouse APIs expect logical points; screenshots are physical pixels. Convert using scale computed from screenshot.",
        }

    @agent.tool
    async def desktop_vqa_window(
        context: RunContext,
        question: str,
        window_title: str | None = None,
        use_grid: bool = False,
    ) -> VQAResult:
        """
        Convenience wrapper for VQA on active window.

        This is the recommended way to use VQA for desktop automation workflows.
        Always captures window-only (never full screen).

        Args:
            question: Question to ask about the window
            window_title: Optional app/window to focus first
            use_grid: Add coordinate grid overlay

        Returns:
            VQAResult with window-relative coordinates

        Examples:
            # Find element in current window
            - desktop_vqa_window(question="Where is the Submit button?")

            # Find element in specific app
            - desktop_vqa_window(
                question="Locate the address bar",
                window_title="TextEdit"
              )
        """
        # Use new unified screenshot_analyze()
        result = await screenshot_analyze(
            question=question,
            window_title=window_title,
            mode="active_window",
            add_grid=use_grid,
        )

        # Convert dict result to VQAResult for backwards compatibility
        from .result_types import VQAResult

        return VQAResult(
            success=result.get("success", False),
            question=result.get("question"),
            answer=result.get("answer", ""),
            confidence=result.get("confidence", 0.0),
            observations=result.get("observations"),
            screenshot_path=result.get("screenshot_path"),
        )

    @agent.tool
    def desktop_window_to_screen_coords(
        context: RunContext,
        window_x: int,
        window_y: int,
        window_title: str | None = None,
    ) -> dict[str, int | str]:
        """
        Convert window-relative coordinates to screen-absolute coordinates.

        Use this when you have coordinates from VQA (which are window-relative by default)
        and need to convert them to screen coordinates for mouse operations.

        Args:
            window_x: X coordinate relative to window top-left
            window_y: Y coordinate relative to window top-left
            window_title: Optional window to get bounds for (default: active window)

        Returns:
            Dict with screen_x, screen_y, and metadata

        Examples:
            # VQA found button at (200, 150) in window
            - coords = desktop_window_to_screen_coords(window_x=200, window_y=150)
            - desktop_mouse_click(x=coords["screen_x"], y=coords["screen_y"])
        """
        from .coordinates import window_to_screen_coords
        from .window_control import _get_active_window_bounds_impl, _focus_window_impl

        # Get window bounds
        if window_title:
            _focus_window_impl(window_title)

        bounds = _get_active_window_bounds_impl()
        if not bounds.success:
            return {
                "error": f"Could not get window bounds: {bounds.error or 'Unknown error'}"
            }

        try:
            screen_x, screen_y = window_to_screen_coords(window_x, window_y, bounds)
            return {
                "screen_x": screen_x,
                "screen_y": screen_y,
                "window_x": window_x,
                "window_y": window_y,
                "window_title": bounds.window_title or bounds.app_name,
                "window_bounds": {
                    "x": bounds.x,
                    "y": bounds.y,
                    "width": bounds.width,
                    "height": bounds.height,
                },
            }
        except ValueError as e:
            return {"error": str(e)}

    @agent.tool
    def desktop_screen_to_window_coords(
        context: RunContext,
        screen_x: int,
        screen_y: int,
        window_title: str | None = None,
    ) -> dict[str, int | str]:
        """
        Convert screen-absolute coordinates to window-relative coordinates.

        Use this when you have screen coordinates and need to convert them to
        window-relative coordinates.

        Args:
            screen_x: X coordinate in screen space
            screen_y: Y coordinate in screen space
            window_title: Optional window to get bounds for (default: active window)

        Returns:
            Dict with window_x, window_y, and metadata

        Examples:
            # Convert screen click to window coords
            - coords = desktop_screen_to_window_coords(screen_x=1000, screen_y=500)
            - print(f"Window position: ({coords['window_x']}, {coords['window_y']})")
        """
        from .coordinates import screen_to_window_coords
        from .window_control import _get_active_window_bounds_impl, _focus_window_impl

        # Get window bounds
        if window_title:
            _focus_window_impl(window_title)

        bounds = _get_active_window_bounds_impl()
        if not bounds.success:
            return {
                "error": f"Could not get window bounds: {bounds.error or 'Unknown error'}"
            }

        try:
            window_x, window_y = screen_to_window_coords(screen_x, screen_y, bounds)
            return {
                "window_x": window_x,
                "window_y": window_y,
                "screen_x": screen_x,
                "screen_y": screen_y,
                "window_title": bounds.window_title or bounds.app_name,
                "window_bounds": {
                    "x": bounds.x,
                    "y": bounds.y,
                    "width": bounds.width,
                    "height": bounds.height,
                },
            }
        except ValueError as e:
            return {"error": str(e)}
