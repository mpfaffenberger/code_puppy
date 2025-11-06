"""Unit tests for DPI-safe pixel sampling utilities."""

from __future__ import annotations


from code_puppy.tools.gui_cub.pixel_utils import match_rgb


class TestPixelUtils:
    def test_match_rgb_any(self):
        samples = [(0, 0, 0), (10, 10, 10), (200, 200, 200)]
        assert (
            match_rgb(samples, expected=(0, 0, 0), tolerance=5, strategy="any") is True
        )
        assert (
            match_rgb(samples, expected=(0, 0, 0), tolerance=0, strategy="any") is True
        )
        assert (
            match_rgb(samples, expected=(250, 250, 250), tolerance=2, strategy="any")
            is False
        )

    def test_match_rgb_all(self):
        samples = [(0, 0, 0), (0, 0, 0), (0, 0, 0)]
        assert (
            match_rgb(samples, expected=(0, 0, 0), tolerance=0, strategy="all") is True
        )
        samples2 = [(0, 0, 0), (1, 1, 1), (0, 0, 0)]
        assert (
            match_rgb(samples2, expected=(0, 0, 0), tolerance=0, strategy="all")
            is False
        )

    def test_match_rgb_majority(self):
        samples = [(0, 0, 0), (0, 0, 0), (10, 10, 10), (255, 255, 255)]
        assert (
            match_rgb(samples, expected=(0, 0, 0), tolerance=10, strategy="majority")
            is True
        )
        assert (
            match_rgb(
                samples, expected=(255, 255, 255), tolerance=10, strategy="majority"
            )
            is False
        )

    def test_match_rgb_mean(self):
        samples = [(0, 0, 0), (10, 10, 10), (20, 20, 20)]
        # mean ~ (10,10,10) within tol 15 for expected (0,0,0)? No.
        assert (
            match_rgb(samples, expected=(0, 0, 0), tolerance=9, strategy="mean")
            is False
        )
        assert (
            match_rgb(samples, expected=(10, 10, 10), tolerance=2, strategy="mean")
            is True
        )

    def test_empty_samples(self):
        assert match_rgb([], expected=(0, 0, 0), tolerance=10, strategy="any") is False
