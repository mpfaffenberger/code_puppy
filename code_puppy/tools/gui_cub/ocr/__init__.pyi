"""Type stubs for OCR text extraction.

Provides OCR-based text extraction and search.
"""

from typing import Any

def extract_text(
    use_active_window: bool = ...,
    use_full_screen: bool = ...,
    x: int | None = ...,
    y: int | None = ...,
    width: int | None = ...,
    height: int | None = ...,
) -> dict[str, Any]:
    """Extract text from screen region using OCR.

    Args:
        use_active_window: Extract from active window only
        use_full_screen: Extract from entire screen
        x: Left coordinate for region
        y: Top coordinate for region
        width: Region width
        height: Region height

    Returns:
        Dict with full_text, words, confidence scores

    Example:
        result = extract_text(use_active_window=True)
        print(result["full_text"])
    """
    ...

def find_text(
    search_text: str,
    use_active_window: bool = ...,
    fuzzy: bool = ...,
) -> dict[str, Any]:
    """Find text on screen using OCR.

    Args:
        search_text: Text to search for
        use_active_window: Search in active window only
        fuzzy: Enable fuzzy matching

    Returns:
        Dict with found status, matches, coordinates

    Example:
        result = find_text("Submit", fuzzy=True)
        if result["found"]:
            print(f"Found at {result['matches'][0]['center_x']}, {result['matches'][0]['center_y']}")
    """
    ...

def verify_text(
    expected_text: str,
    use_active_window: bool = ...,
) -> dict[str, Any]:
    """Verify expected text appears on screen.

    Args:
        expected_text: Text that should be visible
        use_active_window: Check active window only

    Returns:
        Dict with verification status

    Example:
        result = verify_text("Welcome")
        assert result["verified"] is True
    """
    ...
