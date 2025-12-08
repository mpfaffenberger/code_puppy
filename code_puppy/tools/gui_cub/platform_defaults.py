"""Platform-specific default values for GUI automation.

These defaults are tuned based on the underlying tooling differences:

macOS:
- OCR: Vision Framework returns internal model scores (0.3-0.6 typical for clean text)
- Accessibility: atomacos uses AXTitle/AXDescription matching

Windows:
- OCR: WinRT OCR doesn't provide confidence scores (always returns 1.0)
- Accessibility: pywinauto UI Automation uses Name/AutomationId/Value matching

The thresholds are calibrated for each platform's behavior to provide
consistent user experience across platforms.
"""

from __future__ import annotations

import sys

# =============================================================================
# OCR Confidence Thresholds
# =============================================================================
# These filter OCR results based on the provider's confidence score.
#
# macOS (Vision Framework):
#   - Returns internal model scores, NOT calibrated probabilities
#   - Clean UI text (12-16pt) typically scores 0.35-0.55
#   - 0.5 = "good match", NOT 50% certainty
#   - Use 0.25-0.5 for filtering
#
# Windows (WinRT OCR):
#   - Does NOT provide confidence scores
#   - Always returns 1.0 for all detected text
#   - Threshold is effectively ignored but kept for API consistency
#
OCR_CONFIDENCE_MACOS: float = 0.5
OCR_CONFIDENCE_WINDOWS: float = 0.5  # Ignored (WinRT returns 1.0), kept for consistency
OCR_CONFIDENCE_DEFAULT: float = 0.5  # Fallback for unknown platforms

# =============================================================================
# Fuzzy Matching Thresholds (Accessibility API)
# =============================================================================
# These control how strictly element names must match the search text.
#
# macOS (atomacos):
#   - Matches against AXTitle and AXDescription attributes
#   - More lenient matching works well (0.6)
#   - macOS apps tend to have consistent, descriptive element names
#
# Windows (pywinauto UI Automation):
#   - Matches against Name, AutomationId, and Value properties
#   - Stricter matching needed (0.7) due to:
#     - Different text normalization
#     - More varied element naming conventions
#     - AutomationId often contains technical strings
#
FUZZY_THRESHOLD_MACOS: float = 0.6
FUZZY_THRESHOLD_WINDOWS: float = 0.7
FUZZY_THRESHOLD_DEFAULT: float = 0.6  # Fallback for unknown platforms


# =============================================================================
# Helper Functions
# =============================================================================


def get_default_ocr_confidence() -> float:
    """Get platform-appropriate OCR confidence threshold.

    Returns:
        OCR confidence threshold for current platform.
        - macOS: 0.5 (Vision Framework internal scores)
        - Windows: 0.5 (WinRT always returns 1.0, so this is ignored)
        - Other: 0.5 (fallback)

    Example:
        >>> confidence = get_default_ocr_confidence()
        >>> # Use in OCR filtering
        >>> if result.confidence >= confidence:
        ...     matches.append(result)
    """
    if sys.platform == "darwin":
        return OCR_CONFIDENCE_MACOS
    elif sys.platform == "win32":
        return OCR_CONFIDENCE_WINDOWS
    return OCR_CONFIDENCE_DEFAULT


def get_default_fuzzy_threshold() -> float:
    """Get platform-appropriate fuzzy matching threshold.

    Returns:
        Fuzzy matching threshold for current platform.
        - macOS: 0.6 (atomacos AXTitle/AXDescription matching)
        - Windows: 0.7 (pywinauto Name/AutomationId matching)
        - Other: 0.6 (fallback)

    Example:
        >>> threshold = get_default_fuzzy_threshold()
        >>> # Use in accessibility element search
        >>> if similarity_score(search, element.name) >= threshold:
        ...     matches.append(element)
    """
    if sys.platform == "darwin":
        return FUZZY_THRESHOLD_MACOS
    elif sys.platform == "win32":
        return FUZZY_THRESHOLD_WINDOWS
    return FUZZY_THRESHOLD_DEFAULT


def get_platform_defaults() -> dict[str, float]:
    """Get all platform defaults as a dictionary.

    Useful for debugging and logging.

    Returns:
        Dictionary with all threshold values for current platform.

    Example:
        >>> defaults = get_platform_defaults()
        >>> print(f"OCR confidence: {defaults['ocr_confidence']}")
        >>> print(f"Fuzzy threshold: {defaults['fuzzy_threshold']}")
    """
    return {
        "platform": sys.platform,
        "ocr_confidence": get_default_ocr_confidence(),
        "fuzzy_threshold": get_default_fuzzy_threshold(),
    }
