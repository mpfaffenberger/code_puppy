"""Linux clipboard image + resize tests (split from test_clipboard.py)."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest


class TestGetLinuxClipboardImage:
    """Tests for _get_linux_clipboard_image."""

    def test_generic_exception(self):
        from code_puppy.command_line.clipboard import _get_linux_clipboard_image

        with (
            patch(
                "code_puppy.command_line.clipboard._check_linux_clipboard_tool",
                return_value="xclip",
            ),
            patch("subprocess.run", side_effect=RuntimeError("oops")),
        ):
            assert _get_linux_clipboard_image() is None

    def test_returns_none_when_no_tool(self):
        from code_puppy.command_line.clipboard import _get_linux_clipboard_image

        with patch(
            "code_puppy.command_line.clipboard._check_linux_clipboard_tool",
            return_value=None,
        ):
            assert _get_linux_clipboard_image() is None

    def test_timeout_expired(self):
        from code_puppy.command_line.clipboard import _get_linux_clipboard_image

        with (
            patch(
                "code_puppy.command_line.clipboard._check_linux_clipboard_tool",
                return_value="wl-paste",
            ),
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 10)),
        ):
            assert _get_linux_clipboard_image() is None

    def test_wl_paste_success(self):
        from code_puppy.command_line.clipboard import _get_linux_clipboard_image

        mock_result = MagicMock(returncode=0, stdout=b"pngdata")
        with (
            patch(
                "code_puppy.command_line.clipboard._check_linux_clipboard_tool",
                return_value="wl-paste",
            ),
            patch("subprocess.run", return_value=mock_result),
        ):
            assert _get_linux_clipboard_image() == b"pngdata"

    def test_xclip_success(self):
        from code_puppy.command_line.clipboard import _get_linux_clipboard_image

        mock_result = MagicMock(returncode=0, stdout=b"pngdata")
        with (
            patch(
                "code_puppy.command_line.clipboard._check_linux_clipboard_tool",
                return_value="xclip",
            ),
            patch("subprocess.run", return_value=mock_result),
        ):
            assert _get_linux_clipboard_image() == b"pngdata"


class TestGetPendingImagesNoBinaryContent:
    """Test get_pending_images when BinaryContent unavailable."""

    def test_returns_empty_list(self):
        from code_puppy.command_line.clipboard import ClipboardAttachmentManager

        manager = ClipboardAttachmentManager()
        manager.add_image(b"data")

        with patch("code_puppy.command_line.clipboard.BINARY_CONTENT_AVAILABLE", False):
            assert manager.get_pending_images() == []


class TestHasImageInClipboard:
    """Tests for has_image_in_clipboard function."""

    def test_returns_bool(self):
        """Test that function always returns a boolean."""
        from code_puppy.command_line.clipboard import has_image_in_clipboard

        # Mock to prevent actual clipboard access
        with (
            patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", True),
            patch("code_puppy.command_line.clipboard.ImageGrab") as mock_grab,
        ):
            mock_grab.grabclipboard.return_value = None
            result = has_image_in_clipboard()

        assert isinstance(result, bool)

    def test_returns_false_on_clipboard_error(self):
        """Test that function returns False on clipboard access error."""
        from code_puppy.command_line.clipboard import has_image_in_clipboard

        with (
            patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", True),
            patch("code_puppy.command_line.clipboard.sys.platform", "darwin"),
            patch("code_puppy.command_line.clipboard.ImageGrab") as mock_grab,
        ):
            mock_grab.grabclipboard.side_effect = Exception("Clipboard error")
            result = has_image_in_clipboard()

        assert result is False

    def test_returns_false_when_pil_unavailable_non_linux(self):
        """Test that function returns False when PIL is not available."""
        with (
            patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", False),
            patch("code_puppy.command_line.clipboard.sys.platform", "darwin"),
        ):
            from code_puppy.command_line.clipboard import has_image_in_clipboard

            result = has_image_in_clipboard()

        assert result is False


class TestHasImageLinuxEdgeCases:
    """Tests for has_image_in_clipboard Linux edge cases."""

    def test_linux_no_tool_returns_false(self):
        from code_puppy.command_line.clipboard import has_image_in_clipboard

        with (
            patch("code_puppy.command_line.clipboard.sys.platform", "linux"),
            patch(
                "code_puppy.command_line.clipboard._check_linux_clipboard_tool",
                return_value=None,
            ),
        ):
            assert has_image_in_clipboard() is False

    def test_linux_timeout_returns_false(self):
        from code_puppy.command_line.clipboard import has_image_in_clipboard

        with (
            patch("code_puppy.command_line.clipboard.sys.platform", "linux"),
            patch(
                "code_puppy.command_line.clipboard._check_linux_clipboard_tool",
                return_value="wl-paste",
            ),
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 5)),
        ):
            assert has_image_in_clipboard() is False

    def test_linux_unknown_tool_returns_false(self):
        """Test fallthrough return False for unknown tool type."""
        from code_puppy.command_line.clipboard import has_image_in_clipboard

        with (
            patch("code_puppy.command_line.clipboard.sys.platform", "linux"),
            patch(
                "code_puppy.command_line.clipboard._check_linux_clipboard_tool",
                return_value="unknown-tool",
            ),
        ):
            assert has_image_in_clipboard() is False

    def test_linux_xclip_has_image(self):
        from code_puppy.command_line.clipboard import has_image_in_clipboard

        mock_result = MagicMock(stdout="image/png\ntext/plain", returncode=0)
        with (
            patch("code_puppy.command_line.clipboard.sys.platform", "linux"),
            patch(
                "code_puppy.command_line.clipboard._check_linux_clipboard_tool",
                return_value="xclip",
            ),
            patch("subprocess.run", return_value=mock_result),
        ):
            assert has_image_in_clipboard() is True


class TestImageResizing:
    """Tests for image resizing functionality."""

    @pytest.mark.parametrize(
        "width, height",
        [
            (5000, 5000),  # large square image triggers resize
            (1000, 10000),  # height over budget
            (10000, 1000),  # width over budget
        ],
    )
    def test_large_image_triggers_resize(self, width, height):
        """Test that large images trigger resize."""
        from code_puppy.command_line.clipboard import _resize_image_if_needed

        mock_image = MagicMock()
        mock_image.width = width
        mock_image.height = height

        call_count = [0]

        def save_side_effect(buffer, **kwargs):
            # First save: simulate large image (20MB); then resized (5MB).
            if call_count[0] == 0:
                buffer.write(b"\x00" * (20 * 1024 * 1024))
            else:
                buffer.write(b"\x00" * (5 * 1024 * 1024))
            call_count[0] += 1

        mock_image.save.side_effect = save_side_effect
        resized_mock = MagicMock()
        mock_image.resize.return_value = resized_mock

        with patch("code_puppy.command_line.clipboard.Image") as mock_image_module:
            mock_image_module.Image = type(mock_image)
            mock_image_module.Resampling.LANCZOS = "lanczos"
            result = _resize_image_if_needed(mock_image, 10 * 1024 * 1024)  # 10MB limit

        assert mock_image.resize.called
        assert result is resized_mock


class TestLinuxClipboardSupport:
    """Tests for Linux clipboard support via xclip/wl-paste."""

    @pytest.mark.parametrize(
        "wl_runs, xclip_runs, expected",
        [
            (0, None, "wl-paste"),  # wl-paste probe succeeds
            (None, 0, "xclip"),  # wl-paste missing, xclip succeeds
            (None, None, None),  # neither tool available
        ],
    )
    def test_check_linux_clipboard_tool(self, wl_runs, xclip_runs, expected):
        """Test Linux clipboard tool detection (wl-paste, then xclip, then none)."""
        from code_puppy.command_line.clipboard import _check_linux_clipboard_tool

        def run_side_effect(cmd, **kwargs):
            if cmd[0] == "wl-paste":
                if wl_runs is None:
                    raise FileNotFoundError()
                return MagicMock(returncode=wl_runs)
            if xclip_runs is None:
                raise FileNotFoundError()
            return MagicMock(returncode=xclip_runs)

        with patch("subprocess.run", side_effect=run_side_effect):
            assert _check_linux_clipboard_tool() == expected

    def test_has_image_on_linux_checks_mime_types(self):
        """Test that Linux image detection checks MIME types."""
        from code_puppy.command_line.clipboard import has_image_in_clipboard

        mock_result = MagicMock()
        mock_result.stdout = "image/png\ntext/plain"
        mock_result.returncode = 0

        with (
            patch("code_puppy.command_line.clipboard.sys.platform", "linux"),
            patch(
                "code_puppy.command_line.clipboard._check_linux_clipboard_tool",
                return_value="wl-paste",
            ),
            patch("subprocess.run", return_value=mock_result),
        ):
            result = has_image_in_clipboard()

        assert result is True


class TestSecurityFeatures:
    """Tests for security features (SEC-CLIP-001 through SEC-CLIP-004)."""

    def test_add_image_raises_when_limit_exceeded(self):
        """Test SEC-CLIP-001: ValueError raised when limit exceeded."""
        import pytest

        from code_puppy.command_line.clipboard import (
            MAX_PENDING_IMAGES,
            ClipboardAttachmentManager,
        )

        manager = ClipboardAttachmentManager()
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        # Fill up to the limit
        for i in range(MAX_PENDING_IMAGES):
            manager.add_image(fake_png)

        # Next add should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            manager.add_image(fake_png)

        assert "Maximum of" in str(exc_info.value)
        assert str(MAX_PENDING_IMAGES) in str(exc_info.value)
