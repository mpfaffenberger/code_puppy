"""Shared image normalization utilities for clipboard and file attachments.

Provides PIL-based image verification, decompression-bomb protection, and
size-based downscaling.  Both ``clipboard.py`` and ``attachments.py`` import
from here so that the resize policy lives in exactly one place.

The budget is expressed in **base64 payload bytes**, because that is the unit
the Anthropic Messages API enforces (10 MiB of base64 per image).  Comparing
raw bytes against the API limit is wrong by a factor of 4/3, and re-encoding a
JPEG as lossless PNG can inflate a photo by an order of magnitude — so we
measure the bytes we would actually send, and keep the source format.

Separately from the API's hard limit, attachments are normalized to the
``image_attachment_max_kb`` setting — 1 MiB encoded by default — because
images are replayed as part of the conversation history on every request, so a
multi-megabyte photo is a per-turn upload tax the model largely throws away.

Public functions fail gracefully (returning the input unchanged) unless the
image cannot be made to fit at all, in which case :class:`ImageTooLargeError`
is raised so callers can surface a clear message instead of sending a request
that is certain to fail.
"""

from __future__ import annotations

import io
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared limits — single source of truth.
# ---------------------------------------------------------------------------

#: API's hard cap on a base64-encoded image payload (Anthropic: 10 MiB).
#: Leave headroom so other JSON fields can't push the request over the edge.
MAX_IMAGE_B64_BYTES: int = 10 * 1024 * 1024 - 64 * 1024

#: Fallback target for attachments: keep uploads (and history replays) light.
#: This is *encoded* bytes — what `ls -l` reports — not base64. Overridden at
#: runtime by the ``image_attachment_max_kb`` config key (see
#: :func:`default_image_b64_budget`).
TARGET_IMAGE_ATTACHMENT_BYTES: int = 1024 * 1024

#: Hard cap on either dimension after any resize.
MAX_IMAGE_DIMENSION: int = 4096

#: Quality used when (re-)encoding photographic content as JPEG.
JPEG_QUALITY: int = 85

#: How many downscale/encode/measure rounds we allow before giving up.
MAX_RESIZE_ATTEMPTS: int = 8

#: Smallest edge we will downscale to before deciding the image cannot fit.
MIN_DIMENSION: int = 64

_PNG_MODES = ("RGB", "RGBA", "L", "LA", "P")


class ImageTooLargeError(ValueError):
    """Raised when an image cannot be encoded small enough for the API.

    Callers are expected to catch this and tell the user to downscale the
    image, rather than shipping a request that will be rejected with an
    opaque HTTP 400.
    """


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


