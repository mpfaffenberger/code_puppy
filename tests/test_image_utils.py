"""Unit tests for code_puppy.command_line.image_utils."""

from __future__ import annotations

import base64
import io
import os
from unittest.mock import patch

import pytest

from code_puppy.command_line.image_utils import (
    DEFAULT_IMAGE_B64_BUDGET,
    MAX_IMAGE_B64_BYTES,
    MAX_IMAGE_DIMENSION,
    TARGET_IMAGE_ATTACHMENT_BYTES,
    ImageTooLargeError,
    _safe_open_image,
    b64_len,
    normalize_image_bytes,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bytes_to_image(data: bytes):
    from PIL import Image

    return Image.open(io.BytesIO(data))


def _encoded_b64_len(data: bytes) -> int:
    return len(base64.b64encode(data))


def _make_png_bytes(width: int = 20, height: int = 20, color=(255, 0, 0)) -> bytes:
    """Return bytes of a small, valid PNG image."""
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover
        pytest.skip("PIL not available")

    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_noisy_jpeg(width: int, height: int, quality: int = 85) -> bytes:
    """Return JPEG bytes whose content is noisy (i.e. resize-resistant)."""
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover
        pytest.skip("PIL not available")

    img = Image.frombytes("RGB", (width, height), os.urandom(width * height * 3))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# b64_len
# ---------------------------------------------------------------------------


class TestB64Len:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [(0, 0), (1, 4), (2, 4), (3, 4), (4, 8), (100, 136)],
    )
    def test_matches_base64_encoding(self, raw: int, expected: int) -> None:
        assert b64_len(raw) == expected == len(base64.b64encode(b"x" * raw))

    def test_default_budget_matches_attachment_target(self) -> None:
        """The default budget is the 256 KiB target in the API's unit."""
        assert DEFAULT_IMAGE_B64_BUDGET == b64_len(TARGET_IMAGE_ATTACHMENT_BYTES)
        assert DEFAULT_IMAGE_B64_BUDGET <= MAX_IMAGE_B64_BYTES


# ---------------------------------------------------------------------------
# _safe_open_image
# ---------------------------------------------------------------------------


class TestSafeOpenImage:
    def test_valid_png_returns_image(self) -> None:
        png = _make_png_bytes()
        result = _safe_open_image(png)
        assert result is not None

    def test_corrupt_bytes_returns_none(self) -> None:
        result = _safe_open_image(b"this is definitely not an image")
        assert result is None

    def test_empty_bytes_returns_none(self) -> None:
        result = _safe_open_image(b"")
        assert result is None

    def test_pil_unavailable_returns_none(self) -> None:
        import code_puppy.command_line.image_utils as iu

        with patch.object(iu, "_PIL_AVAILABLE", False):
            result = _safe_open_image(_make_png_bytes())
        assert result is None


# ---------------------------------------------------------------------------
# normalize_image_bytes
# ---------------------------------------------------------------------------


