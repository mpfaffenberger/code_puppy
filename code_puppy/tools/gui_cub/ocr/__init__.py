"""OCR tools for text extraction and search from images.

This package provides OCR functionality split into focused modules.
"""

from __future__ import annotations

from .extraction import extract_text_from_image
from .result_types import (
    OCRDebugVisualization,
    OCRExtractResult,
    OCRFindResult,
    OCRVerifyResult,
    TextBoundingBox,
)
from .search import find_text_in_elements
from .tools import register_ocr_tools

__all__ = [
    # Types
    "TextBoundingBox",
    "OCRExtractResult",
    "OCRFindResult",
    "OCRVerifyResult",
    "OCRDebugVisualization",
    # Functions
    "extract_text_from_image",
    "find_text_in_elements",
    # Tools
    "register_ocr_tools",
]
