"""Windows WinRT OCR provider (Windows 10+ native OCR).

This module provides OCR using Windows Runtime (WinRT) APIs via PyWinRT,
specifically Windows.Media.Ocr. This provides native Windows OCR
and requires no external dependencies on Windows 10+.

Uses the modern PyWinRT modular packages (winrt-* namespace).
See: https://pywinrt.readthedocs.io

Note: WinRT APIs are async, but we wrap them with asyncio.run() to provide
a synchronous interface consistent with the OCRProvider contract.

WinRT OCR Concurrency Handling:
    The WinRT OCR engine does NOT support concurrent RecognizeAsync operations.
    This provider implements automatic retry with exponential backoff to handle
    the common case where rapid successive OCR calls trigger concurrency errors.
"""

from __future__ import annotations

import io
import time


from PIL import Image

try:
    import asyncio

    # Import WinRT modules - note: these require winrt-* packages installed
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage.streams import (
        DataWriter,
        InMemoryRandomAccessStream,
    )

    WINRT_AVAILABLE = True
except ImportError as e:
    WINRT_AVAILABLE = False
    # Store the import error for debugging
    _IMPORT_ERROR = str(e)
except Exception as e:
    WINRT_AVAILABLE = False
    _IMPORT_ERROR = f"Unexpected error: {str(e)}"

from .base import OCRProvider, OCRResult, OCRWord


class WinRTOCRProvider(OCRProvider):
    """Windows Runtime OCR provider using Windows.Media.Ocr.

    Provides fast, native OCR on Windows 10 and later without requiring
    external dependencies.

    Advantages:
    - Fast native performance
    - No external dependencies
    - Native Windows integration
    - Handles DPI scaling automatically

    Requirements:
    - Windows 10 or later
    - PyWinRT packages (installed automatically):
      - winrt-runtime>=2.0.0
      - winrt-windows-foundation>=2.0.0
      - winrt-windows-foundation-collections>=2.0.0
      - winrt-windows-graphics-imaging>=2.0.0
      - winrt-windows-media-ocr>=2.0.0
      - winrt-windows-storage-streams>=2.0.0
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

        Implements automatic retry with exponential backoff to handle WinRT
        OCR concurrency errors when operations are called in rapid succession.

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

        # Retry logic to handle WinRT OCR concurrency errors
        max_retries = 3
        base_delay = 0.5  # seconds

        for attempt in range(max_retries):
            try:
                # Run async OCR operation synchronously
                result = asyncio.run(self._extract_text_async(image))
                return result
            except Exception as e:
                error_msg = str(e)
                # Check if it's a WinRT concurrency error
                is_concurrency_error = (
                    "RecognizeAsync" in error_msg
                    or "-2147467260" in error_msg  # E_ILLEGAL_METHOD_CALL
                )

                if is_concurrency_error and attempt < max_retries - 1:
                    # Exponential backoff: 0.5s, 1.0s, 2.0s
                    delay = base_delay * (2**attempt)
                    time.sleep(delay)
                    continue  # Retry

                # Either not a concurrency error, or we've exhausted retries
                return OCRResult(
                    success=False,
                    words=[],
                    full_text="",
                    provider="winrt",
                    error=f"WinRT OCR failed: {error_msg}",
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
        words: list[OCRWord] = []
        full_text_lines: list[str] = []

        # Convert WinRT collection to list to avoid iteration issues
        # WinRT collections can cause import errors when iterating
        # in some Python versions
        lines = list(ocr_result.lines) if ocr_result.lines else []

        for line in lines:
            line_words = []
            # Convert words collection to list as well
            words_list = list(line.words) if line.words else []
            for word in words_list:
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
