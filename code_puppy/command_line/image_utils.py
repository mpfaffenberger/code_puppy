"""Shared image normalization utilities for clipboard and file attachments.

Provides PIL-based image verification, decompression-bomb protection, and
size-based downscaling.  Both ``clipboard.py`` and ``attachments.py`` import
from here so that the resize policy lives in exactly one place.

All public functions fail gracefully — if PIL is unavailable, or the bytes
are not a recognisable image, the original data is returned unchanged.
"""

from __future__ import annotations

import io
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared limits — single source of truth.
# ---------------------------------------------------------------------------

#: Maximum encoded image size before a resize is triggered.
MAX_IMAGE_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB

#: Conservative cap compatible with Anthropic's many-image request limit.
MAX_IMAGE_DIMENSION: int = 2000  # px


# ---------------------------------------------------------------------------
# Optional PIL import
# ---------------------------------------------------------------------------

try:
    from PIL import Image

    _PIL_AVAILABLE = True
    # SEC-CLIP-002: Guard against decompression bombs for all image consumers.
    Image.MAX_IMAGE_PIXELS = 178_956_970
except ImportError:  # pragma: no cover
    _PIL_AVAILABLE = False
    Image = None  # type: ignore[misc, assignment]


# ---------------------------------------------------------------------------
# Internal helpers (re-exported for callers that hold a PIL Image already)
# ---------------------------------------------------------------------------


def _safe_open_image(image_bytes: bytes) -> "Optional[Image.Image]":
    """Open and verify image bytes with PIL.

    Uses a two-pass approach: ``verify()`` checks integrity without fully
    decoding the pixel data; we then re-open for actual use because
    ``verify()`` closes the internal file handle.

    Returns ``None`` on any error (corrupt data, unknown format,
    decompression bomb, PIL unavailable).
    """
    if not _PIL_AVAILABLE or Image is None:
        return None

    try:
        probe = Image.open(io.BytesIO(image_bytes))
        probe.verify()  # raises on corrupt / malicious content
        # Re-open after verify() closes the handle
        return Image.open(io.BytesIO(image_bytes))
    except Image.DecompressionBombError as exc:
        logger.warning("Rejected decompression bomb image: %s", exc)
    except Image.UnidentifiedImageError as exc:
        logger.warning("Rejected unidentified image format: %s", exc)
    except OSError as exc:
        logger.warning("Rejected potentially malicious image: %s", exc)
    except Exception as exc:  # pragma: no cover – defensive
        logger.warning("Failed to open/verify image: %s: %s", type(exc).__name__, exc)
    return None


def _resize_image_if_needed(
    image: "Image.Image",
    max_bytes: int,
) -> "Image.Image":
    """Downscale for dimension and encoded-size limits independently.

    The dimension cap applies even to highly compressible screenshots. Preserve
    aspect ratio and never upscale a short edge to satisfy a pixel floor.
    """
    if Image is None:  # pragma: no cover
        return image

    scale = min(1.0, MAX_IMAGE_DIMENSION / max(image.size))
    resized = image
    if scale < 1.0:
        resized = image.resize(
            tuple(max(1, int(edge * scale)) for edge in image.size),
            Image.Resampling.LANCZOS,
        )

    buf = io.BytesIO()
    resized.save(buf, format="PNG", optimize=True)
    current = buf.tell()
    if current > max_bytes:
        # Retain the existing approximate byte-budget policy; the dimension
        # ceiling above is unconditional, not gated on this estimate.
        scale = (max_bytes / current) ** 0.5 * 0.9
        resized = resized.resize(
            tuple(max(1, int(edge * scale)) for edge in resized.size),
            Image.Resampling.LANCZOS,
        )
    return resized


# ---------------------------------------------------------------------------
# Public entry-point used by both clipboard.py and attachments.py
# ---------------------------------------------------------------------------


def normalize_image_bytes(
    data: bytes,
    media_type: str,
    *,
    max_bytes: int = MAX_IMAGE_SIZE_BYTES,
) -> Tuple[bytes, str]:
    """Verify and resize image bytes so they fit within *max_bytes*.

    Args:
        data: Raw image bytes.
        media_type: MIME type string (e.g. ``"image/png"``).
        max_bytes: Byte budget; defaults to :data:`MAX_IMAGE_SIZE_BYTES`.

    Returns:
        A ``(bytes, media_type)`` tuple.  If a resize was performed the bytes
        are re-encoded as PNG and *media_type* is updated to ``"image/png"``.
        The original ``(data, media_type)`` pair is returned unchanged when:

        - *media_type* does not start with ``"image/"``
        - PIL is unavailable
        - the image already fits the byte and dimension limits
        - any error occurs (always fails gracefully)
    """
    if not media_type.startswith("image/"):
        return data, media_type

    if not _PIL_AVAILABLE:
        logger.debug("PIL unavailable; skipping image normalization")
        return data, media_type

    image = _safe_open_image(data)
    if image is None:
        # Corrupt or unrecognised — pass through and let the model deal with it
        return data, media_type

    # Ensure PIL can PNG-encode the mode
    if image.mode not in ("RGB", "RGBA", "L", "LA", "P"):
        image = image.convert("RGB")

    resized = _resize_image_if_needed(image, max_bytes)

    if resized is image:
        # No resize was needed; return the original bytes untouched
        return data, media_type

    buf = io.BytesIO()
    resized.save(buf, format="PNG", optimize=True)
    return buf.getvalue(), "image/png"


__all__ = [
    "MAX_IMAGE_SIZE_BYTES",
    "MAX_IMAGE_DIMENSION",
    "normalize_image_bytes",
    # Internal helpers re-exported for clipboard.py
    "_safe_open_image",
    "_resize_image_if_needed",
]
