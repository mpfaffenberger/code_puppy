"""OCR (Optical Character Recognition) tools for desktop automation."""

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

try:
    import pytesseract
    from pytesseract import Output

    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    pytesseract = None
    Output = None

from pydantic import BaseModel, Field
from pydantic_ai import RunContext

from code_puppy.messaging import emit_error, emit_info, emit_warning
from code_puppy.tools.common import generate_group_id

from .constants import ERROR_PILLOW_MISSING, ERROR_PYAUTOGUI_MISSING
from .result_types import BaseAutomationResult

# Error message for missing tesseract
ERROR_TESSERACT_MISSING = (
    "OCR tools require pytesseract and tesseract-ocr. "
    "Install with: uv pip install pytesseract && brew install tesseract (macOS) "
    "or apt-get install tesseract-ocr (Linux) "
    "or choco install tesseract (Windows)"
)


class TextBoundingBox(BaseModel):
    """A single text element with its bounding box."""

    text: str
    confidence: float  # 0.0 to 1.0
    x: int  # Top-left corner
    y: int  # Top-left corner
    width: int
    height: int
    center_x: int
    center_y: int


class OCRExtractResult(BaseAutomationResult):
    """Result from OCR text extraction.
    
    Uses success-conditional compaction:
    - On success: Returns compact summary with key elements
    - On failure: Returns full diagnostic data
    """

    # Compact fields (always included)
    found_count: int = 0
    key_elements: list[str] = Field(default_factory=list)
    summary: str = ""
    average_confidence: float = 0.0
    
    # Verbose fields (only included on failure or when text_elements needed)
    full_text: str = ""
    text_elements: list[TextBoundingBox] = Field(default_factory=list)
    total_words: int = 0
    language: str = "eng"
    region: list[int] | None = Field(
        None,
        description="Region as [x, y, width, height]",
        json_schema_extra={"items": {"type": "integer"}, "minItems": 4, "maxItems": 4},
    )


class OCRFindResult(BaseAutomationResult):
    """Result from OCR text search.
    
    Uses success-conditional compaction:
    - On found=True: Returns best match only
    - On found=False: Returns all text elements for debugging
    """

    search_text: str = ""
    found: bool = False
    total_matches: int = 0
    best_match: TextBoundingBox | None = None
    
    # Verbose fields (only on failure)
    matches: list[TextBoundingBox] = Field(default_factory=list)
    full_text_elements: list[TextBoundingBox] = Field(default_factory=list)  # All OCR elements for debugging


class OCRVerifyResult(BaseAutomationResult):
    """Result from OCR text verification."""

    expected_text: str = ""
    found: bool = False
    actual_text: str = ""
    match_confidence: float = 0.0
    location: TextBoundingBox | None = None


class OCRDebugVisualization(BaseAutomationResult):
    """Result from OCR bounding box visualization."""

    screenshot_path: str = ""
    total_boxes: int = 0
    language: str = "eng"
    message: str = ""


def _generate_ocr_summary(text_elements: list[TextBoundingBox]) -> str:
    """
    Generate a brief natural language summary of OCR findings.
    
    Categorizes elements into buttons, fields, and general text.
    
    Examples:
        - "Login form with username, password fields and Submit, Cancel buttons"
        - "Dialog with OK, Cancel buttons"
        - "Menu with File, Edit, View options"
    """
    if not text_elements:
        return "No text found"
    
    # Categorize elements by keywords
    buttons = []
    fields = []
    
    for elem in text_elements:
        text_lower = elem.text.lower()
        
        # Check for button-like elements
        if any(kw in text_lower for kw in ['submit', 'ok', 'cancel', 'button', 'save', 'close', 'confirm']):
            buttons.append(elem.text)
        
        # Check for field-like elements
        elif any(kw in text_lower for kw in ['username', 'password', 'email', 'name', 'field', 'input']):
            fields.append(elem.text)
    
    # Build summary
    parts = []
    if fields:
        parts.append(f"{', '.join(fields[:3])} fields")
    if buttons:
        parts.append(f"{', '.join(buttons[:3])} buttons")
    if not parts:
        # Generic summary
        sample_text = [elem.text for elem in text_elements[:5] if len(elem.text.strip()) > 2]
        if sample_text:
            parts.append(f"Text including: {', '.join(sample_text)}")
        else:
            parts.append(f"{len(text_elements)} text elements")
    
    return " with ".join(parts)


