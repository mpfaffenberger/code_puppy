"""OCR text extraction from images."""

from __future__ import annotations

try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    Image = None

from ..ocr_providers import get_ocr_provider
from .result_types import OCRExtractResult, OCRFindResult, TextBoundingBox


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
        if any(
            kw in text_lower
            for kw in ["submit", "ok", "cancel", "button", "save", "close", "confirm"]
        ):
            buttons.append(elem.text)

        # Check for field-like elements
        elif any(
            kw in text_lower
            for kw in ["username", "password", "email", "name", "field", "input"]
        ):
            fields.append(elem.text)

    # Build summary
    parts = []
    if fields:
        parts.append(f"{', '.join(fields[:3])} fields")
    if buttons:
        parts.append(f"{', '.join(buttons[:3])} buttons")
    if not parts:
        # Generic summary
        sample_text = [
            elem.text for elem in text_elements[:5] if len(elem.text.strip()) > 2
        ]
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
        for elem in sorted(
            full_result.text_elements, key=lambda e: e.confidence, reverse=True
        )[:10]
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


def _compact_ocr_find_result(full_result: "OCRFindResult") -> "OCRFindResult":
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
    Extract text from a PIL Image using OCR provider chain.

    Uses native platform OCR first (WinRT on Windows, Vision on macOS) with
    Tesseract as fallback.

    Args:
        image: PIL Image to extract text from
        language: Language code (e.g., "eng", "spa", "fra")
        scale_factor: HiDPI/Retina scaling factor to convert physical screenshot
                     coordinates to logical screen coordinates (default: 1.0)
        region_offset: Optional (x, y) offset if screenshot was captured from a specific
                      screen region. Coordinates will be adjusted to screen space.
                      (default: None, meaning screenshot is from screen origin)

    Returns:
        OCRExtractResult with full text and individual text elements
        (coordinates are converted to screen/logical space if scale_factor != 1.0)
    """
    # Use provider chain (WinRT/Vision → Tesseract fallback)
    ocr_chain = get_ocr_provider()

    # Convert language code to ISO 639-1 format ("eng" → "en")
    lang_code = language[:2] if len(language) > 2 else language

    provider_result = ocr_chain.extract_text(image, language=lang_code)

    if not provider_result.success:
        return OCRExtractResult(
            success=False,
            error=provider_result.error or "OCR failed",
        )

    # Convert provider OCRWords to TextBoundingBox format
    text_elements = []
    for word in provider_result.words:
        # OCR returns coordinates in screenshot space (physical pixels)
        # Convert to logical screen coordinates
        x_screen = int(word.bbox[0] / scale_factor)
        y_screen = int(word.bbox[1] / scale_factor)
        width_screen = int(word.bbox[2] / scale_factor)
        height_screen = int(word.bbox[3] / scale_factor)

        # Add region offset (also convert from physical to logical)
        if region_offset:
            region_x_logical = int(region_offset[0] / scale_factor)
            region_y_logical = int(region_offset[1] / scale_factor)
            x_screen += region_x_logical
            y_screen += region_y_logical

        text_elem = TextBoundingBox(
            text=word.text,
            confidence=word.confidence,
            x=x_screen,
            y=y_screen,
            width=width_screen,
            height=height_screen,
            center_x=x_screen + width_screen // 2,
            center_y=y_screen + height_screen // 2,
        )
        text_elements.append(text_elem)

    # Calculate average confidence
    avg_confidence = (
        sum(elem.confidence for elem in text_elements) / len(text_elements)
        if text_elements
        else 0.0
    )

    return OCRExtractResult(
        success=True,
        found_count=len(text_elements),
        full_text=provider_result.full_text,
        text_elements=text_elements,
        total_words=len(text_elements),
        average_confidence=avg_confidence,
        language=language,
    )


# Legacy Tesseract function removed - now using native platform OCR providers
# See ocr_providers/ for WinRT (Windows) and Vision (macOS) implementations
