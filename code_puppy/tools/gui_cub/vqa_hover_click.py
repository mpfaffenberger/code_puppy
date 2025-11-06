"""
VQA Hover & Click - Simplified Visual Element Location

Combines VQA element detection with hover verification in ONE tool.
No complex recursion - just find, hover, verify, return.
"""

from dataclasses import dataclass
from typing import Optional
from pydantic_ai import RunContext

from code_puppy.messaging import emit_info, emit_warning
from .screen_capture import capture_screen
from .vqa_desktop import run_desktop_vqa_analysis
from .window_control import _get_active_window_bounds_impl


@dataclass
class VQAHoverResult:
    """Result from VQA hover & verify operation."""

    success: bool
    mouse_x: Optional[int] = None
    mouse_y: Optional[int] = None
    confidence: float = 0.0
    description: str = ""
    verification_screenshot: Optional[str] = None
    error: Optional[str] = None


def _vqa_hover_and_click_impl(
    element_description: str,
    window_title: Optional[str] = None,
    click_after_verify: bool = False,
    verify_zoom_size: int = 300,
    group_id: Optional[str] = None,
) -> VQAHoverResult:
    """
    Find element with VQA, hover to verify, optionally click.

    Process:
    1. Capture window screenshot
    2. VQA finds element → rough coordinates
    3. Hover to those coordinates → get ACTUAL mouse position
    4. Capture small region around mouse (with cursor visible)
    5. VQA verifies: "Is [element] under cursor?"
    6. Return actual mouse position

    Args:
        element_description: What to find (e.g. "yellow minimize button")
        window_title: Optional window to focus first
        click_after_verify: If True, clicks after successful verification
        verify_zoom_size: Size of verification screenshot (default 300px)
        group_id: Message group ID for logging

    Returns:
        VQAHoverResult with mouse position and verification status
    """
    try:
        # Import here to avoid circular dependency
        import pyautogui
    except ImportError:
        return VQAHoverResult(
            success=False, error="pyautogui not available - cannot control mouse"
        )

    import time
    from .platform import IS_MACOS

    emit_info(
        f"[bold cyan]🎯 VQA HOVER & VERIFY[/bold cyan]\n"
        f"[dim]   Looking for: {element_description}[/dim]\n"
        f"[dim]   Window: {window_title or 'Current frontmost'}[/dim]",
        message_group=group_id,
    )

    # Step 1: Focus window and get bounds
    if window_title:
        emit_info(
            f"[cyan]🎯 Focusing window: {window_title}[/cyan]", message_group=group_id
        )
        from .window_control import _focus_window_impl

        try:
            _focus_window_impl(window_title)
            time.sleep(0.5)
        except Exception as e:
            emit_warning(
                f"[yellow]⚠️  Could not focus window: {e}[/yellow]",
                message_group=group_id,
            )

    # Get window bounds
    bounds_result = _get_active_window_bounds_impl()
    if not bounds_result.success:
        return VQAHoverResult(
            success=False, error=f"Could not get window bounds: {bounds_result.error}"
        )

    emit_info(
        f"[green]✓ Window bounds:[/green]\n"
        f"[dim]   App: {bounds_result.app_name}[/dim]\n"
        f"[dim]   Position: ({bounds_result.x}, {bounds_result.y})[/dim]\n"
        f"[dim]   Size: {bounds_result.width}x{bounds_result.height}[/dim]",
        message_group=group_id,
    )

    # Calculate screenshot region (include title bar on macOS)
    region_x = bounds_result.x
    region_y = bounds_result.y
    region_w = bounds_result.width
    region_h = bounds_result.height

    if IS_MACOS:
        # macOS window bounds exclude title bar - expand upward
        title_bar_height = 40
        region_y -= title_bar_height
        region_h += title_bar_height
        emit_info(
            f"[dim]🍎 Added {title_bar_height}px for macOS title bar[/dim]",
            message_group=group_id,
        )

    # Step 2: Capture window screenshot
    emit_info("[cyan]📸 Capturing window screenshot...[/cyan]", message_group=group_id)
    screenshot_result = capture_screen(region=(region_x, region_y, region_w, region_h))

    if not screenshot_result.success:
        return VQAHoverResult(
            success=False, error=f"Screenshot failed: {screenshot_result.error}"
        )

    emit_info(
        f"[green]✓ Screenshot captured: {region_w}x{region_h}[/green]\n"
        f"[dim]   File: {screenshot_result.screenshot_path}[/dim]",
        message_group=group_id,
    )

    # Step 3: VQA analysis - find the element
    emit_info("[cyan]🤖 Analyzing with VQA...[/cyan]", message_group=group_id)

    vqa_question = (
        f"Target window: {bounds_result.app_name}. "
        f"Look for the {element_description}. "
        f"If you find it, provide the coordinates as (X, Y) where X and Y are pixel coordinates within this image. "
        f"Image size: {region_w}x{region_h}. "
        f"Respond with ONLY the coordinates like '(123, 456)' if found, or 'Not found' if not visible."
    )

    vqa_result = run_desktop_vqa_analysis(
        question=vqa_question,
        image_bytes=screenshot_result.screenshot_data,
        media_type="image/png",
    )

    if not vqa_result.found:
        emit_warning(
            f"[yellow]❌ VQA could not find element[/yellow]\n"
            f"[dim]   Response: {vqa_result.answer}[/dim]",
            message_group=group_id,
        )
        return VQAHoverResult(
            success=False,
            confidence=vqa_result.confidence,
            description=vqa_result.answer,
            error="Element not found by VQA",
        )

    # Parse coordinates from VQA response
    import re

    coord_pattern = r"\(?\s*(\d+)\s*,\s*(\d+)\s*\)?"
    match = re.search(coord_pattern, vqa_result.answer)

    if not match:
        emit_warning(
            f"[yellow]⚠️  Could not parse coordinates from VQA response[/yellow]\n"
            f"[dim]   Response: {vqa_result.answer}[/dim]",
            message_group=group_id,
        )
        return VQAHoverResult(
            success=False,
            confidence=vqa_result.confidence,
            description=vqa_result.answer,
            error="Could not parse coordinates from VQA",
        )

    local_x = int(match.group(1))
    local_y = int(match.group(2))

    # Convert to screen coordinates
    screen_x = region_x + local_x
    screen_y = region_y + local_y

    emit_info(
        f"[green]✓ VQA found element[/green]\n"
        f"[dim]   Local coords: ({local_x}, {local_y})[/dim]\n"
        f"[dim]   Screen coords: ({screen_x}, {screen_y})[/dim]\n"
        f"[dim]   Confidence: {vqa_result.confidence:.0%}[/dim]",
        message_group=group_id,
    )

    # Step 4: Hover to location
    emit_info(
        f"[cyan]🖱️  Hovering to ({screen_x}, {screen_y})...[/cyan]",
        message_group=group_id,
    )

    pyautogui.moveTo(screen_x, screen_y, duration=0.3)
    time.sleep(0.15)  # Wait for cursor to fully settle

    # Get ACTUAL mouse position (may differ due to accessibility offsets)
    actual_x, actual_y = pyautogui.position()
    offset_x = actual_x - screen_x
    offset_y = actual_y - screen_y

    emit_info(
        f"[green]✓ Hover complete[/green]\n"
        f"[dim]   Target: ({screen_x}, {screen_y})[/dim]\n"
        f"[dim]   Actual: ({actual_x}, {actual_y})[/dim]\n"
        f"[dim]   Offset: ({offset_x:+d}, {offset_y:+d}) pixels[/dim]",
        message_group=group_id,
    )

    # Step 5: Capture verification screenshot centered on ACTUAL mouse position
    emit_info(
        f"[cyan]📸 Capturing verification screenshot ({verify_zoom_size}x{verify_zoom_size} around cursor)...[/cyan]",
        message_group=group_id,
    )

    verify_x = actual_x - verify_zoom_size // 2
    verify_y = actual_y - verify_zoom_size // 2

    verify_screenshot = capture_screen(
        region=(verify_x, verify_y, verify_zoom_size, verify_zoom_size),
        show_cursor=True,  # CRITICAL: Show cursor in verification screenshot!
    )

    if not verify_screenshot.success:
        emit_warning(
            f"[yellow]⚠️  Verification screenshot failed: {verify_screenshot.error}[/yellow]",
            message_group=group_id,
        )
        # Still return success - we have the hover position
        return VQAHoverResult(
            success=True,
            mouse_x=actual_x,
            mouse_y=actual_y,
            confidence=vqa_result.confidence,
            description=vqa_result.answer,
            verification_screenshot=None,
        )

    emit_info(
        f"[green]✓ Verification screenshot saved[/green]\n"
        f"[dim]   File: {verify_screenshot.screenshot_path}[/dim]",
        message_group=group_id,
    )

    # Step 6: Quick VQA verification - is element under cursor?
    emit_info(
        "[cyan]🔍 Verifying element is under cursor...[/cyan]", message_group=group_id
    )

    verify_question = (
        f"This screenshot shows a cursor (pointer/arrow). "
        f"Is the {element_description} directly under or very close to the cursor tip? "
        f"Respond with 'Yes' if the cursor is on or very near the target element, "
        f"or 'No' if the cursor is not on the element."
    )

    verify_vqa = run_desktop_vqa_analysis(
        question=verify_question,
        image_bytes=verify_screenshot.screenshot_data,
        media_type="image/png",
    )

    is_verified = verify_vqa.answer and "yes" in verify_vqa.answer.lower()

    if is_verified:
        emit_info(
            f"[bold green]✅ VERIFICATION PASSED - Cursor is on target element[/bold green]\n"
            f"[dim]   VQA says: {verify_vqa.answer}[/dim]",
            message_group=group_id,
        )
    else:
        emit_warning(
            f"[yellow]⚠️  VERIFICATION UNCERTAIN[/yellow]\n"
            f"[dim]   VQA says: {verify_vqa.answer}[/dim]\n"
            f"[dim]   Cursor may not be exactly on target - check screenshot[/dim]",
            message_group=group_id,
        )

    # Step 7: Optional click
    if click_after_verify and is_verified:
        emit_info(
            f"[cyan]🖱️  Clicking at ({actual_x}, {actual_y})...[/cyan]",
            message_group=group_id,
        )
        pyautogui.click(actual_x, actual_y)
        emit_info("[green]✓ Click executed[/green]", message_group=group_id)

    return VQAHoverResult(
        success=True,
        mouse_x=actual_x,
        mouse_y=actual_y,
        confidence=vqa_result.confidence
        * (verify_vqa.confidence if is_verified else 0.5),
        description=f"Initial: {vqa_result.answer} | Verify: {verify_vqa.answer}",
        verification_screenshot=verify_screenshot.screenshot_path,
    )