def _compact_ocr_extract_result(full_result: OCRExtractResult) -> OCRExtractResult:
    """
    Compress OCR extraction result to minimal essential data.
    
    Strategy:
    - Keep success/error status
    - Count total elements found
    - Extract key text elements (high confidence, meaningful words)
    - Generate brief summary
    - Strip full_text and detailed element list
    
    Args:
        full_result: Full OCR result with all data
    
    Returns:
        Compact OCR result with ~90% token reduction
    """
    # Extract high-confidence, meaningful text elements (top 10)
    key_elements = [
        elem.text
        for elem in sorted(full_result.text_elements, key=lambda e: e.confidence, reverse=True)[:10]
        if elem.confidence > 0.7 and len(elem.text.strip()) > 2
    ]
    
    # Generate summary
    summary = _generate_ocr_summary(full_result.text_elements)
    
    return OCRExtractResult(
        success=full_result.success,
        found_count=len(full_result.text_elements),
        key_elements=key_elements,
        summary=summary,
        average_confidence=full_result.average_confidence,
        error=full_result.error,
        # Explicitly exclude verbose fields
        full_text="",
        text_elements=[],
        total_words=0,
        language=full_result.language,
        region=full_result.region,
    )


def _compact_ocr_find_result(full_result: 'OCRFindResult') -> 'OCRFindResult':
    """
    Compress OCR find result to minimal data.
    
    On success: Return just the best match coordinates
    On failure: Return full data for debugging
    """
    if not full_result.found or not full_result.best_match:
        # Failure - return full result for debugging
        return full_result
    
    # Success - return compact version with just best match
    return OCRFindResult(
        success=full_result.success,
        found=True,
        search_text=full_result.search_text,
        total_matches=full_result.total_matches,
        best_match=full_result.best_match,  # Keep best match (has coords)
        matches=[],  # Strip full match list
        error=None,
    )


def extract_text_from_image(
    image: "Image.Image",
    language: str = "eng",
    scale_factor: float = 1.0,
    region_offset: tuple[int, int] | None = None,
) -> OCRExtractResult:
    """
    Extract text from a PIL Image using Tesseract OCR only.

    Args:
        image: PIL Image to extract text from
        language: Tesseract language code (e.g., "eng", "spa", "fra")
        scale_factor: HiDPI/Retina scaling factor to convert physical screenshot
                     coordinates to logical screen coordinates (default: 1.0)
        region_offset: Optional (x, y) offset if screenshot was captured from a specific
                      screen region. Coordinates will be adjusted to screen space.
                      (default: None, meaning screenshot is from screen origin)

    Returns:
        OCRExtractResult with full text and individual text elements
        (coordinates are converted to screen/logical space if scale_factor != 1.0)
    """
    return _extract_text_from_image_tesseract(
        image=image,
        language=language,
        scale_factor=scale_factor,
        region_offset=region_offset,
    )


