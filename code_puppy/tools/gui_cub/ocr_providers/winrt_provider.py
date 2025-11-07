"""Windows WinRT OCR provider (Windows 10+ native OCR).

This module provides OCR using Windows Runtime (WinRT) APIs, specifically
Windows.Media.Ocr. This is significantly faster than Tesseract and requires
no external dependencies on Windows 10+.

Note: WinRT APIs are async, but we wrap them with asyncio.run() to provide
a synchronous interface consistent with the OCRProvider contract.
"""

from __future__ import annotations

import io
from typing import List

from PIL import Image

try:
    import asyncio

    from winsdk.windows.graphics.imaging import BitmapDecoder
    from winsdk.windows.media.ocr import OcrEngine
    from winsdk.windows.storage.streams import (
        DataWriter,
        InMemoryRandomAccessStream,
    )

    WINRT_AVAILABLE = True
except ImportError:
    WINRT_AVAILABLE = False

from .base import OCRProvider, OCRResult, OCRWord


class WinRTOCRProvider(OCRProvider):
    """Windows Runtime OCR provider using Windows.Media.Ocr.

    Provides fast, native OCR on Windows 10 and later without requiring
    external dependencies like Tesseract.

    Advantages:
    - Fast (2-5x faster than Tesseract)
    - No external dependencies
    - Native Windows integration
    - Handles DPI scaling automatically

    Requirements:
    - Windows 10 or later
    - winrt-Windows.Media.Ocr Python package
    - winrt-Windows.Graphics.Imaging Python package
    - winrt-Windows.Storage.Streams Python package
    """

    def __init__(self):
        """Initialize WinRT OCR provider."""
        self._engine = None
        if WINRT_AVAILABLE:
            try:
                # Try to create OCR engine for user's display language
                self._engine = OcrEngine.try_create_from_user_profile_languages()
            except Exception:
                # Engine creation failed, provider will be unavailable
                pass

    def is_available(self) -> bool:
        """Check if WinRT OCR is available.

        Returns:
            True if running on Windows 10+ with WinRT packages installed
        """
        return WINRT_AVAILABLE and self._engine is not None

    def get_name(self) -> str:
        """Get provider name.

        Returns:
            'WinRT OCR'
        """
        return "WinRT OCR"

    def extract_text(self, image: Image.Image, language: str = "en") -> OCRResult:
        """Extract text using WinRT OCR.

        This method wraps the async WinRT APIs with asyncio.run() to provide
        a synchronous interface.

        Args:
            image: PIL Image to perform OCR on
            language: Language code (currently ignored, uses system language)

        Returns:
            OCRResult with recognized text and bounding boxes
        """
        if not WINRT_AVAILABLE:
            return OCRResult(
                success=False,
                words=[],
                full_text="",
                provider="winrt",
                error="WinRT not available (requires Windows 10+ and winrt packages)",
            )

        if self._engine is None:
            return OCRResult(
                success=False,
                words=[],
                full_text="",
                provider="winrt",
                error="WinRT OCR engine not initialized",
            )

        try:
            # Run async OCR operation synchronously
            result = asyncio.run(self._extract_text_async(image))
            return result
        except Exception as e:
            return OCRResult(
                success=False,
                words=[],
                full_text="",
                provider="winrt",
                error=f"WinRT OCR failed: {str(e)}",
            )

    async def _extract_text_async(self, image: Image.Image) -> OCRResult:
        """Async implementation of text extraction.

        Steps:
        1. Convert PIL Image to PNG bytes
        2. Load into InMemoryRandomAccessStream
        3. Create BitmapDecoder
        4. Get SoftwareBitmap
        5. Run OCR engine
        6. Parse results

        Args:
            image: PIL Image to perform OCR on

        Returns:
            OCRResult with recognized text
        """
        # Convert PIL Image to PNG bytes
        img_bytes = io.BytesIO()
        image.save(img_bytes, format="PNG")
        img_bytes.seek(0)
        img_data = img_bytes.read()

        # Create WinRT stream
        stream = InMemoryRandomAccessStream()
        writer = DataWriter(stream.get_output_stream_at(0))
        writer.write_bytes(img_data)
        await writer.store_async()
        await writer.flush_async()

        # Decode to SoftwareBitmap
        decoder = await BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()

        # Run OCR
        ocr_result = await self._engine.recognize_async(bitmap)

        # Parse results
        words: List[OCRWord] = []
        full_text_lines: List[str] = []

        for line in ocr_result.lines:
            line_words = []
            for word in line.words:
                # WinRT returns bounding box as (x, y, width, height)
                bbox = (
                    int(word.bounding_rect.x),
                    int(word.bounding_rect.y),
                    int(word.bounding_rect.width),
                    int(word.bounding_rect.height),
                )

                # WinRT doesn't provide confidence scores, use 1.0
                ocr_word = OCRWord(text=word.text, confidence=1.0, bbox=bbox)
                words.append(ocr_word)
                line_words.append(word.text)

            # Reconstruct line text
            if line_words:
                full_text_lines.append(" ".join(line_words))

        full_text = "\n".join(full_text_lines)

        return OCRResult(
            success=True, words=words, full_text=full_text, provider="winrt"
        )
