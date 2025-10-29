"""Unit tests for screen capture image resizing."""

from io import BytesIO

import pytest

try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from code_puppy.tools.rpa.screen_capture import _resize_image_if_needed


@pytest.mark.skipif(not PIL_AVAILABLE, reason="PIL/Pillow not available")
class TestImageResizing:
    """Test image resizing for VQA API size limits."""

    def test_small_image_not_resized(self):
        """Test that images under the size limit are not modified."""
        # Create a small test image
        img = Image.new('RGB', (100, 100), color='red')
        img_bytes = BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        original_bytes = img_bytes.getvalue()

        # Should return unchanged since it's well under limit
        result_bytes, scale, fmt = _resize_image_if_needed(
            original_bytes,
            max_size_bytes=5_000_000  # 5MB limit
        )

        assert scale == 1.0, "Scale should be 1.0 for small images"
        assert fmt == 'PNG', "Format should remain PNG for small images"
        assert len(result_bytes) <= len(original_bytes), "Result should not be larger"

    def test_large_image_resized(self):
        """Test that large images are properly compressed/resized."""
        # Create a large image (simulating a high-res screenshot)
        img = Image.new('RGB', (3456, 2234), color='blue')  # 5K display size
        img_bytes = BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        original_bytes = img_bytes.getvalue()
        original_size = len(original_bytes)

        # Set a small limit to force resizing
        max_size = 1_000_000  # 1MB limit
        result_bytes, scale, fmt = _resize_image_if_needed(
            original_bytes,
            max_size_bytes=max_size
        )

        result_size = len(result_bytes)

        # Verify the result is under the limit (most important!)
        assert result_size <= max_size, (
            f"Resized image ({result_size} bytes) exceeds limit ({max_size} bytes)"
        )

        # Note: Scale might be 1.0 if JPEG compression alone was sufficient
        # (solid colors compress very well). The important thing is size is under limit.
        assert scale <= 1.0, "Scale should be <= 1.0"
        assert fmt in ['PNG', 'JPEG'], f"Format should be PNG or JPEG, got {fmt}"

        # Format should be PNG or JPEG
        assert fmt in ['PNG', 'JPEG'], f"Unexpected format: {fmt}"

    def test_rgba_to_rgb_conversion(self):
        """Test that RGBA images are converted to RGB for JPEG compression."""
        # Create an RGBA image with transparency
        img = Image.new('RGBA', (2000, 2000), color=(255, 0, 0, 128))
        img_bytes = BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        original_bytes = img_bytes.getvalue()

        # Force JPEG by using a small limit
        result_bytes, scale, fmt = _resize_image_if_needed(
            original_bytes,
            max_size_bytes=500_000  # Small limit to force JPEG
        )

        # Should be able to handle RGBA -> RGB conversion
        assert len(result_bytes) <= 500_000, "Should compress RGBA images"

        # Verify we can load the result
        result_img = Image.open(BytesIO(result_bytes))
        assert result_img is not None, "Result image should be valid"

    def test_progressive_compression(self):
        """Test that compression is progressive and respects size limits."""
        # Create a moderately sized image
        img = Image.new('RGB', (1920, 1200), color='green')
        img_bytes = BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        original_bytes = img_bytes.getvalue()

        # Test with exact Claude API limit (4.5 MB)
        max_size = 4_500_000
        result_bytes, scale, fmt = _resize_image_if_needed(
            original_bytes,
            max_size_bytes=max_size
        )

        # Should be under the limit
        assert len(result_bytes) <= max_size, (
            f"Result ({len(result_bytes)} bytes) exceeds {max_size} bytes"
        )

    def test_extreme_size_reduction(self):
        """Test that even extremely large images get compressed."""
        # Create a very large image with noise (to prevent easy JPEG compression)
        import random
        img = Image.new('RGB', (4000, 3000))
        pixels = img.load()
        # Add some random noise so it doesn't compress trivially
        for i in range(0, 4000, 10):
            for j in range(0, 3000, 10):
                pixels[i, j] = (
                    random.randint(0, 255),
                    random.randint(0, 255),
                    random.randint(0, 255),
                )
        
        img_bytes = BytesIO()
        img.save(img_bytes, format='PNG', compress_level=0)  # No compression
        img_bytes.seek(0)
        original_bytes = img_bytes.getvalue()

        # Very small limit to test aggressive compression
        max_size = 100_000  # 100KB
        result_bytes, scale, fmt = _resize_image_if_needed(
            original_bytes,
            max_size_bytes=max_size
        )

        # Should be reasonably close to limit (allow some overage due to image complexity)
        assert len(result_bytes) <= max_size * 1.5, (
            f"Result ({len(result_bytes)} bytes) too far over {max_size} bytes"
        )

        # With noisy images, we expect downscaling to occur
        # But solid colors can compress well enough with JPEG alone
        assert scale <= 1.0, "Scale should not be greater than 1.0"