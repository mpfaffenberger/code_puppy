"""OCR text extraction from images."""

from __future__ import annotations

from datetime import datetime
import json

from ..dependencies import PIL_AVAILABLE

if PIL_AVAILABLE:
    from PIL import Image, ImageFilter, ImageOps
else:
    Image = None
    ImageFilter = None
    ImageOps = None

from ..ocr_providers import get_ocr_provider
from .result_types import OCRExtractResult, OCRFindResult, TextBoundingBox
from ..result_types import CompactSummary


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 characters per token."""
    return max(1, len(text) // 4)


def _estimate_result_tokens(obj: dict | list | str) -> int:
    """Estimate tokens in a serialized object."""
    if isinstance(obj, str):
        return _estimate_tokens(obj)
    try:
        serialized = json.dumps(obj)
        return _estimate_tokens(serialized)
    except Exception:
        return 100  # Fallback estimate


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
    Compress OCR extraction result to minimal essential data with structured summary.

    Strategy:
    - Keep success/error status
    - Count total elements found
    - Extract top 10 text elements (high confidence, min 1 char)
    - Include x,y coordinates for clickability
    - Keep full_text for validation use cases
    - Generate structured CompactSummary with metrics

    Args:
        full_result: Full OCR result with all data

    Returns:
        Compact OCR result with ~95% token reduction (still includes coordinates!)
    """
    # Extract meaningful text elements (top 10) WITH COORDINATES
    # Note: Vision Framework on macOS reports low confidence (0.3-0.5) even for accurate text
    # This is normal - Vision uses internal model scores, not calibrated probabilities
    # Threshold at 0.25 instead of 0.7 to avoid filtering valid UI text
    sorted_elements = sorted(
        full_result.text_elements, key=lambda e: e.confidence, reverse=True
    )

    compact_elements = [
        {
            "text": elem.text,
            "x": elem.center_x,
            "y": elem.center_y,
            "confidence": round(elem.confidence, 2),
        }
        for elem in sorted_elements[:10]
        if elem.confidence > 0.25  # Lowered from 0.7 for Vision Framework (macOS)
        and len(elem.text.strip()) >= 1  # Allow 1+ chars ("OK", "Go", etc.)
        and not elem.text.strip().isspace()  # Filter pure whitespace
    ]

    # Calculate metrics
    filtered_count = len(full_result.text_elements) - len(compact_elements)
    confidence_values = [e.confidence for e in full_result.text_elements]
    below_threshold = sum(
        1 for c in confidence_values if c <= 0.25
    )  # Vision Framework threshold

    # Estimate token savings
    full_tokens = _estimate_result_tokens(
        [
            {
                "text": e.text,
                "x": e.x,
                "y": e.y,
                "width": e.width,
                "height": e.height,
                "center_x": e.center_x,
                "center_y": e.center_y,
                "confidence": e.confidence,
            }
            for e in full_result.text_elements
        ]
    )
    compact_tokens = _estimate_result_tokens(compact_elements)

    # Generate structured summary
    summary = CompactSummary(
        tool="ocr_extract",
        success=True,
        timestamp=datetime.now().isoformat(),
        found_count=len(full_result.text_elements),
        returned_count=len(compact_elements),
        filtered_count=filtered_count,
        one_line=f"Found {len(full_result.text_elements)} text elements (avg confidence: {full_result.average_confidence:.2f}), showing top {len(compact_elements)} with coordinates",
        top_items=[e["text"] for e in compact_elements[:5]],
        compaction_ratio=len(compact_elements) / len(full_result.text_elements)
        if full_result.text_elements
        else 0,
        estimated_tokens_full=full_tokens,
        estimated_tokens_compact=compact_tokens,
        tokens_saved=full_tokens - compact_tokens,
        filters_applied=[
            "confidence > 0.25 (Vision Framework adjusted)",
            "min_length >= 1 char",
            "top 10 by confidence",
            "includes x,y coordinates",
        ],
        thresholds={"confidence_min": 0.25, "min_text_length": 1, "max_elements": 10},
        confidence_stats={
            "min": min(confidence_values) if confidence_values else 0.0,
            "max": max(confidence_values) if confidence_values else 0.0,
            "avg": full_result.average_confidence,
            "below_threshold": below_threshold,
        },
        detail_hint="Use _internal=True to get all {} elements with full bounding boxes".format(
            len(full_result.text_elements)
        ),
        full_data_available=True,
        progressive_hints=[
            "Returned elements include x,y coordinates for clicking",
            "Use full_text field for complete text content",
            "If target text not found, try _internal=True for all elements",
        ],
        extra={
            "has_full_text": True,
            "has_coordinates": True,
            "language": full_result.language,
        },
    )

    return OCRExtractResult(
        success=full_result.success,
        found_count=len(full_result.text_elements),
        key_elements=compact_elements,  # Now with coordinates!
        summary=summary.model_dump(),  # Structured summary
        average_confidence=full_result.average_confidence,
        error=full_result.error,
        # Keep full_text for validation use cases
        full_text=full_result.full_text,
        # Strip verbose fields
        text_elements=[],
        total_words=0,
        language=full_result.language,
        region=full_result.region,
    )


