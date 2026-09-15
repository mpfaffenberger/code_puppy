"""Comprehensive tests for clipboard image handling.

Covers ClipboardAttachmentManager, singleton pattern, image capture,
size limiting, error handling, and cross-platform detection.
"""

from unittest.mock import MagicMock, patch


class TestCaptureClipboardImageToPending:
    """Tests for capture_clipboard_image_to_pending function."""

    def test_rate_limiting_blocks_rapid_captures(self):
        """Test that rate limiting blocks rapid captures."""
        from code_puppy.command_line import clipboard

        # Reset for clean state
        original_manager = clipboard._clipboard_manager
        clipboard._clipboard_manager = None
        clipboard._last_clipboard_capture = 0.0

        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        with patch(
            "code_puppy.command_line.clipboard.get_clipboard_image",
            return_value=fake_png,
        ):
            # First capture should succeed
            result1 = clipboard.capture_clipboard_image_to_pending()
            assert result1 is not None

            # Second immediate capture should be rate limited
            result2 = clipboard.capture_clipboard_image_to_pending()
            assert result2 is None  # Rate limited

        # Restore
        clipboard._clipboard_manager = original_manager

    def test_returns_none_when_no_image(self):
        """Test that function returns None when clipboard has no image."""
        from code_puppy.command_line import clipboard

        # Reset rate limit for test
        clipboard._last_clipboard_capture = 0.0

        with patch(
            "code_puppy.command_line.clipboard.get_clipboard_image", return_value=None
        ):
            result = clipboard.capture_clipboard_image_to_pending()

        assert result is None

    def test_returns_placeholder_when_image_captured(self):
        """Test that function returns placeholder when image is captured."""
        from code_puppy.command_line import clipboard

        # Reset manager for predictable placeholder and reset rate limit
        original_manager = clipboard._clipboard_manager
        clipboard._clipboard_manager = None
        clipboard._last_clipboard_capture = 0.0

        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        with patch(
            "code_puppy.command_line.clipboard.get_clipboard_image",
            return_value=fake_png,
        ):
            result = clipboard.capture_clipboard_image_to_pending()

        assert result == "[clipboard image 1]"

        # Restore
        clipboard._clipboard_manager = original_manager