def _extract_text_from_image_tesseract(
    image: "Image.Image",
    language: str = "eng",
    scale_factor: float = 1.0,
    region_offset: tuple[int, int] | None = None,
) -> OCRExtractResult:
    """
    Extract text from a PIL Image using Tesseract OCR.

    Args:
        image: PIL Image to extract text from
        language: Tesseract language code (e.g., "eng", "spa", "fra")
        scale_factor: HiDPI/Retina scaling factor to convert physical screenshot
                     coordinates to logical screen coordinates (default: 1.0)
        region_offset: Optional (x, y) offset if screenshot was captured from a specific
                      screen region. Coordinates will be adjusted to screen space.
                      (default: None, meaning screenshot is from screen origin)

    Returns:
        OCRExtractResult with full text and individual text elements
        (coordinates are converted to screen/logical space if scale_factor != 1.0)
    """
    from code_puppy.messaging import emit_info, emit_warning
    
    if not TESSERACT_AVAILABLE:
        return OCRExtractResult(
            success=False,
            error=ERROR_TESSERACT_MISSING,
        )

    try:
        emit_info(
            f"[bold cyan]🔍 OCR STARTING[/bold cyan]\n"
            f"[dim]   Engine: Tesseract[/dim]\n"
            f"[dim]   Language: {language}[/dim]\n"
            f"[dim]   Image size: {image.width}x{image.height}[/dim]\n"
            f"[dim]   Scale factor: {scale_factor}x[/dim]\n"
            f"[dim]   Region offset: {region_offset if region_offset else 'None (full screen)'}[/dim]"
        )
        
        # Extract text with bounding boxes
        data = pytesseract.image_to_data(
            image,
            lang=language,
            output_type=Output.DICT,
        )

        # Build text elements list
        text_elements = []
        full_text_parts = []
        total_confidence = 0.0
        word_count = 0

        for i in range(len(data["text"])):
            text = data["text"][i].strip()
            if not text:  # Skip empty strings
                continue

            conf = float(data["conf"][i])
            if conf < 0:  # Skip invalid confidence scores
                continue

            x, y, w, h = (
                data["left"][i],
                data["top"][i],
                data["width"][i],
                data["height"][i],
            )

            # Apply HiDPI/Retina scaling correction
            # Convert from physical screenshot pixels to logical screen coordinates
            if scale_factor != 1.0:
                x = int(x / scale_factor)
                y = int(y / scale_factor)
                w = int(w / scale_factor)
                h = int(h / scale_factor)

            # Apply region offset to convert from screenshot-relative to screen-absolute coordinates
            # CRITICAL FIX: When screenshot is from a specific region (e.g., active window),
            # OCR coordinates are relative to screenshot origin, but we need screen coordinates
            if region_offset is not None:
                region_x, region_y = region_offset
                x += region_x
                y += region_y

            text_elements.append(
                TextBoundingBox(
                    text=text,
                    confidence=conf / 100.0,  # Convert to 0.0-1.0 range
                    x=x,
                    y=y,
                    width=w,
                    height=h,
                    center_x=x + w // 2,
                    center_y=y + h // 2,
                )
            )

            full_text_parts.append(text)
            total_confidence += conf
            word_count += 1

        full_text = " ".join(full_text_parts)
        avg_confidence = (
            (total_confidence / word_count / 100.0) if word_count > 0 else 0.0
        )
        
        emit_info(
            f"[bold green]✅ OCR COMPLETE[/bold green]\n"
            f"[dim]   Words found: {word_count}[/dim]\n"
            f"[dim]   Average confidence: {avg_confidence:.2%}[/dim]\n"
            f"[dim]   Full text preview: {full_text[:100]}{'...' if len(full_text) > 100 else ''}[/dim]"
        )
        
        if word_count == 0:
            emit_warning(
                f"[yellow]⚠️  OCR found NO text in image[/yellow]\n"
                f"[dim]   Image might be too blurry, wrong language, or contain no text[/dim]"
            )
        elif avg_confidence < 0.5:
            emit_warning(
                f"[yellow]⚠️  OCR confidence is LOW ({avg_confidence:.2%})[/yellow]\n"
                f"[dim]   Results may be inaccurate - consider higher resolution image[/dim]"
            )

        return OCRExtractResult(
            success=True,
            full_text=full_text,
            text_elements=text_elements,
            total_words=word_count,
            average_confidence=avg_confidence,
            language=language,
        )

    except Exception as e:
        from code_puppy.messaging import emit_error
        emit_error(
            f"[red]❌ OCR FAILED[/red]\n"
            f"[dim]   Error: {e}[/dim]\n"
            f"[dim]   Image: {image.width}x{image.height}[/dim]"
        )
        return OCRExtractResult(
            success=False,
            error=f"OCR extraction failed: {e}",
        )