def _compact_ocr_find_result(full_result: "OCRFindResult") -> "OCRFindResult":
    """
    Compress OCR find result to minimal data with structured summary.

    On success: Return just the best match coordinates with summary
    On failure: Return full data for debugging
    """
    if not full_result.found or not full_result.best_match:
        # Failure - return full result for debugging
        return full_result

    # Success - generate structured summary
    summary = CompactSummary(
        tool="ocr_find",
        success=True,
        timestamp=datetime.now().isoformat(),
        found_count=full_result.total_matches,
        returned_count=1,  # Best match only
        filtered_count=full_result.total_matches - 1,
        one_line=f"Found '{full_result.search_text}' at ({full_result.best_match.center_x}, {full_result.best_match.center_y}) with {full_result.best_match.confidence:.0%} confidence",
        top_items=[full_result.search_text],
        compaction_ratio=1 / full_result.total_matches
        if full_result.total_matches > 0
        else 1.0,
        filters_applied=["best_match_only"],
        detail_hint=f"Found {full_result.total_matches} matches, returning best"
        if full_result.total_matches > 1
        else None,
        full_data_available=False,  # Matches not kept
        extra={
            "search_text": full_result.search_text,
            "total_matches": full_result.total_matches,
        },
    )

    # Success - return compact version with just best match
    return OCRFindResult(
        success=full_result.success,
        found=True,
        search_text=full_result.search_text,
        total_matches=full_result.total_matches,
        best_match=full_result.best_match,  # Keep best match (has coords)
        summary=summary.model_dump(),
        matches=[],  # Strip full match list
        error=None,
    )


def prepare_ocr_image(image: "Image.Image", scale_factor: float) -> "Image.Image":
    """
    Prepare a Retina/HiDPI image for optimal OCR accuracy.

    On Retina displays, screenshots are captured at 2x physical resolution.
    OCR engines are trained on 1x DPI images and struggle with:
    - Text that appears 2x larger than expected
    - Sub-pixel anti-aliasing artifacts
    - Thin Retina font rendering

    This function normalizes 2x images to 1x using:
    1. Light Gaussian blur (radius=0.3) to suppress sub-pixel fringing
    2. BOX resampling for exact 2→1 downscale (fast, text-friendly)
    3. Grayscale conversion to remove color noise
    4. Autocontrast to maximize text clarity

    Based on industry best practices for OCR on HiDPI displays.

    Args:
        image: PIL Image at physical resolution (e.g., 1000x800 on 2x Retina)
        scale_factor: HiDPI scaling factor (2.0 for Retina, 1.0 for standard)

    Returns:
        PIL Image normalized to 1x DPI, optimized for OCR
        (e.g., 500x400 grayscale for 2x Retina input)
    """
    if not PIL_AVAILABLE:
        return image

    # Step 1: Light blur to suppress sub-pixel anti-aliasing (always apply)
    # Even on logical resolution images, this helps remove anti-aliasing artifacts
    blurred = image.filter(ImageFilter.GaussianBlur(radius=0.3))

    # Step 2: Downscale only if scale_factor > 1.0 (for true 2x physical images)
    if scale_factor > 1.0:
        new_width = round(blurred.width / scale_factor)
        new_height = round(blurred.height / scale_factor)
        processed = blurred.resize((new_width, new_height), Image.Resampling.BOX)
    else:
        # No downscaling needed
        processed = blurred

    # Always apply grayscale and autocontrast for OCR (improves accuracy)
    grayscale = ImageOps.grayscale(processed)
    normalized = ImageOps.autocontrast(grayscale, cutoff=0)

    return normalized


