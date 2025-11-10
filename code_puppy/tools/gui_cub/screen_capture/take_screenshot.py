"""Desktop screenshot and analysis tool."""

from __future__ import annotations

import asyncio
from io import BytesIO

from code_puppy.messaging import emit_error, emit_info, emit_warning
from code_puppy.tools.common import generate_group_id

from ..constants import DEFAULT_GRID_SPACING
from ..result_types import ScreenshotInfo, VQAResult
from ..vqa_desktop import run_desktop_vqa_analysis
from .capture import capture_screen
from .image_utils import (
    VQA_MAX_IMAGE_SIZE_BYTES,
    VQA_MAX_RESOLUTION,
    resize_image_if_needed,
)
from .screenshot_analyze import _compact_vqa_result


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
    include_image: bool = False,  # NEW: Delegation pattern - exclude image by default
) -> VQAResult:
    """
    Take a desktop screenshot and analyze it using visual understanding.

    **DEFAULT: Captures active window only (not full screen).**
    This reduces image size, improves accuracy, and avoids VQA size limits.

    **DELEGATION PATTERN:**
    The screenshot is analyzed in a SEPARATE vision model context (isolated agent).
    By default, only the text analysis is returned - NOT the full image. This achieves
    99%+ token savings while maintaining full-quality image analysis.

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
        include_image: Include base64 image in result (default: False for 99%+ token savings)

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
            from ..window_control import _focus_window_impl

            focus_result = _focus_window_impl(window_title)
            if not focus_result.success:
                emit_warning(
                    f"[yellow]Could not focus window '{window_title}', using current active window[/yellow]"
                )
            # Let window focus settle
            await asyncio.sleep(0.3)

        # Get active window bounds
        from ..window_control import _get_active_window_bounds_impl

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
            from ..platform import get_screen_scale_factor

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
            screenshot_bytes, vqa_scale, vqa_format = resize_image_if_needed(
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

        # Add base64 image if requested (delegation pattern - excluded by default)
        if include_image and screenshot_result.screenshot_path:
            import base64
            with open(screenshot_result.screenshot_path, "rb") as f:
                image_data = f.read()
                full_result.image_base64 = base64.b64encode(image_data).decode("utf-8")
                size_mb = len(image_data) / 1_000_000
                emit_warning(
                    f"[yellow]⚠️  Image included in result (~{size_mb:.2f} MB base64)[/yellow]\n"
                    f"[dim]   Token cost: ~{int(size_mb * 100_000)} tokens[/dim]\n"
                    f"[dim]   Consider using include_image=False for 99%+ token savings[/dim]",
                    message_group=group_id,
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
