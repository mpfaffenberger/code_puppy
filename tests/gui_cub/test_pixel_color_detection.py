"""Unit tests for pixel color detection with HiDPI scaling fixes."""

from unittest.mock import patch

import pytest

try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from code_puppy.tools.gui_cub.pixel_utils import match_rgb, sample_neighborhood_rgb


@pytest.mark.skipif(not PIL_AVAILABLE, reason="PIL/Pillow not available")
class TestPixelColorDetection:
    """Test pixel color sampling with HiDPI scaling."""

    def create_test_image(self, width: int, height: int, color: tuple[int, int, int]):
        """Create a solid color test image."""
        img = Image.new("RGB", (width, height), color)
        return img

    def create_pattern_image(self, width: int, height: int):
        """Create a patterned test image with different regions.

        Layout:
        - Top-left quadrant: Red (255, 0, 0)
        - Top-right quadrant: Green (0, 255, 0)
        - Bottom-left quadrant: Blue (0, 0, 255)
        - Bottom-right quadrant: White (255, 255, 255)
        """
        img = Image.new("RGB", (width, height))
        pixels = img.load()

        mid_x = width // 2
        mid_y = height // 2

        for y in range(height):
            for x in range(width):
                if x < mid_x and y < mid_y:
                    pixels[x, y] = (255, 0, 0)  # Red
                elif x >= mid_x and y < mid_y:
                    pixels[x, y] = (0, 255, 0)  # Green
                elif x < mid_x and y >= mid_y:
                    pixels[x, y] = (0, 0, 255)  # Blue
                else:
                    pixels[x, y] = (255, 255, 255)  # White

        return img

    def test_sample_single_pixel_1x_display(self):
        """Test single pixel sampling on 1x (non-Retina) display."""
        # Mock both pyautogui and ImageGrab to simulate 1x display
        # (Code uses ImageGrab on macOS, pyautogui elsewhere)
        with patch("code_puppy.tools.gui_cub.pixel_utils.pyautogui") as mock_pg, \
             patch("code_puppy.tools.gui_cub.pixel_utils.ImageGrab") as mock_ig:
            # Logical size = Physical size (1x display)
            mock_pg.size.return_value = (1000, 800)

            # Create test image: solid red
            test_image = self.create_test_image(1000, 800, (255, 0, 0))
            mock_pg.screenshot.return_value = test_image
            mock_ig.grab.return_value = test_image  # Also mock ImageGrab for macOS

            # Sample at logical (500, 400) -> physical (500, 400)
            samples, center_rgb = sample_neighborhood_rgb(x=500, y=400, neighborhood=0)

            # Should get red color
            assert center_rgb == (255, 0, 0), f"Expected red, got {center_rgb}"
            assert len(samples) == 1, "Single pixel should return 1 sample"

    def test_sample_single_pixel_2x_display(self):
        """Test single pixel sampling on 2x (Retina) display.

        This is the critical test for the HiDPI bug fix!
        """
        with patch("code_puppy.tools.gui_cub.pixel_utils.pyautogui") as mock_pg, \
             patch("code_puppy.tools.gui_cub.pixel_utils.ImageGrab") as mock_ig:
            # Logical size = 1000x800, Physical size = 2000x1600 (2x Retina)
            mock_pg.size.return_value = (1000, 800)

            # Create test pattern at 2x resolution
            test_image = self.create_pattern_image(2000, 1600)
            mock_pg.screenshot.return_value = test_image
            mock_ig.grab.return_value = test_image  # Also mock ImageGrab for macOS

            # Sample at logical (250, 200) -> should map to physical (500, 400)
            # Physical (500, 400) is in top-left quadrant = RED
            samples, center_rgb = sample_neighborhood_rgb(x=250, y=200, neighborhood=0)

            assert center_rgb == (255, 0, 0), (
                f"Expected red at logical (250, 200) / physical (500, 400), "
                f"got {center_rgb}"
            )

    def test_sample_all_quadrants_2x_display(self):
        """Test sampling from all four quadrants on 2x display."""
        with patch("code_puppy.tools.gui_cub.pixel_utils.pyautogui") as mock_pg, \
             patch("code_puppy.tools.gui_cub.pixel_utils.ImageGrab") as mock_ig:
            mock_pg.size.return_value = (1000, 800)
            test_image = self.create_pattern_image(2000, 1600)
            mock_pg.screenshot.return_value = test_image
            mock_ig.grab.return_value = test_image  # Also mock ImageGrab for macOS

            # Test all four quadrants
            # Top-left (logical 250, 200) -> physical (500, 400) = RED
            _, rgb = sample_neighborhood_rgb(x=250, y=200, neighborhood=0)
            assert rgb == (255, 0, 0), f"Top-left should be red, got {rgb}"

            # Top-right (logical 750, 200) -> physical (1500, 400) = GREEN
            _, rgb = sample_neighborhood_rgb(x=750, y=200, neighborhood=0)
            assert rgb == (0, 255, 0), f"Top-right should be green, got {rgb}"

            # Bottom-left (logical 250, 600) -> physical (500, 1200) = BLUE
            _, rgb = sample_neighborhood_rgb(x=250, y=600, neighborhood=0)
            assert rgb == (0, 0, 255), f"Bottom-left should be blue, got {rgb}"

            # Bottom-right (logical 750, 600) -> physical (1500, 1200) = WHITE
            _, rgb = sample_neighborhood_rgb(x=750, y=600, neighborhood=0)
            assert rgb == (255, 255, 255), f"Bottom-right should be white, got {rgb}"

    def test_neighborhood_sampling_3x3(self):
        """Test 3x3 neighborhood sampling (neighborhood=1)."""
        with patch("code_puppy.tools.gui_cub.pixel_utils.pyautogui") as mock_pg, \
             patch("code_puppy.tools.gui_cub.pixel_utils.ImageGrab") as mock_ig:
            mock_pg.size.return_value = (100, 100)
            test_image = self.create_test_image(100, 100, (128, 128, 128))
            mock_pg.screenshot.return_value = test_image
            mock_ig.grab.return_value = test_image  # Also mock ImageGrab for macOS

            # Sample 3x3 neighborhood
            samples, center_rgb = sample_neighborhood_rgb(x=50, y=50, neighborhood=1)

            # Should get 9 samples (3x3)
            assert len(samples) == 9, f"Expected 9 samples, got {len(samples)}"
            # All should be gray
            assert all(rgb == (128, 128, 128) for rgb in samples)

    def test_neighborhood_sampling_5x5_on_2x_display(self):
        """Test 5x5 logical neighborhood sampling on 2x display.

        On a 2x display:
        - neighborhood=2 means logical radius=2 (5x5 grid in logical space)
        - Physical radius = 2 * 2 = 4
        - Physical grid = range(-4, 5) = 9 values
        - Total samples = 9x9 = 81

        This is correct! The physical neighborhood scales with the display.
        """
        with patch("code_puppy.tools.gui_cub.pixel_utils.pyautogui") as mock_pg, \
             patch("code_puppy.tools.gui_cub.pixel_utils.ImageGrab") as mock_ig:
            mock_pg.size.return_value = (100, 100)
            # 2x display
            test_image = self.create_test_image(200, 200, (64, 64, 64))
            mock_pg.screenshot.return_value = test_image
            mock_ig.grab.return_value = test_image  # Also mock ImageGrab for macOS

            # Sample 5x5 logical neighborhood (neighborhood=2)
            samples, center_rgb = sample_neighborhood_rgb(x=50, y=50, neighborhood=2)

            # On 2x display, neighborhood=2 -> physical radius=4 -> 9x9 = 81 samples
            assert len(samples) == 81, (
                f"Expected 81 samples (9x9 on 2x display), got {len(samples)}"
            )
            assert all(rgb == (64, 64, 64) for rgb in samples)
            assert center_rgb == (64, 64, 64)

    def test_edge_clamping(self):
        """Test that coordinates near edges are clamped to image bounds."""
        with patch("code_puppy.tools.gui_cub.pixel_utils.pyautogui") as mock_pg, \
             patch("code_puppy.tools.gui_cub.pixel_utils.ImageGrab") as mock_ig:
            mock_pg.size.return_value = (100, 100)
            test_image = self.create_test_image(100, 100, (200, 200, 200))
            mock_pg.screenshot.return_value = test_image
            mock_ig.grab.return_value = test_image  # Also mock ImageGrab for macOS

            # Sample near top-left corner
            samples, center_rgb = sample_neighborhood_rgb(x=0, y=0, neighborhood=1)

            # Should not crash and should return samples
            assert len(samples) > 0
            assert center_rgb == (200, 200, 200)

            # Sample near bottom-right corner
            samples, center_rgb = sample_neighborhood_rgb(x=99, y=99, neighborhood=1)
            assert len(samples) > 0
            assert center_rgb == (200, 200, 200)


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