def find_text_in_elements(
    search_text: str,
    text_elements: list[TextBoundingBox],
    case_sensitive: bool = False,
    fuzzy: bool = False,
    fuzzy_threshold: float = 0.75,
) -> OCRFindResult:
    """
    Search for text within OCR text elements.

    Args:
        search_text: Text to search for
        text_elements: List of text elements from OCR extraction
        case_sensitive: Whether to match case exactly

    Returns:
        OCRFindResult with matching elements
    """
    from code_puppy.messaging import emit_info, emit_warning
    
    emit_info(
        f"[cyan]🔎 OCR TEXT SEARCH[/cyan]\n"
        f"[dim]   Searching for: '{search_text}'[/dim]\n"
        f"[dim]   Case sensitive: {case_sensitive}[/dim]\n"
        f"[dim]   Fuzzy: {fuzzy} (threshold={fuzzy_threshold})[/dim]\n"
        f"[dim]   Total OCR elements: {len(text_elements)}[/dim]"
    )
    
    matches = []
    search_lower = search_text.lower() if not case_sensitive else search_text

    import difflib
    for elem in text_elements:
        elem_text_raw = elem.text
        elem_text = elem_text_raw if case_sensitive else elem_text_raw.lower()

        # Exact or substring match first
        if search_lower in elem_text:
            matches.append(elem)
            continue

        # Optional fuzzy matching as fallback
        if fuzzy:
            ratio = difflib.SequenceMatcher(None, search_lower, elem_text).ratio()
            if ratio >= fuzzy_threshold:
                matches.append(elem)

    # Sort by confidence (highest first)
    matches.sort(key=lambda e: e.confidence, reverse=True)
    
    if matches:
        emit_info(
            f"[green]✅ FOUND {len(matches)} MATCH(ES)[/green]\n"
            f"[dim]   Best match: '{matches[0].text}' at ({matches[0].center_x}, {matches[0].center_y}) confidence {matches[0].confidence:.2%}[/dim]"
        )
        for i, match in enumerate(matches[:5], 1):  # Show first 5
            emit_info(
                f"[dim]   {i}. '{match.text}' at ({match.center_x}, {match.center_y}) conf:{match.confidence:.2%}[/dim]"
            )
        if len(matches) > 5:
            emit_info(f"[dim]   ... and {len(matches) - 5} more[/dim]")
    else:
        emit_warning(
            f"[yellow]❌ NO MATCHES FOUND[/yellow]\n"
            f"[dim]   Searched for: '{search_text}'[/dim]\n"
            f"[dim]   In {len(text_elements)} OCR elements[/dim]"
        )

    return OCRFindResult(
        success=True,
        search_text=search_text,
        found=len(matches) > 0,
        matches=matches,
        total_matches=len(matches),
        best_match=matches[0] if matches else None,
    )


