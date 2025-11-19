"""OCR provider abstraction layer for GUI-Cub.

This package provides a pluggable OCR system that uses native platform APIs:
- Windows: WinRT OCR (Windows.Media.Ocr)
- macOS: Vision Framework (VNRecognizeTextRequest)

Architecture:
- OCRProvider: Abstract base class for all providers
- OCRProviderChain: Chain of responsibility pattern for automatic fallback
- Platform-specific providers: WinRTOCRProvider, VisionOCRProvider

Usage:
    >>> from code_puppy.tools.gui_cub.ocr_providers import get_ocr_provider
    >>> chain = get_ocr_provider()
    >>> result = chain.extract_text(screenshot)
    # Automatically uses best available native provider
"""

from __future__ import annotations

from code_puppy.tools.gui_cub.platform import IS_MACOS, IS_WINDOWS

from .base import OCRProvider, OCRResult, OCRWord
from .provider_chain import OCRProviderChain

# Platform-specific providers imported conditionally
if IS_WINDOWS:
    from .winrt_provider import WinRTOCRProvider

if IS_MACOS:
    from .vision_provider import VisionOCRProvider


def get_default_ocr_chain() -> OCRProviderChain:
    """Get platform-specific OCR provider chain.

    Provider priority:
    - Windows: WinRT OCR (native)
    - macOS: Vision Framework (native)

    Returns:
        OCRProviderChain configured for current platform
    """
    providers = []

    # Add native platform provider
    if IS_WINDOWS:
        providers.append(WinRTOCRProvider())
    elif IS_MACOS:
        providers.append(VisionOCRProvider())

    return OCRProviderChain(providers)


# Singleton instance for efficiency
_default_chain: OCRProviderChain | None = None


def get_ocr_provider() -> OCRProviderChain:
    """Get singleton OCR provider chain.

    Returns:
        Singleton OCRProviderChain instance
    """
    global _default_chain
    if _default_chain is None:
        _default_chain = get_default_ocr_chain()
    return _default_chain


__all__ = [
    "OCRProvider",
    "OCRResult",
    "OCRWord",
    "OCRProviderChain",
    "get_ocr_provider",
    "get_default_ocr_chain",
]
