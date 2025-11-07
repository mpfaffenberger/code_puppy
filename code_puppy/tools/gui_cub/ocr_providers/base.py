"""Base classes for OCR provider abstraction.

This module defines the abstract interface that all OCR providers must implement,
allowing GUI-Cub to use native platform OCR (WinRT, Vision Framework) with
Tesseract as a fallback.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from PIL import Image
from pydantic import BaseModel, Field


class OCRWord(BaseModel):
    """Single word or text element recognized by OCR.

    Represents a single piece of text with its bounding box and confidence score.
    All coordinates are in pixels relative to the source image.
    """

    text: str = Field(description="The recognized text")
    confidence: float = Field(
        description="Confidence score from 0.0 to 1.0",
        ge=0.0,
        le=1.0,
    )
    bbox: tuple[int, int, int, int] = Field(
        description="Bounding box as (x, y, width, height) in pixels"
    )

    @property
    def x(self) -> int:
        """X coordinate of top-left corner."""
        return self.bbox[0]

    @property
    def y(self) -> int:
        """Y coordinate of top-left corner."""
        return self.bbox[1]

    @property
    def width(self) -> int:
        """Width of bounding box."""
        return self.bbox[2]

    @property
    def height(self) -> int:
        """Height of bounding box."""
        return self.bbox[3]

    @property
    def center_x(self) -> int:
        """X coordinate of center point."""
        return self.bbox[0] + self.bbox[2] // 2

    @property
    def center_y(self) -> int:
        """Y coordinate of center point."""
        return self.bbox[1] + self.bbox[3] // 2


class OCRResult(BaseModel):
    """Result from an OCR operation.

    Contains all recognized text elements, full text, and metadata about
    which provider was used and whether the operation succeeded.
    """

    success: bool = Field(description="Whether OCR operation succeeded")
    words: List[OCRWord] = Field(
        default_factory=list,
        description="List of recognized text elements with bounding boxes",
    )
    full_text: str = Field(default="", description="All recognized text as a string")
    provider: str = Field(
        description="Name of OCR provider used (e.g. 'winrt', 'vision')"
    )
    error: Optional[str] = Field(
        default=None, description="Error message if operation failed"
    )


class OCRProvider(ABC):
    """Abstract base class for OCR providers.

    All OCR providers (WinRT, Vision Framework, Tesseract) must implement this
    interface to be usable in the provider chain.

    Design principles:
    - Synchronous operations only (no async)
    - Platform-agnostic coordinate system (pixels)
    - Fail gracefully with detailed error messages
    """

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this OCR provider is available on the current system.

        Returns:
            True if provider can be used, False otherwise

        Example:
            >>> provider = WinRTOCRProvider()
            >>> if provider.is_available():
            ...     result = provider.extract_text(image)
        """
        pass

    @abstractmethod
    def extract_text(self, image: Image.Image, language: str = "en") -> OCRResult:
        """Extract text from an image using this OCR provider.

        Args:
            image: PIL Image to perform OCR on
            language: Language code (e.g. 'en', 'es', 'fr')

        Returns:
            OCRResult with recognized text and metadata

        Note:
            This method must be synchronous (blocking). Async OCR APIs
            should be wrapped with asyncio.run() to provide a sync interface.
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Get human-readable name of this provider for logging.

        Returns:
            Provider name (e.g. 'WinRT OCR', 'Apple Vision', 'Tesseract')
        """
        pass
