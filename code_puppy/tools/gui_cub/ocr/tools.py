"""OCR tool registration for agents."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic_ai import RunContext

if TYPE_CHECKING:
    from pydantic_ai import Agent

from ..dependencies import PIL_AVAILABLE, PYAUTOGUI_AVAILABLE

if PYAUTOGUI_AVAILABLE:
    import pyautogui
else:
    pyautogui = None

if PIL_AVAILABLE:
    from PIL import Image, ImageDraw
else:
    Image = None
    ImageDraw = None

# Import thread-safe screenshot function
from ..screen_capture.capture import _safe_screenshot

from code_puppy.messaging import emit_error, emit_warning
from ..rich_emit import emit_rich
from code_puppy.tools.common import generate_group_id

from ..constants import ERROR_PILLOW_MISSING, ERROR_PYAUTOGUI_MISSING
from .extraction import (
    _compact_ocr_extract_result,
    _compact_ocr_find_result,
    extract_text_from_image,
)
from ..result_types import BaseAutomationResult
from .result_types import (
    OCRDebugVisualization,
    OCRExtractResult,
    OCRFindResult,
    OCRVerifyResult,
)
from .search import _check_ocr_capability, find_text_in_elements


# ============================================================================
# MODULE-LEVEL FUNCTIONS (importable for use by other modules)
# ============================================================================


def desktop_find_text(
    context: "RunContext | None" = None,
    search_text: str = "",
    case_sensitive: bool = False,
    fuzzy: bool = False,
    fuzzy_threshold: float = 0.75,
    x: int | None = None,
    y: int | None = None,
    width: int | None = None,
    height: int | None = None,
    use_active_window: bool = True,
    use_full_screen: bool = False,
    language: str = "eng",
    min_confidence: float | None = None,
) -> OCRFindResult:
    """
    Find text on screen using OCR and return its coordinates.

    This is the module-level function that can be imported directly.
    Searches ONLY the active window by default for better performance.

    Args:
        context: Optional RunContext (not used, kept for API compatibility)
        search_text: Text to search for (case-insensitive by default)
        case_sensitive: Whether to match case exactly (default: False)
        fuzzy: Enable fuzzy matching (default: False)
        fuzzy_threshold: Minimum similarity for fuzzy matching (default: 0.75)
        x: Optional left coordinate of region to search within
        y: Optional top coordinate of region to search within
        width: Optional width of region to search within
        height: Optional height of region to search within
        use_active_window: Search only the active window (default: True)
        use_full_screen: Search the entire screen (default: False)
        language: Language code for OCR (default: "eng")
        min_confidence: Optional minimum confidence filter (0.0-1.0)

    Returns:
        OCRFindResult with matches sorted by confidence
    """
    if not search_text:
        return OCRFindResult(
            success=False,
            error="search_text is required",
            search_text=search_text,
        )

    # Check capabilities
    is_available, error_msg = _check_ocr_capability()
    if not is_available:
        return OCRFindResult(
            success=False,
            error=error_msg,
            search_text=search_text,
        )

    if not PYAUTOGUI_AVAILABLE:
        return OCRFindResult(
            success=False,
            error=ERROR_PYAUTOGUI_MISSING,
            search_text=search_text,
        )

    group_id = generate_group_id("ocr_find", search_text[:30])

    # Determine region to capture
    region = None

    if x is not None and y is not None and width is not None and height is not None:
        region = (x, y, width, height)
    elif use_full_screen:
        region = None
    elif use_active_window:
        from ..window_control import _get_active_window_bounds_impl

        bounds_result = _get_active_window_bounds_impl()
        if bounds_result.success and bounds_result.x is not None:
            region = (
                bounds_result.x,
                bounds_result.y,
                bounds_result.width,
                bounds_result.height,
            )

    try:
        # Detect HiDPI scaling
        from ..platform import get_screen_scale_factor

        scale_factor = get_screen_scale_factor()

        # Convert to physical pixels if needed
        if region and scale_factor != 1.0:
            region = (
                int(region[0] * scale_factor),
                int(region[1] * scale_factor),
                int(region[2] * scale_factor),
                int(region[3] * scale_factor),
            )

        # Take screenshot
        screenshot = _safe_screenshot(region=region)
        if screenshot is None:
            return OCRFindResult(
                success=False,
                error="Failed to capture screenshot",
                search_text=search_text,
            )

        # Extract text from screenshot
        extract_result = extract_text_from_image(
            screenshot,
            language=language,
            scale_factor=scale_factor,
        )

        if not extract_result.success:
            return OCRFindResult(
                success=False,
                error=extract_result.error or "OCR extraction failed",
                search_text=search_text,
            )

        text_elements = extract_result.text_elements or []

        # Apply region offset to coordinates
        if region and text_elements:
            offset_x = region[0] / scale_factor if scale_factor != 1.0 else region[0]
            offset_y = region[1] / scale_factor if scale_factor != 1.0 else region[1]
            for elem in text_elements:
                elem.x = int(elem.x + offset_x)
                elem.center_x = int(elem.center_x + offset_x)
                elem.y = int(elem.y + offset_y)
                elem.center_y = int(elem.center_y + offset_y)

        # Search for text
        find_result = find_text_in_elements(
            search_text=search_text,
            text_elements=text_elements,
            case_sensitive=case_sensitive,
            fuzzy=fuzzy,
            fuzzy_threshold=fuzzy_threshold,
        )

        # Apply confidence filter if specified
        if min_confidence is not None and find_result.found:
            if find_result.matches:
                high_conf = [
                    m for m in find_result.matches if m.confidence >= min_confidence
                ]
                if not high_conf:
                    return OCRFindResult(
                        success=True,
                        search_text=search_text,
                        found=False,
                        total_matches=0,
                        best_match=None,
                        matches=[],
                    )
                best = max(high_conf, key=lambda m: m.confidence)
                find_result = OCRFindResult(
                    success=True,
                    search_text=search_text,
                    found=True,
                    total_matches=len(high_conf),
                    best_match=best,
                    matches=high_conf,
                )
            elif find_result.best_match:
                if find_result.best_match.confidence < min_confidence:
                    return OCRFindResult(
                        success=True,
                        search_text=search_text,
                        found=False,
                        total_matches=0,
                        best_match=None,
                        matches=[],
                    )

        if find_result.found:
            emit_rich(
                f"[green]Found {find_result.total_matches} match(es) for '{search_text}'[/green]",
                message_group=group_id,
            )
            return _compact_ocr_find_result(find_result)
        else:
            emit_warning(
                f"[yellow]No matches found for '{search_text}'[/yellow]",
                message_group=group_id,
            )
            return find_result

    except Exception as e:
        return OCRFindResult(
            success=False,
            error=f"OCR failed: {str(e)}",
            search_text=search_text,
        )


def desktop_find_text_reliable(
    context: "RunContext | None" = None,
    search_text: str = "",
    min_confidence: float = 0.7,
    case_sensitive: bool = False,
    x: int | None = None,
    y: int | None = None,
    width: int | None = None,
    height: int | None = None,
    use_active_window: bool = True,
    use_full_screen: bool = False,
    language: str = "eng",
) -> OCRFindResult:
    """
    Find text on screen with OCR confidence filtering for reliable results.

    This is the module-level function that can be imported directly.
    Wrapper around desktop_find_text() that ONLY returns matches with
    OCR confidence >= min_confidence.

    Args:
        context: Optional RunContext (not used, kept for API compatibility)
        search_text: Text to search for
        min_confidence: Minimum OCR confidence required (0.0-1.0, default: 0.7)
        case_sensitive: Whether to match case exactly (default: False)
        x: Optional left coordinate of search region
        y: Optional top coordinate of search region
        width: Optional width of search region
        height: Optional height of search region
        use_active_window: Search only active window (default: True)
        use_full_screen: Search entire screen (default: False)
        language: Language code for OCR (default: "eng")

    Returns:
        OCRFindResult with only high-confidence matches
    """
    return desktop_find_text(
        context=context,
        search_text=search_text,
        case_sensitive=case_sensitive,
        x=x,
        y=y,
        width=width,
        height=height,
        use_active_window=use_active_window,
        use_full_screen=use_full_screen,
        language=language,
        min_confidence=min_confidence,
    )


def register_ocr_tools(agent: "Agent[Any, Any]") -> None:
    """Register OCR (Optical Character Recognition) tools.

    This file contains 6 OCR tools (925 lines total):
    1. desktop_extract_text - Extract all text from screen region (~199 lines)
    2. desktop_find_text_on_screen - Find specific text and return coordinates (~113 lines)
    3. desktop_verify_text_visible - Verify text is visible on screen (~112 lines)
    4. desktop_click_text - Click on text found via OCR (~264 lines)
    5. desktop_smart_scroll_to_text - Scroll until text is visible (~167 lines)
    6. desktop_highlight_text - Highlight text on screen for debugging (~28 lines)

    Note: File is long but cohesive - all tools are OCR-based text operations.
    """

    # ============================================================================
    # TOOL 1: EXTRACT TEXT (~199 lines)
    # Extract all text from a screen region using native OCR
    # ============================================================================

    # Global counter to track tool invocations
    _extract_text_call_count = {"count": 0}

    @agent.tool
    def desktop_extract_text(
        context: RunContext,
        x: int | None = None,
        y: int | None = None,
        width: int | None = None,
        height: int | None = None,
        use_active_window: bool = True,
        use_full_screen: bool = False,
        language: str = "eng",
        _internal: bool = False,  # Internal use - skip compaction
    ) -> OCRExtractResult:
        """
        Extract text from a screenshot using OCR (Optical Character Recognition).

        By default, this captures ONLY the active window to improve performance and accuracy.
        Use use_full_screen=True to capture the entire screen instead.

        Args:
            x: Optional left coordinate of region to extract text from
            y: Optional top coordinate of region to extract text from
            width: Optional width of region to extract text from
            height: Optional height of region to extract text from
            use_active_window: Capture only the active window (default: True)
            use_full_screen: Capture the entire screen instead of active window (default: False)
            language: Language code for OCR (default: "eng" for English)
                      Supports: "eng", "spa", "fra", "deu", "chi_sim", etc.

        Returns:
            OCRExtractResult with full text, individual text elements with bounding boxes,
            and confidence scores

        Examples:
            - desktop_extract_text() - Extract text from active window (RECOMMENDED)
            - desktop_extract_text(use_full_screen=True) - Extract from entire screen
            - desktop_extract_text(x=100, y=100, width=500, height=300) - Extract from specific region
            - desktop_extract_text(language="spa") - Extract Spanish text from active window
        """
        # Check capabilities from config
        is_available, error_msg = _check_ocr_capability()
        if not is_available:
            return OCRExtractResult(
                success=False,
                error=error_msg,
            )

        if not PYAUTOGUI_AVAILABLE:
            return OCRExtractResult(
                success=False,
                error=f"{ERROR_PYAUTOGUI_MISSING} and {ERROR_PILLOW_MISSING}",
            )

        # Native OCR (WinRT on Windows, Vision on macOS) is used

        # Increment call counter FIRST
        _extract_text_call_count["count"] += 1
        call_num = _extract_text_call_count["count"]

        # Create group_id early (before we use it in logging)
        # We'll update the description later if needed
        group_id = generate_group_id(
            "ocr_extract",
            f"call_{call_num}",
        )

        # Determine region to capture
        region = None
        region_description = "full screen"

        # Priority: explicit coordinates > full_screen flag > active window (default)
        if x is not None and y is not None and width is not None and height is not None:
            # Explicit region provided
            region = (x, y, width, height)
            region_description = f"custom region {region}"
        elif use_full_screen:
            # Full screen explicitly requested
            region = None
            region_description = "full screen"
        elif use_active_window:
            # Use active window (default behavior)
            # BUGFIX: Use the centralized window bounds helper that correctly handles HiDPI/Retina scaling
            from ..window_control import _get_active_window_bounds_impl

            bounds_result = _get_active_window_bounds_impl()

            if bounds_result.success and bounds_result.x is not None:
                region = (
                    bounds_result.x,
                    bounds_result.y,
                    bounds_result.width,
                    bounds_result.height,
                )
                region_description = (
                    f"active window ({bounds_result.window_title or 'unknown'})"
                )

            else:
                # Fallback to full screen if active window detection fails
                region = None
                region_description = "full screen (window detection failed)"
                emit_warning(
                    f"[yellow]⚠️  Window detection failed, falling back to full screen[/yellow]\n"
                    f"[yellow]   Error: {bounds_result.error}[/yellow]",
                    message_group=group_id,
                )
        # Now emit the main header with the final region description
        emit_rich(
            f"[bold white on blue] OCR EXTRACT TEXT 🐻 [/bold white on blue] 📖 region={region_description} language={language}",
            message_group=group_id,
        )

        try:
            # Detect HiDPI/Retina scaling factor
            from ..platform import get_screen_scale_factor

            scale_factor = get_screen_scale_factor()

            if scale_factor != 1.0:
                emit_rich(
                    f"[yellow]⚠️  HiDPI/Retina display detected (scale factor: {scale_factor}x)[/yellow]",
                    message_group=group_id,
                )
                emit_rich(
                    "[yellow]→ Coordinates will be converted from physical to logical space[/yellow]",
                    message_group=group_id,
                )

            # Log region offset information and convert to physical pixels
            if region:
                # Convert logical coordinates to physical pixels for pyautogui
                # pyautogui.screenshot() expects physical pixels on Retina displays
                region_logical = region

                region = (
                    int(region[0] * scale_factor),
                    int(region[1] * scale_factor),
                    int(region[2] * scale_factor),
                    int(region[3] * scale_factor),
                )

                emit_rich(
                    f"[cyan]📍 Region (logical): {region_logical}[/cyan]\n"
                    f"[cyan]📍 Region (physical): {region} - for screenshot capture[/cyan]",
                    message_group=group_id,
                )

            # Capture screenshot
            if region:
                screenshot = _safe_screenshot(region=region)
            else:
                screenshot = _safe_screenshot()

            # Save screenshot to temp if debug mode enabled
            from ..config_manager import get_debug_screenshots_enabled
            from ..debug_screenshot_manager import save_temp_debug_screenshot

            if get_debug_screenshots_enabled():
                save_temp_debug_screenshot(screenshot, "ocr_region", group_id)

            # Extract text with scaling correction and region offset
            # Pass region offset (x, y) so coordinates are converted to screen space
            region_offset = (region[0], region[1]) if region else None

            result = extract_text_from_image(
                screenshot,
                language=language,
                scale_factor=scale_factor,
                region_offset=region_offset,
            )
            result.region = list(region) if region else None

            if result.success:
                emit_rich(
                    f"[green]✅ Extracted {result.total_words} words with avg confidence {result.average_confidence:.2f}[/green]",
                    message_group=group_id,
                )
                if result.text_elements:
                    sample_elem = result.text_elements[0]
                    emit_rich(
                        f"[cyan]Example: '{sample_elem.text}' at screen coords ({sample_elem.center_x}, {sample_elem.center_y})[/cyan]",
                        message_group=group_id,
                    )
                emit_rich(
                    f"[dim]Full text: {result.full_text[:200]}{'...' if len(result.full_text) > 200 else ''}[/dim]",
                    message_group=group_id,
                )

                # Success-conditional compaction: Return compact result (unless internal call)
                if len(result.text_elements) > 0 and not _internal:
                    compact_result = _compact_ocr_extract_result(result)
                    emit_rich(
                        f"[dim]💾 Compacted OCR result: {len(result.text_elements)} elements → summary + {len(compact_result.key_elements)} key elements[/dim]",
                        message_group=group_id,
                    )
                    return compact_result
            else:
                emit_error(
                    f"[red]OCR extraction failed: {result.error}[/red]",
                    message_group=group_id,
                )

            # Failure or empty result - return full diagnostic data
            return result

        except Exception as e:
            emit_error(
                f"[red]Screenshot or OCR failed: {e}[/red]",
                message_group=group_id,
            )
            return OCRExtractResult(
                success=False,
                error=str(e),
            )

    # ============================================================================
    # TOOL 2: FIND TEXT ON SCREEN (~113 lines)
    # Search for specific text on screen and return its coordinates
    # ============================================================================

    @agent.tool
    def desktop_find_text(
        context: RunContext,
        search_text: str,
        case_sensitive: bool = False,
        fuzzy: bool = False,
        fuzzy_threshold: float = 0.75,
        x: int | None = None,
        y: int | None = None,
        width: int | None = None,
        height: int | None = None,
        use_active_window: bool = True,
        use_full_screen: bool = False,
        language: str = "eng",
    ) -> OCRFindResult:
        """
        Find text on screen using OCR and return its coordinates.

        By default, this searches ONLY the active window to improve performance and accuracy.
        Use use_full_screen=True to search the entire screen instead.

        This is useful for locating UI elements by their text labels.
        More reliable than VQA for finding exact text matches.

        Args:
            search_text: Text to search for (case-insensitive by default)
            case_sensitive: Whether to match case exactly (default: False)
            x: Optional left coordinate of region to search within
            y: Optional top coordinate of region to search within
            width: Optional width of region to search within
            height: Optional height of region to search within
            use_active_window: Search only the active window (default: True)
            use_full_screen: Search the entire screen instead of active window (default: False)
            language: Language code for OCR (default: "eng")

        Returns:
            OCRFindResult with matches sorted by confidence, including coordinates

        Examples:
            - desktop_find_text(search_text="Submit") - Find "Submit" in active window (RECOMMENDED)
            - desktop_find_text(search_text="Save", use_full_screen=True) - Search entire screen
            - desktop_find_text(search_text="Save", x=0, y=0, width=200, height=100) - Search in region
            - desktop_find_text(search_text="OK", case_sensitive=True) - Exact case match
        """
        group_id = generate_group_id("ocr_find", search_text[:30])
        emit_rich(
            f"[bold white on blue] OCR FIND TEXT 🐻 [/bold white on blue] 🔍 search='{search_text}' case_sensitive={case_sensitive}",
            message_group=group_id,
        )

        # First, extract all text (internal call - get full result)
        extract_result = desktop_extract_text(
            context=context,
            x=x,
            y=y,
            width=width,
            height=height,
            use_active_window=use_active_window,
            use_full_screen=use_full_screen,
            language=language,
            _internal=True,  # Get full result for searching
        )

        if not extract_result.success:
            return OCRFindResult(
                success=False,
                error=extract_result.error,
                search_text=search_text,
            )

        # Search within extracted text elements
        find_result = find_text_in_elements(
            search_text=search_text,
            text_elements=extract_result.text_elements,
            case_sensitive=case_sensitive,
            fuzzy=fuzzy,
            fuzzy_threshold=fuzzy_threshold,
        )

        if find_result.found:
            emit_rich(
                f"[green]Found {find_result.total_matches} match(es) for '{search_text}'[/green]",
                message_group=group_id,
            )
            if find_result.best_match:
                emit_rich(
                    f"[green]Best match: '{find_result.best_match.text}' at ({find_result.best_match.center_x}, {find_result.best_match.center_y}) confidence={find_result.best_match.confidence:.2f}[/green]",
                    message_group=group_id,
                )

            # Success-conditional compaction: Return compact result
            compact_result = _compact_ocr_find_result(find_result)
            emit_rich(
                f"[dim]💾 Compacted find result: {find_result.total_matches} matches → best match only[/dim]",
                message_group=group_id,
            )
            return compact_result
        else:
            emit_warning(
                f"[yellow]No matches found for '{search_text}'[/yellow]",
                message_group=group_id,
            )
            emit_rich(
                f"[dim]Returning full OCR data ({len(extract_result.text_elements)} elements) for debugging[/dim]",
                message_group=group_id,
            )
            # Failure - return full diagnostic data with all text elements
            find_result.full_text_elements = (
                extract_result.text_elements
            )  # Add for debugging

        return find_result

    # ============================================================================
    # TOOL 3: VERIFY TEXT VISIBLE (~112 lines)
    # Check if specific text is visible on screen
    # ============================================================================

    @agent.tool
    def desktop_verify_text(
        context: RunContext,
        expected_text: str,
        fuzzy: bool = False,
        fuzzy_threshold: float = 0.75,
        x: int | None = None,
        y: int | None = None,
        width: int | None = None,
        height: int | None = None,
        use_active_window: bool = True,
        use_full_screen: bool = False,
        language: str = "eng",
        case_sensitive: bool = False,
    ) -> OCRVerifyResult:
        """
        Verify that expected text appears on screen (useful for validation).

        By default, this checks ONLY the active window to improve performance and accuracy.
        Use use_full_screen=True to check the entire screen instead.

        This is helpful for confirming that an action succeeded by checking
        for success/error messages on screen.

        Args:
            expected_text: Text that should appear on screen
            x: Optional left coordinate of region to check
            y: Optional top coordinate of region to check
            width: Optional width of region to check
            height: Optional height of region to check
            use_active_window: Check only the active window (default: True)
            use_full_screen: Check the entire screen instead of active window (default: False)
            language: Language code for OCR (default: "eng")
            case_sensitive: Whether to match case exactly (default: False)

        Returns:
            OCRVerifyResult with verification status and location if found

        Examples:
            - desktop_verify_text(expected_text="Save complete") - Verify in active window (RECOMMENDED)
            - desktop_verify_text(expected_text="Error", use_full_screen=True) - Check entire screen
            - desktop_verify_text(expected_text="Login", x=800, y=500, width=200, height=100)
        """
        group_id = generate_group_id("ocr_verify", expected_text[:30])
        emit_rich(
            f"[bold white on blue] OCR VERIFY TEXT 🐻 [/bold white on blue] ✓ expected='{expected_text}'",
            message_group=group_id,
        )

        # Find the text
        find_result = desktop_find_text(
            context=context,
            search_text=expected_text,
            case_sensitive=case_sensitive,
            fuzzy=fuzzy,
            fuzzy_threshold=fuzzy_threshold,
            x=x,
            y=y,
            width=width,
            height=height,
            use_active_window=use_active_window,
            use_full_screen=use_full_screen,
            language=language,
        )

        if not find_result.success:
            return OCRVerifyResult(
                success=False,
                error=find_result.error,
                expected_text=expected_text,
            )

        # Verification result
        if find_result.found and find_result.best_match:
            emit_rich(
                f"[bold green]✓ Text verified: '{expected_text}' found at ({find_result.best_match.center_x}, {find_result.best_match.center_y})[/bold green]",
                message_group=group_id,
            )
            return OCRVerifyResult(
                success=True,
                expected_text=expected_text,
                found=True,
                actual_text=find_result.best_match.text,
                match_confidence=find_result.best_match.confidence,
                location=find_result.best_match,
            )
        else:
            emit_warning(
                f"[yellow]✗ Text not found: '{expected_text}'[/yellow]",
                message_group=group_id,
            )
            # Extract all text to show what WAS found
            extract_result = desktop_extract_text(
                context=context,
                x=x,
                y=y,
                width=width,
                height=height,
                use_active_window=use_active_window,
                use_full_screen=use_full_screen,
                language=language,
            )
            actual_text = extract_result.full_text if extract_result.success else ""

            return OCRVerifyResult(
                success=True,  # Tool succeeded, just didn't find the text
                expected_text=expected_text,
                found=False,
                actual_text=actual_text[:500],  # First 500 chars
                match_confidence=0.0,
            )

    # ============================================================================
    # TOOL 4: CLICK TEXT (~264 lines)
    # Find text via OCR and click on it with smart offset calculation
    # ============================================================================

    @agent.tool
    def desktop_click_text(
        context: RunContext,
        x: int | None = None,
        y: int | None = None,
        width: int | None = None,
        height: int | None = None,
        use_active_window: bool = True,
        use_full_screen: bool = False,
        language: str = "eng",
        show_confidence: bool = True,
        min_confidence: float = 0.0,
    ) -> OCRDebugVisualization:
        """
        Visual debugger showing ALL OCR bounding boxes on screen.

        This is a CRITICAL debugging tool for diagnosing OCR click accuracy!
        It generates an annotated screenshot showing:
        - Green rectangles around all detected text
        - Red dots at center points (where clicks would happen)
        - Text labels with confidence scores
        - Helps identify offset issues visually

        Use this to see exactly where OCR thinks text is located!

        🚨 Note: This tool ALWAYS saves a debug screenshot (to system temp) since it's
        explicitly for debugging. Use only when user requests OCR visualization!

        Args:
            x: Optional left coordinate of region
            y: Optional top coordinate of region
            width: Optional width of region
            height: Optional height of region
            use_active_window: Capture only active window (default: True)
            use_full_screen: Capture entire screen (default: False)
            language: Language code for OCR (default: "eng")
            show_confidence: Whether to show confidence scores in labels (default: True)
            min_confidence: Minimum confidence to display (0.0-1.0, default: 0.0)

        Returns:
            OCRDebugVisualization with screenshot path showing all bounding boxes
            Screenshot saved to system temp directory (not user's pwd)

        Examples:
            # Debug active window OCR (only when user explicitly requests)
            result = desktop_show_all_ocr_boxes()
            print(f"Saved debug visualization: {result.screenshot_path}")

            # Show only high-confidence text (>70%)
            result = desktop_show_all_ocr_boxes(min_confidence=0.7)

            # Debug specific region
            result = desktop_show_all_ocr_boxes(x=100, y=100, width=500, height=300)
        """
        group_id = generate_group_id("ocr_debug_viz", "show_all_boxes")
        emit_rich(
            "[bold yellow on blue] OCR DEBUG VISUALIZATION [/bold yellow on blue] 📊 Generating bounding box overlay",
            message_group=group_id,
        )

        # Extract all text with OCR
        extract_result = desktop_extract_text(
            context=context,
            x=x,
            y=y,
            width=width,
            height=height,
            use_active_window=use_active_window,
            use_full_screen=use_full_screen,
            language=language,
        )

        if not extract_result.success:
            return OCRDebugVisualization(
                success=False,
                error=extract_result.error,
            )

        try:
            # Detect HiDPI/Retina scaling factor
            from ..platform import get_screen_scale_factor
            from PIL import (
                ImageFont,
            )  # Import at function level to avoid scoping issues

            scale_factor = get_screen_scale_factor()

            # Capture screenshot again for drawing
            region = None
            if (
                x is not None
                and y is not None
                and width is not None
                and height is not None
            ):
                region = (x, y, width, height)
            elif use_full_screen:
                region = None
            elif use_active_window:
                # BUGFIX: Use the centralized window bounds helper that correctly handles HiDPI/Retina scaling
                from ..window_control import _get_active_window_bounds_impl
                from ..platform import get_screen_scale_factor

                bounds_result = _get_active_window_bounds_impl()
                if bounds_result.success and bounds_result.x is not None:
                    # Convert logical coordinates to physical pixels for pyautogui
                    scale_factor = get_screen_scale_factor()
                    region = (
                        int(bounds_result.x * scale_factor),
                        int(bounds_result.y * scale_factor),
                        int(bounds_result.width * scale_factor),
                        int(bounds_result.height * scale_factor),
                    )

            screenshot = _safe_screenshot(region=region)
            draw = ImageDraw.Draw(screenshot, "RGBA")

            # Filter by confidence
            elements = [
                elem
                for elem in extract_result.text_elements
                if elem.confidence >= min_confidence
            ]

            # Draw each bounding box
            for elem in elements:
                # After the region offset fix, text_elements now have coordinates in screen space
                # To draw on the screenshot, we need to convert back to screenshot-relative coords:
                # 1. Subtract region offset (screen -> screenshot relative)
                # 2. Scale up for HiDPI (logical -> physical pixels)

                # Convert from screen coords to screenshot-relative coords
                screen_x = elem.x
                screen_y = elem.y
                screenshot_x = screen_x - (region[0] if region else 0)
                screenshot_y = screen_y - (region[1] if region else 0)

                # Scale up for HiDPI/Retina
                box_x = int(screenshot_x * scale_factor)
                box_y = int(screenshot_y * scale_factor)
                box_w = int(elem.width * scale_factor)
                box_h = int(elem.height * scale_factor)

                # Center point (same logic)
                screenshot_center_x = elem.center_x - (region[0] if region else 0)
                screenshot_center_y = elem.center_y - (region[1] if region else 0)
                center_x = int(screenshot_center_x * scale_factor)
                center_y = int(screenshot_center_y * scale_factor)

                # Draw bounding box (green with transparency)
                draw.rectangle(
                    [(box_x, box_y), (box_x + box_w, box_y + box_h)],
                    outline=(0, 255, 0, 200),
                    width=2,
                )

                # Draw center point (red dot where click would happen)
                dot_radius = 4
                draw.ellipse(
                    [
                        (center_x - dot_radius, center_y - dot_radius),
                        (center_x + dot_radius, center_y + dot_radius),
                    ],
                    fill=(255, 0, 0, 255),
                )

                # Add text label
                if show_confidence:
                    label = f"{elem.text[:20]} ({elem.confidence:.2f})"
                else:
                    label = elem.text[:20]

                # Try to load font (ImageFont imported at function level)
                try:
                    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 12)
                except Exception:
                    font = ImageFont.load_default()

                # Draw label background
                bbox = draw.textbbox((box_x, box_y - 18), label, font=font)
                draw.rectangle(
                    (bbox[0] - 2, bbox[1] - 2, bbox[2] + 2, bbox[3] + 2),
                    fill=(255, 255, 255, 200),
                )
                draw.text(
                    (box_x, box_y - 18),
                    label,
                    fill=(0, 128, 0, 255),
                    font=font,
                )

            # Add legend
            legend_text = [
                "OCR Bounding Box Visualization",
                f"Total boxes: {len(elements)} (min confidence: {min_confidence:.2f})",
                f"HiDPI Scale Factor: {scale_factor}x",
                "Green rectangles: Text bounding boxes",
                "Red dots: Click center points",
                "(Coordinates shown are in SCREEN/LOGICAL space)",
            ]

            try:
                legend_font = ImageFont.truetype(
                    "/System/Library/Fonts/Helvetica.ttc", 14
                )
            except Exception:
                legend_font = ImageFont.load_default()

            legend_y = 10
            for line in legend_text:
                bbox = draw.textbbox((10, legend_y), line, font=legend_font)
                draw.rectangle(
                    (bbox[0] - 5, bbox[1] - 2, bbox[2] + 5, bbox[3] + 2),
                    fill=(0, 0, 0, 180),
                )
                draw.text(
                    (10, legend_y), line, fill=(255, 255, 255, 255), font=legend_font
                )
                legend_y += 20

            # Save screenshot to temp directory
            # This tool is explicitly for debugging, so saving is expected
            from ..debug_screenshot_manager import save_temp_debug_screenshot

            save_path = save_temp_debug_screenshot(
                screenshot, "ocr_debug_visualization", group_id
            )

            emit_rich(
                f"[green]✅ OCR debug visualization saved to temp: {save_path}[/green]",
                message_group=group_id,
            )
            emit_rich(
                "[dim]   (Use gui_cub_save_debug_screenshot() to copy to current directory if needed)[/dim]",
                message_group=group_id,
            )
            emit_rich(
                f"[cyan]📊 Displayed {len(elements)} text boxes[/cyan]",
                message_group=group_id,
            )

            return OCRDebugVisualization(
                success=True,
                screenshot_path=str(save_path),
                total_boxes=len(elements),
                language=language,
                message=f"Visualization saved with {len(elements)} bounding boxes",
            )

        except Exception as e:
            emit_error(
                f"[red]Visualization failed: {e}[/red]",
                message_group=group_id,
            )
            return OCRDebugVisualization(
                success=False,
                error=str(e),
            )

    # ============================================================================
    # TOOL 5: SMART SCROLL TO TEXT (~167 lines)
    # Scroll until specific text becomes visible on screen
    # ============================================================================

    @agent.tool
    def desktop_find_text_reliable(
        context: RunContext,
        search_text: str,
        min_confidence: float = 0.7,
        case_sensitive: bool = False,
        x: int | None = None,
        y: int | None = None,
        width: int | None = None,
        height: int | None = None,
        use_active_window: bool = True,
        use_full_screen: bool = False,
        language: str = "eng",
    ) -> OCRFindResult:
        """
        Find text on screen with OCR confidence filtering for reliable results.

        This is a wrapper around desktop_find_text() that ONLY returns matches
        with OCR confidence >= min_confidence. Use this when you need high
        accuracy and want to filter out low-quality OCR detections.

        Filtering low-confidence matches reduces false positives and improves
        click accuracy!

        Args:
            search_text: Text to search for
            min_confidence: Minimum OCR confidence required (0.0-1.0, default: 0.7)
                           0.7 = 70% confidence, 0.8 = 80%, etc.
            case_sensitive: Whether to match case exactly (default: False)
            x: Optional left coordinate of search region
            y: Optional top coordinate of search region
            width: Optional width of search region
            height: Optional height of search region
            use_active_window: Search only active window (default: True)
            use_full_screen: Search entire screen (default: False)
            language: Language code for OCR (default: "eng")

        Returns:
            OCRFindResult with only high-confidence matches

        Examples:
            # Find "Submit" with at least 70% confidence (default)
            result = desktop_find_text_reliable(search_text="Submit")
            if result.found:
                print(f"High-confidence match at ({result.best_match.center_x}, {result.best_match.center_y})")

            # Require 80% confidence for critical clicks
            result = desktop_find_text_reliable(
                search_text="Delete Account",
                min_confidence=0.8
            )

            # Lower threshold for difficult text
            result = desktop_find_text_reliable(
                search_text="OK",
                min_confidence=0.6
            )
        """
        group_id = generate_group_id(
            "ocr_find_reliable",
            f"{search_text[:30]}_conf{int(min_confidence * 100)}",
        )
        emit_rich(
            f"[bold white on blue] OCR FIND (HIGH CONFIDENCE) 🐻 [/bold white on blue] 🔍 search='{search_text}' min_confidence={min_confidence}",
            message_group=group_id,
        )

        # Find all matches using standard method
        find_result = desktop_find_text(
            context=context,
            search_text=search_text,
            case_sensitive=case_sensitive,
            x=x,
            y=y,
            width=width,
            height=height,
            use_active_window=use_active_window,
            use_full_screen=use_full_screen,
            language=language,
        )

        if not find_result.success:
            return find_result

        # Filter matches by confidence
        # NOTE: After compaction, matches=[] but best_match still exists!
        # Check best_match instead of matches for compacted results
        if not find_result.found:
            emit_warning(
                f"[yellow]No matches found for '{search_text}'[/yellow]",
                message_group=group_id,
            )
            return find_result

        # Handle compacted results (matches=[] but best_match exists)
        if not find_result.matches and find_result.best_match:
            # Result was compacted - check best_match confidence
            if find_result.best_match.confidence < min_confidence:
                emit_warning(
                    f"[yellow]Found match but confidence {find_result.best_match.confidence:.2%} below minimum {min_confidence:.2%}[/yellow]",
                    message_group=group_id,
                )
                return OCRFindResult(
                    success=True,
                    search_text=search_text,
                    found=False,
                    total_matches=0,
                    best_match=None,
                    matches=[],
                )
            # Best match meets confidence threshold - return it
            emit_rich(
                "[green]✅ Found high-confidence match (compacted result)[/green]",
                message_group=group_id,
            )
            emit_rich(
                f"[cyan]Match: '{find_result.best_match.text}' at ({find_result.best_match.center_x}, {find_result.best_match.center_y}) conf: {find_result.best_match.confidence:.2%}[/cyan]",
                message_group=group_id,
            )
            return find_result

        # No matches at all
        if not find_result.matches:
            emit_warning(
                f"[yellow]No matches found for '{search_text}'[/yellow]",
                message_group=group_id,
            )
            return find_result

        high_conf_matches = [
            match for match in find_result.matches if match.confidence >= min_confidence
        ]

        if not high_conf_matches:
            emit_warning(
                f"[yellow]Found {len(find_result.matches)} match(es) but none met minimum confidence {min_confidence:.2f}[/yellow]",
                message_group=group_id,
            )
            return OCRFindResult(
                success=True,
                search_text=search_text,
                found=False,
                total_matches=0,
                best_match=None,
                matches=[],
            )

        # Return filtered results
        best_match = max(high_conf_matches, key=lambda m: m.confidence)
        emit_rich(
            f"[green]✅ Found {len(high_conf_matches)} high-confidence match(es)[/green]",
            message_group=group_id,
        )
        emit_rich(
            f"[cyan]Best match: '{best_match.text}' (conf: {best_match.confidence:.2%})[/cyan]",
            message_group=group_id,
        )

        return OCRFindResult(
            success=True,
            search_text=search_text,
            found=True,
            total_matches=len(high_conf_matches),
            best_match=best_match,
            matches=high_conf_matches,
        )

    # ============================================================================
    # TOOL 6: TOGGLE DEBUG SCREENSHOTS (~28 lines)
    # Enable/disable debug screenshot saving for troubleshooting
    # ============================================================================

    @agent.tool
    def desktop_toggle_debug_screenshots(
        context: RunContext, enabled: bool
    ) -> BaseAutomationResult:
        """Toggle debug screenshot copying to current working directory.

        When enabled, all screenshots captured will be copied to the current
        working directory in addition to their normal temporary location.
        This is useful for debugging OCR/VQA issues.

        Args:
            enabled: True to enable debug copying, False to disable

        Returns:
            BaseAutomationResult indicating success

        Examples:
            # Enable debug mode
            result = desktop_toggle_debug_screenshots(enabled=True)
            # Now all screenshots will be copied to CWD

            # Disable debug mode
            result = desktop_toggle_debug_screenshots(enabled=False)
        """
        from ..config_manager import set_debug_screenshots_enabled

        set_debug_screenshots_enabled(enabled)

        return BaseAutomationResult(
            success=True,
        )
