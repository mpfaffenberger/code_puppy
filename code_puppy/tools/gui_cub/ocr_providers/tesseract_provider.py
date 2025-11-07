"""Tesseract OCR provider (cross-platform fallback).

This module provides OCR using Tesseract, which serves as a fallback when
native platform OCR (WinRT, Vision Framework) is unavailable or fails.
"""

from __future__ import annotations

from typing import List

from PIL import Image

try:
    import pytesseract
    from pytesseract import Output

    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    pytesseract = None
    Output = None

from .base import OCRProvider, OCRResult, OCRWord


class TesseractOCRProvider(OCRProvider):
    """Tesseract OCR provider (cross-platform fallback).

    Uses pytesseract to perform OCR on images. This is the fallback provider
    used when native platform OCR is unavailable or fails.

    Requires:
    - pytesseract Python package
    - tesseract-ocr system package
    """

    # Language code mapping (ISO 639-1 to Tesseract)
    LANGUAGE_MAP = {
        "en": "eng",
        "es": "spa",
        "fr": "fra",
        "de": "deu",
        "it": "ita",
        "pt": "por",
        "ru": "rus",
        "zh": "chi_sim",
        "ja": "jpn",
        "ko": "kor",
    }

    def is_available(self) -> bool:
        """Check if Tesseract is installed and accessible.

        Returns:
            True if pytesseract and tesseract-ocr are available
        """
        if not TESSERACT_AVAILABLE:
            return False

        try:
            # Try to get Tesseract version to verify it's installed
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False

    def get_name(self) -> str:
        """Get provider name.

        Returns:
            'Tesseract'
        """
        return "Tesseract"

    def extract_text(self, image: Image.Image, language: str = "en") -> OCRResult:
        """Extract text using Tesseract OCR.

        Args:
            image: PIL Image to perform OCR on
            language: Language code (e.g. 'en', 'es', 'fr')

        Returns:
            OCRResult with recognized text and bounding boxes
        """
        if not TESSERACT_AVAILABLE:
            return OCRResult(
                success=False,
                words=[],
                full_text="",
                provider="tesseract",
                error="pytesseract not installed",
            )

        try:
            # Map language code to Tesseract language
            tesseract_lang = self.LANGUAGE_MAP.get(language, "eng")

            # Get detailed OCR data with bounding boxes
            data = pytesseract.image_to_data(
                image, lang=tesseract_lang, output_type=Output.DICT
            )

            # Parse results into OCRWord objects
            words: List[OCRWord] = []
            for i in range(len(data["text"])):
                text = data["text"][i].strip()
                if not text:  # Skip empty text
                    continue

                # Tesseract confidence is 0-100, convert to 0.0-1.0
                confidence = max(0.0, min(100.0, data["conf"][i])) / 100.0

                word = OCRWord(
                    text=text,
                    confidence=confidence,
                    bbox=(
                        data["left"][i],
                        data["top"][i],
                        data["width"][i],
                        data["height"][i],
                    ),
                )
                words.append(word)

            # Get full text (faster than reconstructing from words)
            full_text = pytesseract.image_to_string(image, lang=tesseract_lang)

            return OCRResult(
                success=True,
                words=words,
                full_text=full_text.strip(),
                provider="tesseract",
            )

        except Exception as e:
            return OCRResult(
                success=False,
                words=[],
                full_text="",
                provider="tesseract",
                error=str(e),
            )
