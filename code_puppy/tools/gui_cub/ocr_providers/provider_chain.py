"""Chain of Responsibility pattern for OCR providers with automatic fallback.

This module implements a provider chain that tries multiple OCR providers in order,
automatically falling back to the next provider if one fails.
"""

from __future__ import annotations

from typing import List

from PIL import Image

from code_puppy.messaging import emit_error, emit_info, emit_warning
from code_puppy.tools.common import generate_group_id

from .base import OCRProvider, OCRResult


class OCRProviderChain:
    """Chain of OCR providers with automatic fallback.

    Tries providers in order until one succeeds. If all fail, returns a
    failure result with aggregated error messages.

    Example:
        >>> chain = OCRProviderChain([
        ...     WinRTOCRProvider(),

        ... ])
        >>> result = chain.extract_text(screenshot)
        # Uses native WinRT OCR on Windows
    """

    def __init__(self, providers: List[OCRProvider]):
        """Initialize provider chain.

        Args:
            providers: List of OCR providers to try in order

        Note:
            Only available providers (is_available() == True) are included
            in the chain. Unavailable providers are filtered out.
        """
        self.providers = [p for p in providers if p.is_available()]

        if not self.providers:
            emit_warning(
                "No OCR providers available. Requires Windows 10+ or macOS 10.15+",
                message_group="ocr_init",
            )

    def extract_text(self, image: Image.Image, language: str = "en") -> OCRResult:
        """Try providers in order until one succeeds.

        Args:
            image: PIL Image to perform OCR on
            language: Language code (e.g. 'en', 'es', 'fr')

        Returns:
            OCRResult from first successful provider, or failure result
            if all providers fail
        """
        if not self.providers:
            return OCRResult(
                success=False,
                words=[],
                full_text="",
                provider="none",
                error="No OCR providers available",
            )

        errors = []
        group_id = generate_group_id("ocr_provider_chain")

        for i, provider in enumerate(self.providers):
            provider_name = provider.get_name()

            try:
                result = provider.extract_text(image, language)

                if result.success:
                    return result

                # Provider returned failure result
                error_msg = f"{provider_name}: {result.error or 'Unknown error'}"
                errors.append(error_msg)

                emit_warning(
                    f"{provider_name} failed: {result.error}", message_group=group_id
                )

            except Exception as e:
                error_msg = f"{provider_name}: {str(e)}"
                errors.append(error_msg)

                emit_error(
                    f"{provider_name} raised exception: {e}", message_group=group_id
                )

            # If this wasn't the last provider, try the next one
            if i < len(self.providers) - 1:
                next_provider = self.providers[i + 1]
                emit_info(
                    f"Falling back to {next_provider.get_name()}...",
                    message_group=group_id,
                )

        # All providers failed
        emit_error(
            f"All {len(self.providers)} OCR provider(s) failed", message_group=group_id
        )

        return OCRResult(
            success=False,
            words=[],
            full_text="",
            provider="none",
            error=f"All OCR providers failed: {'; '.join(errors)}",
        )

    def get_available_providers(self) -> List[str]:
        """Get list of available provider names.

        Returns:
            List of provider names that are available
        """
        return [p.get_name() for p in self.providers]