class TestClipboardAttachmentManager:
    """Tests for ClipboardAttachmentManager class."""

    def test_add_image_returns_placeholder(self):
        """Test that add_image returns a properly formatted placeholder."""
        from code_puppy.command_line.clipboard import ClipboardAttachmentManager

        manager = ClipboardAttachmentManager()
        # Create fake PNG bytes (minimal valid PNG header)
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        placeholder = manager.add_image(fake_png)

        assert placeholder == "[clipboard image 1]"

    def test_clear_pending_removes_all_images(self):
        """Test that clear_pending removes all pending images."""
        from code_puppy.command_line.clipboard import ClipboardAttachmentManager

        manager = ClipboardAttachmentManager()
        manager.add_image(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        manager.add_image(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        assert manager.get_pending_count() == 2

        manager.clear_pending()

        assert manager.get_pending_count() == 0
        assert not manager.has_pending()
        assert manager.get_pending_images() == []

    def test_get_pending_images_returns_binary_content_list(self):
        """Test that get_pending_images returns list of BinaryContent."""
        from code_puppy.command_line.clipboard import ClipboardAttachmentManager

        manager = ClipboardAttachmentManager()
        fake_png1 = b"\x89PNG\r\n\x1a\n" + b"\x01" * 100
        fake_png2 = b"\x89PNG\r\n\x1a\n" + b"\x02" * 100

        manager.add_image(fake_png1)
        manager.add_image(fake_png2)

        images = manager.get_pending_images()

        assert len(images) == 2
        # Verify they are BinaryContent objects with correct media type
        for img in images:
            assert hasattr(img, "data")
            assert hasattr(img, "media_type")
            assert img.media_type == "image/png"


class TestGetClipboardImage:
    """Tests for get_clipboard_image function."""

    def test_handles_clipboard_access_error(self):
        """Test that function handles clipboard access errors gracefully."""
        from code_puppy.command_line.clipboard import get_clipboard_image

        with (
            patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", True),
            patch("code_puppy.command_line.clipboard.sys.platform", "darwin"),
            patch("code_puppy.command_line.clipboard.ImageGrab") as mock_grab,
        ):
            mock_grab.grabclipboard.side_effect = OSError("Clipboard access denied")
            result = get_clipboard_image()

        assert result is None

    def test_returns_none_when_clipboard_contains_file_list(self):
        """Test that function returns None when clipboard has file list (not image)."""
        from code_puppy.command_line.clipboard import get_clipboard_image

        with (
            patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", True),
            patch("code_puppy.command_line.clipboard.sys.platform", "darwin"),
            patch("code_puppy.command_line.clipboard.ImageGrab") as mock_grab,
            patch("code_puppy.command_line.clipboard.Image") as mock_image_module,
        ):
            # File list instead of image
            mock_grab.grabclipboard.return_value = ["/path/to/file.txt"]
            mock_image_module.Image = MagicMock  # Not a match for list
            result = get_clipboard_image()

        assert result is None

    def test_returns_none_when_no_image_in_clipboard(self):
        """Test that function returns None when clipboard has no image."""
        from code_puppy.command_line.clipboard import get_clipboard_image

        with (
            patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", True),
            patch("code_puppy.command_line.clipboard.sys.platform", "darwin"),
            patch("code_puppy.command_line.clipboard.ImageGrab") as mock_grab,
        ):
            mock_grab.grabclipboard.return_value = None
            result = get_clipboard_image()

        assert result is None

    def test_returns_none_when_pil_unavailable(self):
        """Test that function returns None when PIL is not available."""
        with (
            patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", False),
            patch("code_puppy.command_line.clipboard.sys.platform", "darwin"),
        ):
            from code_puppy.command_line.clipboard import get_clipboard_image

            result = get_clipboard_image()

        assert result is None

    def test_returns_png_bytes_when_image_captured(self):
        """Test that function returns PNG bytes when image is captured."""
        from code_puppy.command_line.clipboard import get_clipboard_image

        # Create a mock image that saves as PNG
        mock_image = MagicMock()
        mock_image.mode = "RGB"
        mock_image.width = 100
        mock_image.height = 100
        mock_image.info = {}

        def save_as_png(buffer, format, **kwargs):
            buffer.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

        mock_image.save.side_effect = save_as_png

        with (
            patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", True),
            patch("code_puppy.command_line.clipboard.sys.platform", "darwin"),
            patch("code_puppy.command_line.clipboard.ImageGrab") as mock_grab,
            patch("code_puppy.command_line.clipboard.Image") as mock_image_module,
        ):
            mock_image_module.Image = type(mock_image)
            mock_grab.grabclipboard.return_value = mock_image
            result = get_clipboard_image()

        assert result is not None
        assert result.startswith(b"\x89PNG")


class TestGetClipboardImageAsBinaryContent:
    """Tests for get_clipboard_image_as_binary_content function."""

    def test_returns_binary_content_when_image_available(self):
        """Test that function returns BinaryContent when image is available."""
        from code_puppy.command_line.clipboard import (
            get_clipboard_image_as_binary_content,
        )

        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        with patch(
            "code_puppy.command_line.clipboard.get_clipboard_image",
            return_value=fake_png,
        ):
            result = get_clipboard_image_as_binary_content()

        assert result is not None
        assert result.data == fake_png
        assert result.media_type == "image/png"

    def test_returns_none_when_binary_content_unavailable(self):
        """Test that function returns None when BinaryContent not importable."""
        with patch("code_puppy.command_line.clipboard.BINARY_CONTENT_AVAILABLE", False):
            from code_puppy.command_line.clipboard import (
                get_clipboard_image_as_binary_content,
            )

            result = get_clipboard_image_as_binary_content()

        assert result is None

    def test_returns_none_when_no_image(self):
        """Test that function returns None when no image available."""
        from code_puppy.command_line.clipboard import (
            get_clipboard_image_as_binary_content,
        )

        with patch(
            "code_puppy.command_line.clipboard.get_clipboard_image", return_value=None
        ):
            result = get_clipboard_image_as_binary_content()

        assert result is None


class TestGetClipboardImageLinux:
    """Tests for get_clipboard_image on Linux."""

    def test_linux_large_image_pil_unavailable(self):
        from code_puppy.command_line.clipboard import (
            MAX_IMAGE_SIZE_BYTES,
            get_clipboard_image,
        )

        large_bytes = b"x" * (MAX_IMAGE_SIZE_BYTES + 1)
        with (
            patch("code_puppy.command_line.clipboard.sys.platform", "linux"),
            patch(
                "code_puppy.command_line.clipboard._get_linux_clipboard_image",
                return_value=large_bytes,
            ),
            patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", False),
        ):
            assert get_clipboard_image() is None

    def test_linux_large_image_resize_exception(self):
        from code_puppy.command_line.clipboard import (
            MAX_IMAGE_SIZE_BYTES,
            get_clipboard_image,
        )

        large_bytes = b"x" * (MAX_IMAGE_SIZE_BYTES + 1)
        mock_img = MagicMock()

        with (
            patch("code_puppy.command_line.clipboard.sys.platform", "linux"),
            patch(
                "code_puppy.command_line.clipboard._get_linux_clipboard_image",
                return_value=large_bytes,
            ),
            patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", True),
            patch(
                "code_puppy.command_line.clipboard._safe_open_image",
                return_value=mock_img,
            ),
            patch(
                "code_puppy.command_line.clipboard._resize_image_if_needed",
                side_effect=RuntimeError("resize fail"),
            ),
        ):
            assert get_clipboard_image() is None

    def test_linux_large_image_resize_success(self):
        from code_puppy.command_line.clipboard import (
            MAX_IMAGE_SIZE_BYTES,
            get_clipboard_image,
        )

        large_bytes = b"x" * (MAX_IMAGE_SIZE_BYTES + 1)
        mock_img = MagicMock()
        resized_img = MagicMock()

        def save_side_effect(buffer, **kwargs):
            buffer.write(b"resized_png")

        resized_img.save.side_effect = save_side_effect

        with (
            patch("code_puppy.command_line.clipboard.sys.platform", "linux"),
            patch(
                "code_puppy.command_line.clipboard._get_linux_clipboard_image",
                return_value=large_bytes,
            ),
            patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", True),
            patch(
                "code_puppy.command_line.clipboard._safe_open_image",
                return_value=mock_img,
            ),
            patch(
                "code_puppy.command_line.clipboard._resize_image_if_needed",
                return_value=resized_img,
            ),
        ):
            result = get_clipboard_image()
        assert result == b"resized_png"

    def test_linux_large_image_verification_fails(self):
        from code_puppy.command_line.clipboard import (
            MAX_IMAGE_SIZE_BYTES,
            get_clipboard_image,
        )

        large_bytes = b"x" * (MAX_IMAGE_SIZE_BYTES + 1)
        with (
            patch("code_puppy.command_line.clipboard.sys.platform", "linux"),
            patch(
                "code_puppy.command_line.clipboard._get_linux_clipboard_image",
                return_value=large_bytes,
            ),
            patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", True),
            patch(
                "code_puppy.command_line.clipboard._safe_open_image", return_value=None
            ),
        ):
            assert get_clipboard_image() is None

    def test_linux_returns_none_when_no_image(self):
        from code_puppy.command_line.clipboard import get_clipboard_image

        with (
            patch("code_puppy.command_line.clipboard.sys.platform", "linux"),
            patch(
                "code_puppy.command_line.clipboard._get_linux_clipboard_image",
                return_value=None,
            ),
        ):
            assert get_clipboard_image() is None

    def test_linux_small_image_pil_available_verified(self):
        from code_puppy.command_line.clipboard import get_clipboard_image

        small_bytes = b"pngdata" * 10
        mock_img = MagicMock()
        with (
            patch("code_puppy.command_line.clipboard.sys.platform", "linux"),
            patch(
                "code_puppy.command_line.clipboard._get_linux_clipboard_image",
                return_value=small_bytes,
            ),
            patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", True),
            patch(
                "code_puppy.command_line.clipboard._safe_open_image",
                return_value=mock_img,
            ),
        ):
            result = get_clipboard_image()
        assert result == small_bytes

    def test_linux_small_image_verification_fails(self):
        from code_puppy.command_line.clipboard import get_clipboard_image

        small_bytes = b"pngdata" * 10
        with (
            patch("code_puppy.command_line.clipboard.sys.platform", "linux"),
            patch(
                "code_puppy.command_line.clipboard._get_linux_clipboard_image",
                return_value=small_bytes,
            ),
            patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", True),
            patch(
                "code_puppy.command_line.clipboard._safe_open_image", return_value=None
            ),
        ):
            assert get_clipboard_image() is None


class TestGetClipboardImageModes:
    """Tests for image mode handling in get_clipboard_image."""

    def _make_mock_image(self, mode, has_transparency=False):
        mock_image = MagicMock()
        mock_image.mode = mode
        mock_image.width = 100
        mock_image.height = 100
        mock_image.info = {"transparency": True} if has_transparency else {}

        def save_as_png(buffer, format, **kwargs):
            buffer.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

        mock_image.save.side_effect = save_as_png
        return mock_image

    def test_l_mode_converted_to_rgb(self):
        from code_puppy.command_line.clipboard import get_clipboard_image

        mock_image = self._make_mock_image("L")
        converted = self._make_mock_image("RGB")
        mock_image.convert.return_value = converted

        with (
            patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", True),
            patch("code_puppy.command_line.clipboard.sys.platform", "darwin"),
            patch("code_puppy.command_line.clipboard.ImageGrab") as mock_grab,
            patch("code_puppy.command_line.clipboard.Image") as mock_img_mod,
            patch(
                "code_puppy.command_line.clipboard._resize_image_if_needed",
                return_value=converted,
            ),
        ):
            mock_img_mod.Image = type(mock_image)
            mock_grab.grabclipboard.return_value = mock_image
            result = get_clipboard_image()
        assert result is not None
        mock_image.convert.assert_called_once_with("RGB")

    def test_rgba_mode_kept(self):
        from code_puppy.command_line.clipboard import get_clipboard_image

        mock_image = self._make_mock_image("RGBA")
        with (
            patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", True),
            patch("code_puppy.command_line.clipboard.sys.platform", "darwin"),
            patch("code_puppy.command_line.clipboard.ImageGrab") as mock_grab,
            patch("code_puppy.command_line.clipboard.Image") as mock_img_mod,
            patch(
                "code_puppy.command_line.clipboard._resize_image_if_needed",
                return_value=mock_image,
            ),
        ):
            mock_img_mod.Image = type(mock_image)
            mock_grab.grabclipboard.return_value = mock_image
            result = get_clipboard_image()
        assert result is not None
        mock_image.convert.assert_not_called()


class TestGetClipboardManager:
    """Tests for singleton clipboard manager."""

    def test_returns_same_instance(self):
        """Test that get_clipboard_manager returns the same instance."""
        from code_puppy.command_line.clipboard import get_clipboard_manager

        manager1 = get_clipboard_manager()
        manager2 = get_clipboard_manager()

        assert manager1 is manager2
