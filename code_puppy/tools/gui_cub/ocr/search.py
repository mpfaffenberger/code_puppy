"""OCR text search and matching."""

from __future__ import annotations


from ..fuzzy_matching import similarity_score
from ..ocr_providers import get_ocr_provider
from .result_types import OCRFindResult, TextBoundingBox


def find_text_in_elements(
    search_text: str,
    text_elements: list[TextBoundingBox],
    case_sensitive: bool = False,
    fuzzy: bool = False,
    fuzzy_threshold: float = 0.75,
) -> OCRFindResult:
    """
    Search for text within OCR text elements.

    Uses existing fuzzy_matching module for consistent matching behavior
    with optimized rapidfuzz performance.

    Args:
        search_text: Text to search for
        text_elements: List of text elements from OCR extraction
        case_sensitive: Whether to match case exactly
        fuzzy: Whether to use fuzzy matching (default: False for exact/substring only)
        fuzzy_threshold: Minimum similarity score for fuzzy matches (0.0-1.0, default: 0.75)

    Returns:
        OCRFindResult with matching elements
    """
    from code_puppy.messaging import emit_warning
    from ..rich_emit import emit_rich

    emit_rich(
        f"[cyan]🔎 OCR TEXT SEARCH[/cyan]\n"
        f"[dim]   Searching for: '{search_text}'[/dim]\n"
        f"[dim]   Case sensitive: {case_sensitive}[/dim]\n"
        f"[dim]   Fuzzy: {fuzzy} (threshold={fuzzy_threshold})[/dim]\n"
        f"[dim]   Total OCR elements: {len(text_elements)}[/dim]"
    )

    matches = []
    search_lower = search_text.lower() if not case_sensitive else search_text

    for elem in text_elements:
        elem_text_raw = elem.text
        elem_text = elem_text_raw if case_sensitive else elem_text_raw.lower()

        # Exact or substring match first (fast path)
        if search_lower in elem_text:
            matches.append(elem)
            continue

        # Optional fuzzy matching as fallback (uses optimized rapidfuzz)
        if fuzzy:
            # Use existing fuzzy_matching module for consistency
            score = similarity_score(search_text, elem_text_raw)
            if score >= fuzzy_threshold:
                matches.append(elem)

    # Sort by confidence (highest first)
    matches.sort(key=lambda e: e.confidence, reverse=True)

    if matches:
        emit_rich(
            f"[green]✅ FOUND {len(matches)} MATCH(ES)[/green]\n"
            f"[dim]   Best match: '{matches[0].text}' at ({matches[0].center_x}, {matches[0].center_y}) confidence {matches[0].confidence:.2%}[/dim]"
        )
        for i, match in enumerate(matches[:5], 1):  # Show first 5
            emit_rich(
                f"[dim]   {i}. '{match.text}' at ({match.center_x}, {match.center_y}) conf:{match.confidence:.2%}[/dim]"
            )
        if len(matches) > 5:
            emit_rich(f"[dim]   ... and {len(matches) - 5} more[/dim]")
    else:
        emit_rich(
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


def _check_ocr_capability() -> tuple[bool, str]:
    """Check if any OCR provider is available.

    Native OCR providers (WinRT on Windows, Vision Framework on macOS) are used.
    This check verifies that at least one OCR provider is available.

    Returns:
        Tuple of (is_available, error_message)
    """
    from code_puppy.tools.gui_cub.config_manager import load_config

    config = load_config()
    if not config:
        return False, "Platform not calibrated. Run gui_cub_calibrate() first."

    # Check if native OCR provider is available
    ocr_chain = get_ocr_provider()
    available_providers = ocr_chain.get_available_providers()

    if not available_providers:
        # No OCR providers available at all
        return False, (
            "No OCR providers available. "
            "Requires Windows 10+ or macOS 10.15+ for native OCR"
        )

    # Native provider available
    return True, ""
