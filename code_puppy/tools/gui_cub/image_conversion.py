"""Image format conversion utilities for VQA.

This module provides utilities to normalize image formats for vision model APIs.
Different models have different supported formats, so we convert unsupported
formats to a universally accepted format (PNG) before sending to the API.

Supported formats by major vision APIs:
- Claude (Anthropic): PNG, JPEG, GIF, WebP
- GPT-4 Vision (OpenAI): PNG, JPEG, GIF, WebP
- Gemini (Google): PNG, JPEG, GIF, WebP

Formats that need conversion: BMP, TIFF, and others.
"""

from __future__ import annotations

import io


# MIME types universally accepted by vision APIs
ACCEPTED_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
}

# Default output format for conversion
DEFAULT_OUTPUT_FORMAT = "PNG"
DEFAULT_OUTPUT_MIME_TYPE = "image/png"


def normalize_image_for_vqa(
    image_bytes: bytes,
    media_type: str,
) -> tuple[bytes, str]:
    """Normalize image format for VQA model compatibility.

    If the image is already in an accepted format, returns it unchanged.
    Otherwise, converts to PNG using Pillow.

    Args:
        image_bytes: Raw image data
        media_type: MIME type of the input image (e.g., 'image/bmp')

    Returns:
        Tuple of (normalized_bytes, normalized_media_type)

    Raises:
        ValueError: If the image cannot be decoded or converted
    """
    # Already in an accepted format - return as-is
    if media_type.lower() in ACCEPTED_MIME_TYPES:
        return image_bytes, media_type

    # Need to convert - import Pillow
    try:
        from PIL import Image
    except ImportError as e:
        raise ValueError(
            f"Pillow is required to convert {media_type} images. "
            "Install with: pip install Pillow"
        ) from e

    try:
        # Load the image from bytes
        with io.BytesIO(image_bytes) as input_buffer:
            img = Image.open(input_buffer)
            # Ensure we read the full image data before the buffer closes
            img.load()

        # Convert to RGB if necessary (PNG supports RGBA, but some formats don't)
        # Keep alpha channel for formats that support it
        if img.mode in ("RGBA", "LA", "P"):
            # Keep transparency for PNG output
            if img.mode == "P":
                img = img.convert("RGBA")
        elif img.mode != "RGB":
            img = img.convert("RGB")

        # Save to PNG format
        with io.BytesIO() as output_buffer:
            img.save(output_buffer, format=DEFAULT_OUTPUT_FORMAT)
            converted_bytes = output_buffer.getvalue()

        return converted_bytes, DEFAULT_OUTPUT_MIME_TYPE

    except Exception as e:
        raise ValueError(
            f"Failed to convert image from {media_type} to PNG: {e}"
        ) from e


def get_mime_type_from_extension(extension: str) -> str:
    """Get MIME type from file extension.

    Args:
        extension: File extension (e.g., '.jpg', 'jpg', '.JPEG')

    Returns:
        MIME type string (e.g., 'image/jpeg')
    """
    # Normalize extension
    ext = extension.lower().lstrip(".")

    mime_map = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "webp": "image/webp",
        "bmp": "image/bmp",
        "tiff": "image/tiff",
        "tif": "image/tiff",
    }

    return mime_map.get(ext, "application/octet-stream")


def is_format_accepted(media_type: str) -> bool:
    """Check if a media type is accepted by vision APIs.

    Args:
        media_type: MIME type string (e.g., 'image/png')

    Returns:
        True if format is universally accepted, False if conversion needed
    """
    return media_type.lower() in ACCEPTED_MIME_TYPES
