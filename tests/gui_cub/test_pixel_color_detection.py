"""Unit tests for RGB color matching logic.

Tests the pure logic of RGB color matching strategies without mocking.
Coordinate transformation and screenshot sampling tests have been removed
as they required heavy mocking and should be integration tests instead.
"""

from code_puppy.tools.gui_cub.pixel_utils import match_rgb


class TestMatchRGB:
    """Test RGB matching strategies."""

    def test_match_exact_single_pixel(self):
        """Test exact match with single pixel."""
        samples = [(255, 0, 0)]
        assert match_rgb(samples, (255, 0, 0), tolerance=0, strategy="any")
        assert not match_rgb(samples, (255, 0, 1), tolerance=0, strategy="any")

    def test_match_with_tolerance(self):
        """Test matching with tolerance."""
        samples = [(255, 0, 0)]
        # Within tolerance
        assert match_rgb(samples, (250, 5, 5), tolerance=10, strategy="any")
        # Outside tolerance
        assert not match_rgb(samples, (200, 0, 0), tolerance=10, strategy="any")

    def test_strategy_any(self):
        """Test 'any' strategy - at least one pixel matches."""
        samples = [
            (255, 0, 0),  # Red
            (0, 255, 0),  # Green
            (0, 0, 255),  # Blue
        ]
        # Should match because at least one pixel is red
        assert match_rgb(samples, (255, 0, 0), tolerance=10, strategy="any")

    def test_strategy_all(self):
        """Test 'all' strategy - all pixels must match."""
        samples_all_red = [(255, 0, 0), (255, 0, 0), (255, 0, 0)]
        samples_mixed = [(255, 0, 0), (0, 255, 0), (255, 0, 0)]

        # All red should match
        assert match_rgb(samples_all_red, (255, 0, 0), tolerance=10, strategy="all")
        # Mixed should not match
        assert not match_rgb(samples_mixed, (255, 0, 0), tolerance=10, strategy="all")

    def test_strategy_majority(self):
        """Test 'majority' strategy - more than half must match."""
        # 3 red, 2 green = majority red
        samples = [
            (255, 0, 0),
            (255, 0, 0),
            (255, 0, 0),
            (0, 255, 0),
            (0, 255, 0),
        ]
        assert match_rgb(samples, (255, 0, 0), tolerance=10, strategy="majority")
        assert not match_rgb(samples, (0, 255, 0), tolerance=10, strategy="majority")

    def test_strategy_mean(self):
        """Test 'mean' strategy - average color must match."""
        # Average of (255, 0, 0) and (0, 255, 0) = (127, 127, 0)
        samples = [(255, 0, 0), (0, 255, 0)]

        # Mean should be close to (127, 127, 0)
        assert match_rgb(samples, (127, 127, 0), tolerance=10, strategy="mean")
        assert not match_rgb(samples, (255, 0, 0), tolerance=10, strategy="mean")

    def test_anti_aliasing_detection(self):
        """Test that 'mean' strategy handles anti-aliased edges."""
        # Simulate anti-aliased edge: mix of foreground and background
        samples = [
            (255, 255, 255),  # White background
            (200, 200, 200),  # Anti-aliased pixel
            (150, 150, 150),  # Anti-aliased pixel
            (100, 100, 100),  # Anti-aliased pixel
            (0, 0, 0),  # Black foreground
        ]

        # Mean should be around (141, 141, 141)
        mean_color = (141, 141, 141)
        assert match_rgb(samples, mean_color, tolerance=20, strategy="mean")
