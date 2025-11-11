"""macOS Vision Framework OCR provider (macOS 10.15+ native OCR).

This module provides OCR using Apple's Vision framework, specifically
VNRecognizeTextRequest. This is significantly faster than Tesseract and
requires no external dependencies on macOS 10.15+.

Key advantages:
- Native Retina/HiDPI handling (normalized coordinates)
- Fast (2-5x faster than Tesseract)
- No external dependencies
"""

from __future__ import annotations

import io
import platform
from typing import List

from PIL import Image

try:
    import Vision
    from Foundation import NSData
    from Quartz import CGImageSourceCreateImageAtIndex, CGImageSourceCreateWithData

    VISION_AVAILABLE = True
except ImportError:
    VISION_AVAILABLE = False

from .base import OCRProvider, OCRResult, OCRWord


class VisionOCRProvider(OCRProvider):
    """Apple Vision Framework OCR provider using VNRecognizeTextRequest.

    Provides fast, native OCR on macOS 10.15 (Catalina) and later without
    requiring external dependencies like Tesseract.

    Advantages:
    - Fast (2-5x faster than Tesseract)
    - No external dependencies
    - Native macOS integration
    - Handles Retina/HiDPI automatically (normalized coordinates)
    - Better accuracy for macOS screenshots

    Requirements:
    - macOS 10.15 (Catalina) or later
    - pyobjc-framework-Vision Python package
    - pyobjc-framework-Quartz Python package
    
    IMPORTANT - Confidence Score Interpretation:
    Vision Framework reports confidence as internal model scores (0.0-1.0),
    NOT calibrated probabilities. For clean UI text (12-16pt):
    - Expected range: 0.35-0.55 (35-55%)
    - 0.5 = "good match", NOT 50% certainty
    - Values are non-linear, logistic scale
    - Scores < 0.3 indicate uncertain segmentation
    
    Comparison to other engines:
    - Tesseract: 80-99 (rescaled percentage)
    - Google Vision: 0.8-1.0 (calibrated probability)  
    - Vision: 0.3-0.8 (internal model space)
    
    Use confidence threshold of 0.25-0.3 for filtering, not 0.7!
    """

    def is_available(self) -> bool:
        """Check if Vision Framework OCR is available.

        Returns:
            True if running on macOS 10.15+ with PyObjC installed
        """
        if not VISION_AVAILABLE:
            return False

        # Check macOS version >= 10.15 (Vision OCR introduced in Catalina)
        try:
            version_str = platform.mac_ver()[0]
            if not version_str:
                return False

            parts = version_str.split(".")
            if len(parts) < 2:
                return False

            major = int(parts[0])
            minor = int(parts[1])

            # macOS 10.15+ or macOS 11+
            return (major == 10 and minor >= 15) or major >= 11
        except (ValueError, IndexError):
            return False

    def get_name(self) -> str:
        """Get provider name.

        Returns:
            'Apple Vision'
        """
        return "Apple Vision"

    def extract_text(self, image: Image.Image, language: str = "en") -> OCRResult:
        """Extract text using Vision Framework.

        Steps:
        1. Convert PIL Image to CGImage
        2. Create VNImageRequestHandler
        3. Create VNRecognizeTextRequest with fast recognition
        4. Perform request
        5. Parse observations

        Args:
            image: PIL Image to perform OCR on
            language: Language code (e.g. 'en', 'es', 'fr')

        Returns:
            OCRResult with recognized text and bounding boxes

        Note:
            Vision Framework returns normalized coordinates (0.0-1.0).
            We convert these to pixel coordinates for consistency with
            other OCR providers.
        """
        if not VISION_AVAILABLE:
            return OCRResult(
                success=False,
                words=[],
                full_text="",
                provider="vision",
                error="Vision Framework not available (requires macOS 10.15+ and pyobjc)",
            )

        try:
            # Convert PIL Image to PNG bytes
            img_bytes = io.BytesIO()
            image.save(img_bytes, format="PNG")
            img_data = NSData.dataWithBytes_length_(
                img_bytes.getvalue(), len(img_bytes.getvalue())
            )

            # Create CGImage from data
            image_source = CGImageSourceCreateWithData(img_data, None)
            if not image_source:
                return OCRResult(
                    success=False,
                    words=[],
                    full_text="",
                    provider="vision",
                    error="Failed to create CGImageSource from image data",
                )

            cg_image = CGImageSourceCreateImageAtIndex(image_source, 0, None)
            if not cg_image:
                return OCRResult(
                    success=False,
                    words=[],
                    full_text="",
                    provider="vision",
                    error="Failed to create CGImage from image source",
                )

            # Create Vision request
            request = Vision.VNRecognizeTextRequest.alloc().init()

            # Set recognition level to accurate (1) for better text detection
            # VNRequestTextRecognitionLevelFast = 0 (faster but may miss text)
            # VNRequestTextRecognitionLevelAccurate = 1 (slower but more reliable)
            # Using accurate mode to ensure we don't miss text
            request.setRecognitionLevel_(1)

            # Enable language correction for better accuracy on UI text
            request.setUsesLanguageCorrection_(True)

            # Set recognition language (default to English US for UI text)
            # Using full locale (en-US) instead of just language code for better results
            lang_locale = f"{language}-US" if language == "en" else language
            request.setRecognitionLanguages_([lang_locale])

            # Use latest revision if available (newer = better accuracy)
            if hasattr(Vision.VNRecognizeTextRequest, "supportedRevisions"):
                revisions = Vision.VNRecognizeTextRequest.supportedRevisions()
                if revisions:
                    request.setRevision_(max(revisions))

            # Create request handler
            # Note: Orientation should be correct by default for screenshots
            # Incorrect orientation can lower confidence scores
            handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(
                cg_image, {}
            )

            # Perform OCR (pass error pointer to get actual errors)
            error_ptr = None
            success = handler.performRequests_error_([request], error_ptr)

            if not success:
                return OCRResult(
                    success=False,
                    words=[],
                    full_text="",
                    provider="vision",
                    error="Vision request failed to execute",
                )

            # Parse results
            words: List[OCRWord] = []
            full_text_lines: List[str] = []

            observations = request.results()
            if not observations:
                # No text found - this might be because:
                # 1. Image has no text
                # 2. Text is too small/blurry
                # 3. Recognition level too strict
                # Return empty result (not an error)
                return OCRResult(
                    success=True, words=[], full_text="", provider="vision"
                )

            img_width, img_height = image.size

            for observation in observations:
                text = observation.text()
                confidence = observation.confidence()

                # Get bounding box (normalized 0.0-1.0)
                bbox_norm = observation.boundingBox()

                # Convert to pixel coordinates
                # Note: Vision uses bottom-left origin, need to flip Y
                x = int(bbox_norm.origin.x * img_width)
                y = int((1.0 - bbox_norm.origin.y - bbox_norm.size.height) * img_height)
                width = int(bbox_norm.size.width * img_width)
                height = int(bbox_norm.size.height * img_height)

                word = OCRWord(
                    text=text, confidence=confidence, bbox=(x, y, width, height)
                )
                words.append(word)
                full_text_lines.append(text)

            full_text = "\n".join(full_text_lines)

            return OCRResult(
                success=True, words=words, full_text=full_text, provider="vision"
            )

        except Exception as e:
            return OCRResult(
                success=False,
                words=[],
                full_text="",
                provider="vision",
                error=f"Vision Framework OCR failed: {str(e)}",
            )
