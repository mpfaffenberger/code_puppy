"""Tests for image_tools.py filename resolution.

macOS names screenshots with U+202F (narrow no-break space) before AM/PM. That
character survives on disk but arrives as an ordinary space when the path is
copied into a prompt, so ``load_image`` has to bridge the difference without
guessing.
"""

from unittest.mock import patch

import pytest
from PIL import Image
from pydantic_ai import ToolReturn

from code_puppy.tools.image_tools import load_image


class TestLoadImagePathResolution:
    """Test Unicode-tolerant path resolution."""

    @pytest.mark.asyncio
    async def test_load_image_resolves_macos_screenshot_space(self, tmp_path):
        """A pasted normal space resolves the narrow no-break space on disk."""
        actual_path = tmp_path / "Screenshot 2026-09-04 at 9.01.58\u202fAM.png"
        image = Image.new("RGB", (32, 24), color="red")
        image.save(actual_path, format="PNG")
        requested_path = tmp_path / "Screenshot 2026-09-04 at 9.01.58 AM.png"

        with (
            patch("code_puppy.tools.image_tools.emit_info"),
            patch("code_puppy.tools.image_tools.emit_success"),
        ):
            result = await load_image(image_path=str(requested_path))

        assert isinstance(result, ToolReturn)
        assert result.metadata["image_path"] == str(actual_path)
        assert result.metadata["requested_image_path"] == str(requested_path)
        assert result.metadata["path_was_resolved"] is True

    @pytest.mark.asyncio
    async def test_load_image_prefers_exact_path(self, tmp_path):
        """An exact match is never re-resolved to a normalized sibling."""
        exact_path = tmp_path / "Screenshot AM.png"
        image = Image.new("RGB", (32, 24), color="red")
        image.save(exact_path, format="PNG")
        image.save(tmp_path / "Screenshot\u202fAM.png", format="PNG")

        with (
            patch("code_puppy.tools.image_tools.emit_info"),
            patch("code_puppy.tools.image_tools.emit_success"),
        ):
            result = await load_image(image_path=str(exact_path))

        assert isinstance(result, ToolReturn)
        assert result.metadata["image_path"] == str(exact_path)
        assert result.metadata["path_was_resolved"] is False

    @pytest.mark.asyncio
    async def test_load_image_does_not_choose_ambiguous_unicode_match(self, tmp_path):
        """Unicode fallback fails closed when multiple filenames normalize alike."""
        image = Image.new("RGB", (32, 24), color="red")
        image.save(tmp_path / "Screenshot AM.png", format="PNG")
        image.save(tmp_path / "Screenshot\u202fAM.png", format="PNG")
        requested_path = tmp_path / "Screenshot\u2009AM.png"

        with (
            patch("code_puppy.tools.image_tools.emit_info"),
            patch("code_puppy.tools.image_tools.emit_error"),
        ):
            result = await load_image(image_path=str(requested_path))

        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_load_image_missing_parent_directory(self, tmp_path):
        """A path whose parent does not exist reports not found, not a crash."""
        requested_path = tmp_path / "nope" / "Screenshot\u202fAM.png"

        with (
            patch("code_puppy.tools.image_tools.emit_info"),
            patch("code_puppy.tools.image_tools.emit_error"),
        ):
            result = await load_image(image_path=str(requested_path))

        assert result["success"] is False
        assert "not found" in result["error"]