def _check_vqa_capability() -> tuple[bool, str]:
    """Check if VQA is available (requires OCR/Tesseract).

    Returns:
        Tuple of (is_available, error_message)
    """
    from code_puppy.tools.gui_cub.config_manager import load_config

    config = load_config()
    if not config:
        return False, "Platform not calibrated. Run gui_cub_calibrate() first."

    # VQA doesn't strictly require Tesseract, but check anyway for consistency
    capabilities = config.get("capabilities", {})

    # Note: VQA uses vision models, not Tesseract, so we don't block it
    # But we can warn if pyautogui is missing
    if not capabilities.get("pyautogui", False):
        return False, "⚠️ PyAutoGUI not available. VQA/screenshot features won't work."

    return True, ""


def register_vqa_hover_tools(agent):
    """Register VQA hover & click tool with an agent."""

    @agent.tool
    def desktop_find_and_hover(
        context: RunContext,
        element_description: str,
        window_title: str | None = None,
        verify_zoom_size: int = 300,
    ) -> dict:
        """
        Find a visual element with VQA and hover to it with verification.

        Simplified one-shot approach:
        1. Captures window screenshot
        2. VQA finds element roughly
        3. Hovers to that location
        4. Captures verification screenshot centered on cursor
        5. VQA verifies cursor is on target
        6. Returns actual mouse position

        This is MUCH simpler than recursive zooming - just find, hover, verify, done!

        Args:
            element_description: What to find (e.g. "yellow minimize button in window controls")
            window_title: Optional window name to focus first (e.g. "Spotify")
            verify_zoom_size: Size of verification screenshot around cursor (default 300px)

        Returns:
            Dictionary with:
            - success: True if found and hovered
            - mouse_x, mouse_y: Actual cursor position
            - confidence: Combined VQA confidence
            - verification_screenshot: Path to screenshot showing cursor on element

        Example:
            # Find and hover to minimize button
            result = desktop_find_and_hover(
                element_description="yellow minimize button",
                window_title="Spotify"
            )

            # Click if hover was successful
            if result["success"]:
                desktop_mouse_click(x=result["mouse_x"], y=result["mouse_y"])

        Why this is better than recursive VQA:
        - ONE screenshot instead of 3-5
        - ONE hover instead of moving mouse multiple times
        - Visual verification screenshot with cursor visible
        - Simpler logic, fewer points of failure
        - Faster (single pass)
        """
        # Check capabilities
        is_available, error_msg = _check_vqa_capability()
        if not is_available:
            return {
                "success": False,
                "error": error_msg,
            }

        result = _vqa_hover_and_click_impl(
            element_description=element_description,
            window_title=window_title,
            click_after_verify=False,
            verify_zoom_size=verify_zoom_size,
            group_id=context.deps.message_group_id
            if hasattr(context.deps, "message_group_id")
            else None,
        )

        return {
            "success": result.success,
            "mouse_x": result.mouse_x,
            "mouse_y": result.mouse_y,
            "confidence": result.confidence,
            "description": result.description,
            "verification_screenshot": result.verification_screenshot,
            "error": result.error,
        }

    @agent.tool
    def desktop_find_and_click(
        context: RunContext,
        element_description: str,
        window_title: str | None = None,
        verify_zoom_size: int = 300,
    ) -> dict:
        """
        Find a visual element with VQA, hover to verify, then click.

        Same as desktop_find_and_hover but automatically clicks after verification.

        Args:
            element_description: What to find (e.g. "Submit button")
            window_title: Optional window name to focus first
            verify_zoom_size: Size of verification screenshot (default 300px)

        Returns:
            Dictionary with success status and mouse position

        Example:
            # Find and click minimize button in one call
            result = desktop_find_and_click(
                element_description="yellow minimize button",
                window_title="Spotify"
            )
        """
        # Check capabilities
        is_available, error_msg = _check_vqa_capability()
        if not is_available:
            return {
                "success": False,
                "error": error_msg,
            }

        result = _vqa_hover_and_click_impl(
            element_description=element_description,
            window_title=window_title,
            click_after_verify=True,
            verify_zoom_size=verify_zoom_size,
            group_id=context.deps.message_group_id
            if hasattr(context.deps, "message_group_id")
            else None,
        )

        return {
            "success": result.success,
            "mouse_x": result.mouse_x,
            "mouse_y": result.mouse_y,
            "confidence": result.confidence,
            "description": result.description,
            "verification_screenshot": result.verification_screenshot,
            "error": result.error,
        }