def b64_len(num_bytes: int) -> int:
    """Return the length of the base64 encoding of *num_bytes* bytes."""
    return 4 * ((num_bytes + 2) // 3)


def default_image_b64_budget() -> int:
    """Return the attachment budget in the API's base64 unit.

    Derived from the user's ``image_attachment_max_kb`` setting (1 MiB by
    default), clamped to the API's hard ceiling. Resolved per call rather than
    frozen at import so ``/set image_attachment_max_kb`` takes effect on the
    next attachment without a restart.
    """
    from code_puppy.config import get_image_attachment_max_kb

    target_bytes = get_image_attachment_max_kb() * 1024
    return min(MAX_IMAGE_B64_BYTES, b64_len(target_bytes))


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


def _has_alpha(image: "Image.Image") -> bool:
    """Return True when *image* carries transparency we must preserve."""
    if image.mode in ("RGBA", "LA"):
        return True
    return image.mode == "P" and "transparency" in image.info


def _flatten_to_rgb(image: "Image.Image") -> "Image.Image":
    """Composite *image* onto white so it can be encoded as JPEG."""
    if not _has_alpha(image):
        return image.convert("RGB")
    rgba = image.convert("RGBA")
    background = Image.new("RGB", rgba.size, (255, 255, 255))
    background.paste(rgba, mask=rgba.split()[-1])
    return background


def _preferred_format(image: "Image.Image", media_type: str) -> Tuple[str, str]:
    """Pick an encoding that keeps the source's character.

    Transparency and PNG sources stay PNG (lossless, and PNG is usually the
    right call for screenshots).  Everything else becomes JPEG, which is what
    photographic content was almost certainly encoded as to begin with.
    """
    if _has_alpha(image) or media_type == "image/png":
        return "PNG", "image/png"
    return "JPEG", "image/jpeg"


def _encode_image(image: "Image.Image", fmt: str) -> bytes:
    """Encode *image* as *fmt*, coercing the mode when required."""
    buf = io.BytesIO()
    if fmt == "JPEG":
        _flatten_to_rgb(image).save(
            buf, format="JPEG", quality=JPEG_QUALITY, optimize=True
        )
    else:
        target = image if image.mode in _PNG_MODES else image.convert("RGB")
        target.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _fit_image(image: "Image.Image", fmt: str, max_b64_bytes: int) -> bytes:
    """Downscale/encode in a bounded loop until the payload fits.

    Always resizes from the *original* image using a cumulative scale factor,
    so we never compound resampling artefacts.  Raises
    :class:`ImageTooLargeError` if the budget cannot be met.

    Returns the encoded bytes (never the input PIL image), because the caller
    needs to measure exactly what will go over the wire.
    """
    width, height = image.size
    # Honour the dimension cap even when the byte budget is generous.
    factor = min(1.0, MAX_IMAGE_DIMENSION / max(width, height))

    encoded = b""
    for _ in range(MAX_RESIZE_ATTEMPTS):
        if factor >= 1.0:
            candidate = image
        else:
            candidate = image.resize(
                (max(1, int(width * factor)), max(1, int(height * factor))),
                Image.Resampling.LANCZOS,
            )

        encoded = _encode_image(candidate, fmt)
        encoded_b64 = b64_len(len(encoded))
        if encoded_b64 <= max_b64_bytes:
            return encoded
        if max(width, height) * factor <= MIN_DIMENSION:
            break
        # Area scales with the square of the linear factor; 0.95 adds headroom
        # and 0.85 caps each step so progress is guaranteed.
        ratio = (max_b64_bytes / encoded_b64) ** 0.5 * 0.95
        factor *= min(ratio, 0.85)

    raise ImageTooLargeError(
        f"Image cannot be encoded under {max_b64_bytes} base64 bytes; "
        "downscale it and try again."
    )


# ---------------------------------------------------------------------------
# Public entry-point used by both clipboard.py and attachments.py
# ---------------------------------------------------------------------------


def normalize_image_bytes(
    data: bytes,
    media_type: str,
    *,
    max_bytes: Optional[int] = None,
) -> Tuple[bytes, str]:
    """Verify and shrink image bytes so the sent payload fits *max_bytes*.

    Args:
        data: Raw image bytes.
        media_type: MIME type string (e.g. ``"image/png"``).
        max_bytes: Base64 payload budget; defaults to
            :func:`default_image_b64_budget`, which keeps encoded attachments
            at or under the configured ``image_attachment_max_kb`` (1 MiB by
            default).

    Returns:
        A ``(bytes, media_type)`` tuple.  The original bytes are returned
        unchanged — byte for byte — when the image already fits, so a photo
        is never re-encoded just because its *decoded* form is large.  When a
        resize is needed the source format is preserved (PNG for transparency
        or PNG sources, JPEG otherwise) and the output is guaranteed to fit.

        The original ``(data, media_type)`` pair is returned unchanged when
        *media_type* is not an image, PIL is unavailable, or the bytes are not
        a recognisable image.

    Raises:
        ImageTooLargeError: If the image cannot be squeezed under *max_bytes*.
    """
    if not media_type.startswith("image/"):
        return data, media_type

    if not _PIL_AVAILABLE:
        logger.debug("PIL unavailable; skipping image normalization")
        return data, media_type

    if max_bytes is None:
        max_bytes = default_image_b64_budget()

    image = _safe_open_image(data)
    if image is None:
        # Corrupt or unrecognised — pass through and let the model deal with it
        return data, media_type

    if b64_len(len(data)) <= max_bytes and max(image.size) <= MAX_IMAGE_DIMENSION:
        # Nothing to do: the bytes we would send are already acceptable.
        return data, media_type

    fmt, out_media_type = _preferred_format(image, media_type)
    encoded = _fit_image(image, fmt, max_bytes)
    logger.info(
        "Re-encoded %s image (%d -> %d raw bytes) as %s",
        media_type,
        len(data),
        len(encoded),
        out_media_type,
    )
    return encoded, out_media_type


__all__ = [
    "MAX_IMAGE_B64_BYTES",
    "MAX_IMAGE_DIMENSION",
    "TARGET_IMAGE_ATTACHMENT_BYTES",
    "default_image_b64_budget",
    "JPEG_QUALITY",
    "ImageTooLargeError",
    "b64_len",
    "normalize_image_bytes",
    # Internal helpers re-exported for clipboard.py
    "_safe_open_image",
    "_encode_image",
]