def register_ocr_tools(agent):
    """Register OCR (Optical Character Recognition) tools."""

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
            language: Tesseract language code (default: "eng" for English)
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
        if not PYAUTOGUI_AVAILABLE:
            return OCRExtractResult(
                success=False,
                error=f"{ERROR_PYAUTOGUI_MISSING} and {ERROR_PILLOW_MISSING}",
            )

        if not TESSERACT_AVAILABLE:
            return OCRExtractResult(
                success=False,
                error=ERROR_TESSERACT_MISSING,
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
            try:
                from .platform import IS_MACOS, IS_WINDOWS

                if IS_MACOS:
                    from AppKit import NSWorkspace
                    from Quartz import (
                        CGWindowListCopyWindowInfo,
                        kCGWindowListOptionOnScreenOnly,
                        kCGNullWindowID,
                    )

                    workspace = NSWorkspace.sharedWorkspace()
                    app = workspace.frontmostApplication()
                    app_name = app.localizedName()
                    pid = app.processIdentifier()

                    window_list = CGWindowListCopyWindowInfo(
                        kCGWindowListOptionOnScreenOnly, kCGNullWindowID
                    )

                    for window in window_list:
                        if window.get("kCGWindowOwnerPID") == pid:
                            bounds = window.get("kCGWindowBounds")
                            if bounds:
                                region = (
                                    int(bounds["X"]),
                                    int(bounds["Y"]),
                                    int(bounds["Width"]),
                                    int(bounds["Height"]),
                                )
                                region_description = f"active window ({app_name})"
                                break

                elif IS_WINDOWS:
                    import win32gui

                    hwnd = win32gui.GetForegroundWindow()
                    if hwnd:
                        rect = win32gui.GetWindowRect(hwnd)
                        x_win, y_win, right, bottom = rect
                        region = (x_win, y_win, right - x_win, bottom - y_win)
                        window_title = win32gui.GetWindowText(hwnd)
                        region_description = f"active window ({window_title})"

            except Exception:
                # Fallback to full screen if active window detection fails
                region = None
                region_description = "full screen (window detection failed)"

        group_id = generate_group_id(
            "ocr_extract",
            region_description.replace(" ", "_")[:50],
        )
        emit_info(
            f"[bold white on blue] OCR EXTRACT TEXT [/bold white on blue] 📖 region={region_description} language={language}",
            message_group=group_id,
        )

        try:
            # Detect HiDPI/Retina scaling factor
            from .platform import get_screen_scale_factor

            scale_factor = get_screen_scale_factor()

            if scale_factor != 1.0:
                emit_info(
                    f"[yellow]⚠️  HiDPI/Retina display detected (scale factor: {scale_factor}x)[/yellow]",
                    message_group=group_id,
                )
                emit_info(
                    "[yellow]→ Coordinates will be converted from physical to logical space[/yellow]",
                    message_group=group_id,
                )

            # Log region offset information (CRITICAL FIX)
            if region:
                emit_info(
                    f"[cyan]📍 Region offset applied: ({region[0]}, {region[1]}) - OCR coords converted to screen space[/cyan]",
                    message_group=group_id,
                )

            # Capture screenshot
            if region:
                screenshot = pyautogui.screenshot(region=region)
            else:
                screenshot = pyautogui.screenshot()

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
                emit_info(
                    f"[green]✅ Extracted {result.total_words} words with avg confidence {result.average_confidence:.2f}[/green]",
                    message_group=group_id,
                )
                if result.text_elements:
                    sample_elem = result.text_elements[0]
                    emit_info(
                        f"[cyan]Example: '{sample_elem.text}' at screen coords ({sample_elem.center_x}, {sample_elem.center_y})[/cyan]",
                        message_group=group_id,
                    )
                emit_info(
                    f"[dim]Full text: {result.full_text[:200]}{'...' if len(result.full_text) > 200 else ''}[/dim]",
                    message_group=group_id,
                )
                
                # Success-conditional compaction: Return compact result (unless internal call)
                if len(result.text_elements) > 0 and not _internal:
                    compact_result = _compact_ocr_extract_result(result)
                    emit_info(
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
            language: Tesseract language code (default: "eng")

        Returns:
            OCRFindResult with matches sorted by confidence, including coordinates

        Examples:
            - desktop_find_text(search_text="Submit") - Find "Submit" in active window (RECOMMENDED)
            - desktop_find_text(search_text="Save", use_full_screen=True) - Search entire screen
            - desktop_find_text(search_text="Save", x=0, y=0, width=200, height=100) - Search in region
            - desktop_find_text(search_text="OK", case_sensitive=True) - Exact case match
        """
        group_id = generate_group_id("ocr_find", search_text[:30])
        emit_info(
            f"[bold white on blue] OCR FIND TEXT [/bold white on blue] 🔍 search='{search_text}' case_sensitive={case_sensitive}",
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
            emit_info(
                f"[green]Found {find_result.total_matches} match(es) for '{search_text}'[/green]",
                message_group=group_id,
            )
            if find_result.best_match:
                emit_info(
                    f"[green]Best match: '{find_result.best_match.text}' at ({find_result.best_match.center_x}, {find_result.best_match.center_y}) confidence={find_result.best_match.confidence:.2f}[/green]",
                    message_group=group_id,
                )
            
            # Success-conditional compaction: Return compact result
            compact_result = _compact_ocr_find_result(find_result)
            emit_info(
                f"[dim]💾 Compacted find result: {find_result.total_matches} matches → best match only[/dim]",
                message_group=group_id,
            )
            return compact_result
        else:
            emit_warning(
                f"[yellow]No matches found for '{search_text}'[/yellow]",
                message_group=group_id,
            )
            emit_info(
                f"[dim]Returning full OCR data ({len(extract_result.text_elements)} elements) for debugging[/dim]",
                message_group=group_id,
            )
            # Failure - return full diagnostic data with all text elements
            find_result.full_text_elements = extract_result.text_elements  # Add for debugging

        return find_result

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
            language: Tesseract language code (default: "eng")
            case_sensitive: Whether to match case exactly (default: False)

        Returns:
            OCRVerifyResult with verification status and location if found

        Examples:
            - desktop_verify_text(expected_text="Save complete") - Verify in active window (RECOMMENDED)
            - desktop_verify_text(expected_text="Error", use_full_screen=True) - Check entire screen
            - desktop_verify_text(expected_text="Login", x=800, y=500, width=200, height=100)
        """
        group_id = generate_group_id("ocr_verify", expected_text[:30])
        emit_info(
            f"[bold white on blue] OCR VERIFY TEXT [/bold white on blue] ✓ expected='{expected_text}'",
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
            emit_info(
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

    @agent.tool
    def desktop_show_all_ocr_boxes(
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

        Args:
            x: Optional left coordinate of region
            y: Optional top coordinate of region
            width: Optional width of region
            height: Optional height of region
            use_active_window: Capture only active window (default: True)
            use_full_screen: Capture entire screen (default: False)
            language: Tesseract language code (default: "eng")
            show_confidence: Whether to show confidence scores in labels (default: True)
            min_confidence: Minimum confidence to display (0.0-1.0, default: 0.0)

        Returns:
            OCRDebugVisualization with screenshot path showing all bounding boxes

        Examples:
            # Debug active window OCR
            result = desktop_show_all_ocr_boxes()
            print(f"Saved debug visualization: {result.screenshot_path}")

            # Show only high-confidence text (>70%)
            result = desktop_show_all_ocr_boxes(min_confidence=0.7)

            # Debug specific region
            result = desktop_show_all_ocr_boxes(x=100, y=100, width=500, height=300)
        """
        group_id = generate_group_id("ocr_debug_viz", "show_all_boxes")
        emit_info(
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
            from .platform import get_screen_scale_factor

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
                # Use same region logic as extract_text
                try:
                    from .platform import IS_MACOS, IS_WINDOWS

                    if IS_MACOS:
                        from AppKit import NSWorkspace
                        from Quartz import (
                            CGWindowListCopyWindowInfo,
                            kCGWindowListOptionOnScreenOnly,
                            kCGNullWindowID,
                        )

                        workspace = NSWorkspace.sharedWorkspace()
                        app = workspace.frontmostApplication()
                        pid = app.processIdentifier()

                        window_list = CGWindowListCopyWindowInfo(
                            kCGWindowListOptionOnScreenOnly, kCGNullWindowID
                        )

                        for window in window_list:
                            if window.get("kCGWindowOwnerPID") == pid:
                                bounds = window.get("kCGWindowBounds")
                                if bounds:
                                    region = (
                                        int(bounds["X"]),
                                        int(bounds["Y"]),
                                        int(bounds["Width"]),
                                        int(bounds["Height"]),
                                    )
                                    break

                    elif IS_WINDOWS:
                        import win32gui

                        hwnd = win32gui.GetForegroundWindow()
                        if hwnd:
                            rect = win32gui.GetWindowRect(hwnd)
                            x_win, y_win, right, bottom = rect
                            region = (x_win, y_win, right - x_win, bottom - y_win)

                except Exception:
                    region = None

            screenshot = pyautogui.screenshot(region=region)
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

                # Try to load font
                from PIL import ImageFont

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

            # Save screenshot
            from datetime import datetime
            from pathlib import Path
            from tempfile import gettempdir

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"ocr_debug_all_boxes_{timestamp}.png"
            save_path = Path(gettempdir()) / "code_puppy_rpa_debug" / filename
            save_path.parent.mkdir(parents=True, exist_ok=True)
            screenshot.save(save_path)

            emit_info(
                f"[green]✅ OCR debug visualization saved: {save_path}[/green]",
                message_group=group_id,
            )
            emit_info(
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
            language: Tesseract language code (default: "eng")

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
        emit_info(
            f"[bold white on blue] OCR FIND (RELIABLE) [/bold white on blue] 🔍 search='{search_text}' min_confidence={min_confidence}",
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
