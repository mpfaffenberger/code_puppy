"""Unit tests for scale detection APIs."""

from __future__ import annotations

import pytest

from code_puppy.tools.gui_cub.platform import get_screen_scale_factor


class TestScaleAPI:
    def test_scale_factor_is_reasonable(self):
        scale = get_screen_scale_factor()
        # Should be between 1.0 and 4.0
        assert 1.0 <= scale <= 4.0
        # Should be a multiple of 0.25 increments due to rounding
        rounded = round(scale * 4) / 4
        assert abs(scale - rounded) < 1e-6
