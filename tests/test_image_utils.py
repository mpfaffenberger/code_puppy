"""Unit tests for code_puppy.command_line.image_utils."""

from __future__ import annotations

import io
from unittest.mock import patch

import pytest

from code_puppy.command_line.image_utils import (
    MAX_IMAGE_DIMENSION,
    MAX_IMAGE_SIZE_BYTES,
    _resize_image_if_needed,
    _safe_open_image,
    normalize_image_bytes,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
# _resize_image_if_needed
# ---------------------------------------------------------------------------


class TestResizeImageIfNeeded:
    def test_small_image_returns_same_object(self) -> None:
        try:
            from PIL import Image
        except ImportError:  # pragma: no cover
            pytest.skip("PIL not available")

        img = Image.new("RGB", (10, 10))
        result = _resize_image_if_needed(img, MAX_IMAGE_SIZE_BYTES)
        # Must be the exact same object — no resize occurred
        assert result is img

    def test_large_image_returns_smaller_image(self) -> None:
        try:
            from PIL import Image
        except ImportError:  # pragma: no cover
            pytest.skip("PIL not available")

        img = Image.new("RGB", (500, 500))
        # Force resize by using a tiny byte budget
        result = _resize_image_if_needed(img, 50)
        assert result is not img
        assert result.width < 500
        assert result.height < 500

    def test_dimensions_floored_at_100(self) -> None:
        """Even a huge budget-to-size ratio should not drop below 100 px."""
        try:
            from PIL import Image
        except ImportError:  # pragma: no cover
            pytest.skip("PIL not available")

        img = Image.new("RGB", (200, 200))
        result = _resize_image_if_needed(img, 1)
        assert result.width >= 100
        assert result.height >= 100

    def test_dimensions_capped_at_max(self) -> None:
        """Resizing a huge image should not exceed MAX_IMAGE_DIMENSION."""
        try:
            from PIL import Image
        except ImportError:  # pragma: no cover
            pytest.skip("PIL not available")

        # Create a very wide image
        img = Image.new("RGB", (10000, 10000))
        # Passing a very large budget means no resize needed — we want to test
        # the cap, so use a moderately large image and simulate via direct call.
        # Instead, test that a resized result respects the cap.
        result = _resize_image_if_needed(img, 100)
        assert result.width <= MAX_IMAGE_DIMENSION
        assert result.height <= MAX_IMAGE_DIMENSION


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

    def test_large_image_resized(self) -> None:
        """Images over the budget are resized and re-encoded as PNG."""
        png = _make_png_bytes(300, 300)
        # Tiny budget to guarantee a resize
        out, mt = normalize_image_bytes(png, "image/jpeg", max_bytes=50)
        assert mt == "image/png"
        assert out != png
        # Verify the output is a valid, smaller PNG
        from PIL import Image

        img = Image.open(io.BytesIO(out))
        assert img.width < 300

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

    def test_jpeg_mime_type_preserved_when_no_resize(self) -> None:
        """MIME type must be left alone when no resize was needed."""
        png = _make_png_bytes(5, 5)
        # Generous budget — no resize should happen
        out, mt = normalize_image_bytes(png, "image/jpeg", max_bytes=MAX_IMAGE_SIZE_BYTES)
        assert mt == "image/jpeg"
        assert out == png

    def test_rgba_image_handled(self) -> None:
        """RGBA (transparency) images should not crash normalization."""
        try:
            from PIL import Image
        except ImportError:  # pragma: no cover
            pytest.skip("PIL not available")

        img = Image.new("RGBA", (20, 20), color=(0, 128, 255, 200))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png = buf.getvalue()

        out, mt = normalize_image_bytes(png, "image/png", max_bytes=50)
        assert mt == "image/png"
        # Verify it's still a valid image
        result = Image.open(io.BytesIO(out))
        assert result.width > 0