def extract_text_from_image(
    image: "Image.Image",
    language: str = "eng",
    scale_factor: float = 1.0,
    region_offset: tuple[int, int] | None = None,
) -> OCRExtractResult:
    """
    Extract text from a PIL Image using native platform OCR.

    Uses native platform OCR (WinRT on Windows, Vision on macOS).

    On Retina/HiDPI displays (scale_factor > 1.0), images are normalized
    to 1x DPI before OCR for optimal accuracy. OCR engines are trained on
    standard DPI and struggle with 2x Retina text.

    Args:
        image: PIL Image to extract text from (may be 2x Retina resolution)
        language: Language code (e.g., "eng", "spa", "fra") - defaults to English
        scale_factor: HiDPI/Retina scaling factor (2.0 for Retina, 1.0 for standard)
        region_offset: Optional (x, y) offset in physical pixels if screenshot was
                      captured from a specific screen region (not origin)

    Returns:
        OCRExtractResult with full text and individual text elements
        (coordinates are in logical screen space)
    """
    from code_puppy.messaging import emit_info

    # Log original image dimensions
    emit_info(
        f"[dim]🔍 DEBUG [extract_text_from_image]: Starting OCR[/dim]\n"
        f"[dim]   Input image: {image.width}x{image.height} ({image.mode})[/dim]\n"
        f"[dim]   Scale factor: {scale_factor}x[/dim]"
    )

    # ImageGrab.grab() on macOS returns LOGICAL resolution, not physical!
    # Don't downscale - the image is already at the right size for OCR
    emit_info(
        f"[dim]   Image size: {image.width}x{image.height}[/dim]\n"
        f"[dim]   Applying grayscale + contrast (NO downscaling)[/dim]"
    )

    # Just apply grayscale + contrast, no downscaling
    ocr_image = prepare_ocr_image(image, 1.0)  # scale_factor=1.0 = no downscaling

    emit_info(
        f"[dim]   ✅ Prepared for OCR: {ocr_image.width}x{ocr_image.height} ({ocr_image.mode})[/dim]"
    )

    # Use native platform OCR provider (Vision on macOS, WinRT on Windows)
    ocr_chain = get_ocr_provider()

    # Convert language code to ISO 639-1 format ("eng" → "en")
    lang_code = language[:2] if len(language) > 2 else language

    # Pass normalized 1x image to OCR
    provider_result = ocr_chain.extract_text(ocr_image, language=lang_code)

    if not provider_result.success:
        return OCRExtractResult(
            success=False,
            error=provider_result.error or "OCR failed",
        )

    # Convert provider OCRWords to TextBoundingBox format
    text_elements = []
    for word in provider_result.words:
        # OCR returns coordinates in the normalized 1x image space
        # Since we downscaled by scale_factor, these ARE already logical coordinates!
        # No division needed - the downscaling already normalized them to 1x
        x_screen = int(word.bbox[0])
        y_screen = int(word.bbox[1])
        width_screen = int(word.bbox[2])
        height_screen = int(word.bbox[3])

        # Add region offset (convert from physical to logical)
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
