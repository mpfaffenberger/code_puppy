"""Tests for shimmer animation effect."""

from unittest.mock import patch

from rich.text import Text

from code_puppy.messaging.spinner.shimmer import shimmer_text


class TestShimmerText:
    """Tests for shimmer_text function."""

    def test_returns_rich_text(self):
        result = shimmer_text("hello")
        assert isinstance(result, Text)

    def test_empty_string_returns_empty_text(self):
        result = shimmer_text("")
        assert str(result) == ""

    def test_preserves_message_content(self):
        msg = "Rolling back prices..."
        result = shimmer_text(msg)
        assert str(result) == msg

    def test_accepts_all_base_colours(self):
        for colour in ("cyan", "yellow", "green", "magenta", "blue"):
            result = shimmer_text("test", base=colour)
            assert str(result) == "test"

    def test_falls_back_to_cyan_for_unknown_colour(self):
        result = shimmer_text("test", base="neon_pink")
        assert str(result) == "test"

    def test_shimmer_position_changes_over_time(self):
        """The shimmer highlight should move — styles should differ at different times."""
        msg = "A" * 30
        with patch("code_puppy.messaging.spinner.shimmer.time") as mock_time:
            mock_time.monotonic.return_value = 0.0
            r1 = shimmer_text(msg)
            mock_time.monotonic.return_value = 1.0
            r2 = shimmer_text(msg)
        # At different times the style spans should differ
        assert r1._spans != r2._spans

    def test_custom_speed_width_padding(self):
        result = shimmer_text("hi", speed=5.0, width=2, padding=4)
        assert str(result) == "hi"

    def test_raises_on_zero_speed(self):
        import pytest

        with pytest.raises(ValueError, match="speed must be > 0"):
            shimmer_text("hello", speed=0)

    def test_raises_on_negative_width(self):
        import pytest

        with pytest.raises(ValueError, match="width must be > 0"):
            shimmer_text("hello", width=-1)

    def test_raises_on_negative_padding(self):
        import pytest

        with pytest.raises(ValueError, match="padding must be >= 0"):
            shimmer_text("hello", padding=-5)