class TestNormalizeImageBytes:
    def test_non_image_media_type_passthrough(self) -> None:
        data = b"some pdf bytes"
        out, mt = normalize_image_bytes(data, "application/pdf")
        assert out is data
        assert mt == "application/pdf"

    def test_non_image_text_passthrough(self) -> None:
        data = b"hello world"
        out, mt = normalize_image_bytes(data, "text/plain")
        assert out is data
        assert mt == "text/plain"

    def test_small_image_unchanged(self) -> None:
        """Images within the limit must not be re-encoded."""
        png = _make_png_bytes(10, 10)
        out, mt = normalize_image_bytes(png, "image/png")
        assert out == png
        assert mt == "image/png"

    def test_corrupt_bytes_passthrough(self) -> None:
        """Corrupt image bytes must be returned unchanged — never crash."""
        data = b"not an image at all"
        out, mt = normalize_image_bytes(data, "image/png")
        assert out is data
        assert mt == "image/png"

    def test_pil_unavailable_passthrough(self) -> None:
        import code_puppy.command_line.image_utils as iu

        png = _make_png_bytes()
        with patch.object(iu, "_PIL_AVAILABLE", False):
            out, mt = normalize_image_bytes(png, "image/png")
        assert out is png
        assert mt == "image/png"

    def test_mime_type_preserved_when_no_resize(self) -> None:
        """MIME type must be left alone when no resize was needed."""
        png = _make_png_bytes(5, 5)
        out, mt = normalize_image_bytes(png, "image/jpeg")
        assert mt == "image/jpeg"
        assert out == png

    def test_small_jpeg_is_sent_unchanged(self) -> None:
        """A JPEG already under the target is never re-encoded."""
        jpeg = _make_noisy_jpeg(300, 200, quality=85)
        assert len(jpeg) <= TARGET_IMAGE_ATTACHMENT_BYTES

        out, mt = normalize_image_bytes(jpeg, "image/jpeg")

        assert out is jpeg
        assert mt == "image/jpeg"

    def test_photo_over_target_is_downscaled_not_inflated(self) -> None:
        """Regression for #1050: a 12 MP photo must not become a bigger PNG.

        The old code probed with a lossless PNG encoding, then resent the image
        as a *larger* PNG that the API rejected.  It now shrinks as JPEG and
        respects the attachment target.
        """
        from PIL import Image

        seed = _bytes_to_image(_make_noisy_jpeg(1008, 756))
        photo = seed.resize((4032, 3024), Image.Resampling.BICUBIC)
        buf = io.BytesIO()
        photo.save(buf, format="JPEG", quality=85)
        jpeg = buf.getvalue()
        assert len(jpeg) > TARGET_IMAGE_ATTACHMENT_BYTES

        out, mt = normalize_image_bytes(jpeg, "image/jpeg")

        assert mt == "image/jpeg"
        assert out[:2] == b"\xff\xd8"  # still JPEG, not PNG
        assert len(out) <= TARGET_IMAGE_ATTACHMENT_BYTES
        assert max(_bytes_to_image(out).size) < 4032

    def test_oversized_jpeg_stays_jpeg_and_fits(self) -> None:
        """Forced resize must keep JPEG (not balloon into PNG) and fit."""
        jpeg = _make_noisy_jpeg(1200, 900, quality=95)
        budget = 400_000
        assert _encoded_b64_len(jpeg) > budget

        out, mt = normalize_image_bytes(jpeg, "image/jpeg", max_bytes=budget)

        assert mt == "image/jpeg"
        assert out[:2] == b"\xff\xd8"  # JPEG SOI marker
        assert _encoded_b64_len(out) <= budget
        assert _bytes_to_image(out).width < 1200

    def test_transparent_png_stays_png_and_fits(self) -> None:
        """Transparency must survive normalization (and force PNG encoding)."""
        from PIL import Image

        rgba = Image.frombytes("RGBA", (600, 600), os.urandom(600 * 600 * 4))
        buf = io.BytesIO()
        rgba.save(buf, format="PNG", compress_level=1)
        png = buf.getvalue()
        budget = 500_000
        assert _encoded_b64_len(png) > budget

        out, mt = normalize_image_bytes(png, "image/png", max_bytes=budget)

        assert mt == "image/png"
        assert out[:8] == b"\x89PNG\r\n\x1a\n"
        assert _encoded_b64_len(out) <= budget
        result = _bytes_to_image(out)
        assert result.mode == "RGBA"
        assert result.width < 600

    def test_dimension_cap_enforced(self) -> None:
        """Images with tiny byte counts but huge dimensions still shrink."""
        from PIL import Image

        img = Image.new("RGB", (MAX_IMAGE_DIMENSION + 900, 100), color=(0, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png = buf.getvalue()

        out, _ = normalize_image_bytes(png, "image/png")

        assert max(_bytes_to_image(out).size) <= MAX_IMAGE_DIMENSION

    def test_unfittable_image_raises(self) -> None:
        """An impossible budget raises instead of shipping a doomed request."""
        png = _make_png_bytes(300, 300)

        with pytest.raises(ImageTooLargeError):
            normalize_image_bytes(png, "image/png", max_bytes=50)
