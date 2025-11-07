"""OCR (Optical Character Recognition) tools for desktop automation.

This module provides OCR functionality using native platform APIs:
- Windows: WinRT OCR (Windows.Media.Ocr)
- macOS: Vision Framework (VNRecognizeTextRequest)

No external dependencies required. Windows and macOS only.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


from ..result_types import BaseAutomationResult

try:
    import pyautogui
    from PIL import Image, ImageDraw

    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    pyautogui = None
    Image = None
    ImageDraw = None

# OCR uses native platform APIs only (WinRT on Windows, Vision on macOS)


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
    full_text_elements: list[TextBoundingBox] = Field(
        default_factory=list
    )  # All OCR elements for debugging


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