class TestRealWorldScenarios:
    """Test realistic scenarios from term1-todo.md."""

    @pytest.mark.skipif(not PIL_AVAILABLE, reason="PIL/Pillow not available")
    def test_retina_display_bug_fix(self):
        """Reproduce and verify fix for the bug described in term1-todo.md.

        Original bug:
        - Testing at logical (1075, 473)
        - Scale incorrectly reported as 1.0x (actual: 2.0x)
        - Pixel sampled at physical (1075, 473) instead of (2150, 946)
        - Result: Desktop background RGB(64, 66, 69) instead of window color

        Fixed behavior:
        - Calculate scale from screenshot dimensions: 3456/1728 = 2.0x
        - Convert logical (1075, 473) to physical (2150, 946)
        - Sample correct pixel
        """
        with patch("code_puppy.tools.gui_cub.pixel_utils.pyautogui") as mock_pg, \
             patch("code_puppy.tools.gui_cub.pixel_utils.ImageGrab") as mock_ig:
            # Simulate term1-todo.md test environment
            # Display: 1728×1117 logical, 3456×2234 physical (2.0x Retina)
            mock_pg.size.return_value = (1728, 1117)

            # Create test image with specific pattern
            # Desktop background: RGB(64, 66, 69)
            # Window area (around 2150, 946): RGB(255, 255, 255) white
            test_image = Image.new("RGB", (3456, 2234), (64, 66, 69))
            pixels = test_image.load()

            # Paint a white region where the window should be
            # (roughly center-ish area where coordinates 2150, 946 would be)
            for y in range(800, 1200):
                for x in range(2000, 2300):
                    pixels[x, y] = (255, 255, 255)

            mock_pg.screenshot.return_value = test_image
            mock_ig.grab.return_value = test_image  # Also mock ImageGrab for macOS

            # Test the buggy scenario
            # Logical (1075, 473) should map to physical (2150, 946)
            samples, center_rgb = sample_neighborhood_rgb(x=1075, y=473, neighborhood=0)

            # Should get white (window color), NOT desktop background!
            assert center_rgb == (255, 255, 255), (
                f"Bug still present! Expected window color (255, 255, 255), "
                f"got desktop background {center_rgb}. "
                f"This means pixel scaling is still broken."
            )

    @pytest.mark.skipif(not PIL_AVAILABLE, reason="PIL/Pillow not available")
    def test_neighborhood_strategy_for_anti_aliasing(self):
        """Test that neighborhood sampling helps with anti-aliased UI elements."""
        with patch("code_puppy.tools.gui_cub.pixel_utils.pyautogui") as mock_pg, \
             patch("code_puppy.tools.gui_cub.pixel_utils.ImageGrab") as mock_ig:
            mock_pg.size.return_value = (100, 100)

            # Create image with anti-aliased edge
            test_image = Image.new("RGB", (100, 100), (255, 255, 255))  # White bg
            pixels = test_image.load()

            # Draw a black line at x=50 with anti-aliasing
            for y in range(100):
                pixels[49, y] = (180, 180, 180)  # Anti-alias
                pixels[50, y] = (0, 0, 0)  # Black line
                pixels[51, y] = (180, 180, 180)  # Anti-alias

            mock_pg.screenshot.return_value = test_image
            mock_ig.grab.return_value = test_image  # Also mock ImageGrab for macOS

            # Sample the black line with neighborhood
            samples, center_rgb = sample_neighborhood_rgb(x=50, y=50, neighborhood=1)

            # Center should be black
            assert center_rgb == (0, 0, 0)

            # Should match black using 'any' strategy (ignores anti-alias)
            assert match_rgb(samples, (0, 0, 0), tolerance=10, strategy="any")

            # Should NOT match using 'all' strategy (anti-alias pixels differ)
            assert not match_rgb(samples, (0, 0, 0), tolerance=10, strategy="all")
