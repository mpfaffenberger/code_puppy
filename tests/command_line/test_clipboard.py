"""Comprehensive tests for clipboard image handling.

Covers ClipboardAttachmentManager, singleton pattern, image capture,
size limiting, error handling, and cross-platform detection.
"""

import io
import subprocess
import threading
from unittest.mock import MagicMock, patch


class TestClipboardAttachmentManager:
    """Tests for ClipboardAttachmentManager class."""

    def test_add_image_returns_placeholder(self):
        """Test that add_image returns a properly formatted placeholder."""
        from code_puppy.command_line.clipboard import ClipboardAttachmentManager

        manager = ClipboardAttachmentManager()
        # Create fake PNG bytes (minimal valid PNG header)
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        placeholder = manager.add_image(fake_png)

        assert placeholder == "[📋 clipboard image 1]"

    def test_placeholder_increments_correctly(self):
        """Test that placeholder numbers increment with each add."""
        from code_puppy.command_line.clipboard import ClipboardAttachmentManager

        manager = ClipboardAttachmentManager()
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        p1 = manager.add_image(fake_png)
        p2 = manager.add_image(fake_png)
        p3 = manager.add_image(fake_png)

        assert p1 == "[📋 clipboard image 1]"
        assert p2 == "[📋 clipboard image 2]"
        assert p3 == "[📋 clipboard image 3]"

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

    def test_get_pending_images_preserves_order(self):
        """Test that images are returned in the order they were added."""
        from code_puppy.command_line.clipboard import ClipboardAttachmentManager

        manager = ClipboardAttachmentManager()
        fake_png1 = b"\x89PNG\r\n\x1a\n" + b"\x01" * 50
        fake_png2 = b"\x89PNG\r\n\x1a\n" + b"\x02" * 50
        fake_png3 = b"\x89PNG\r\n\x1a\n" + b"\x03" * 50

        manager.add_image(fake_png1)
        manager.add_image(fake_png2)
        manager.add_image(fake_png3)

        images = manager.get_pending_images()

        assert images[0].data == fake_png1
        assert images[1].data == fake_png2
        assert images[2].data == fake_png3

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

    def test_get_pending_count_returns_correct_count(self):
        """Test that get_pending_count returns accurate count."""
        from code_puppy.command_line.clipboard import ClipboardAttachmentManager

        manager = ClipboardAttachmentManager()
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        assert manager.get_pending_count() == 0

        manager.add_image(fake_png)
        assert manager.get_pending_count() == 1

        manager.add_image(fake_png)
        assert manager.get_pending_count() == 2

        manager.clear_pending()
        assert manager.get_pending_count() == 0

    def test_has_pending_returns_correct_boolean(self):
        """Test that has_pending returns correct boolean state."""
        from code_puppy.command_line.clipboard import ClipboardAttachmentManager

        manager = ClipboardAttachmentManager()
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        assert manager.has_pending() is False

        manager.add_image(fake_png)
        assert manager.has_pending() is True

        manager.clear_pending()
        assert manager.has_pending() is False

    def test_counter_persists_after_clear(self):
        """Test that the counter continues incrementing after clear."""
        from code_puppy.command_line.clipboard import ClipboardAttachmentManager

        manager = ClipboardAttachmentManager()
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        p1 = manager.add_image(fake_png)
        assert p1 == "[📋 clipboard image 1]"

        manager.clear_pending()

        p2 = manager.add_image(fake_png)
        assert p2 == "[📋 clipboard image 2]"

    def test_manager_is_thread_safe(self):
        """Test basic thread safety of add_image and get_pending_count."""
        from code_puppy.command_line.clipboard import (
            MAX_PENDING_IMAGES,
            ClipboardAttachmentManager,
        )

        manager = ClipboardAttachmentManager()
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        num_threads = 5
        images_per_thread = 2  # Stay under MAX_PENDING_IMAGES limit

        def add_images():
            for _ in range(images_per_thread):
                try:
                    manager.add_image(fake_png)
                except ValueError:
                    pass  # Expected if limit reached

        threads = [threading.Thread(target=add_images) for _ in range(num_threads)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have added images up to the limit
        assert manager.get_pending_count() <= MAX_PENDING_IMAGES
        assert manager.get_pending_count() == num_threads * images_per_thread

    def test_manager_thread_safe_clear(self):
        """Test thread safety when clearing while adding."""
        from code_puppy.command_line.clipboard import ClipboardAttachmentManager

        manager = ClipboardAttachmentManager()
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        unexpected_errors = []

        def add_images():
            for _ in range(5):
                try:
                    manager.add_image(fake_png)
                except ValueError:
                    # Expected if limit reached - not an error
                    pass
                except Exception as e:
                    unexpected_errors.append(e)

        def clear_images():
            try:
                for _ in range(5):
                    manager.clear_pending()
            except Exception as e:
                unexpected_errors.append(e)

        threads = [
            threading.Thread(target=add_images),
            threading.Thread(target=add_images),
            threading.Thread(target=clear_images),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should complete without unexpected errors (ValueError for limit is expected)
        assert len(unexpected_errors) == 0


class TestGetClipboardManager:
    """Tests for singleton clipboard manager."""

    def test_returns_same_instance(self):
        """Test that get_clipboard_manager returns the same instance."""
        from code_puppy.command_line.clipboard import get_clipboard_manager

        manager1 = get_clipboard_manager()
        manager2 = get_clipboard_manager()

        assert manager1 is manager2

    def test_singleton_is_clipboard_attachment_manager(self):
        """Test that singleton is a ClipboardAttachmentManager instance."""
        from code_puppy.command_line.clipboard import (
            ClipboardAttachmentManager,
            get_clipboard_manager,
        )

        manager = get_clipboard_manager()

        assert isinstance(manager, ClipboardAttachmentManager)

    def test_singleton_thread_safe_creation(self):
        """Test that singleton creation is thread-safe."""
        from code_puppy.command_line import clipboard

        # Reset the singleton for this test
        original_manager = clipboard._clipboard_manager
        clipboard._clipboard_manager = None

        managers = []
        lock = threading.Lock()

        def get_manager():
            mgr = clipboard.get_clipboard_manager()
            with lock:
                managers.append(mgr)

        threads = [threading.Thread(target=get_manager) for _ in range(20)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should be the same instance
        assert all(m is managers[0] for m in managers)

        # Restore original singleton
        clipboard._clipboard_manager = original_manager


class TestCaptureClipboardImageToPending:
    """Tests for capture_clipboard_image_to_pending function."""

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

        assert result == "[📋 clipboard image 1]"

        # Restore
        clipboard._clipboard_manager = original_manager

    def test_adds_image_to_manager(self):
        """Test that captured image is added to the manager."""
        from code_puppy.command_line import clipboard

        # Reset manager for clean state and reset rate limit
        original_manager = clipboard._clipboard_manager
        clipboard._clipboard_manager = None
        clipboard._last_clipboard_capture = 0.0

        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        with patch(
            "code_puppy.command_line.clipboard.get_clipboard_image",
            return_value=fake_png,
        ):
            clipboard.capture_clipboard_image_to_pending()

        manager = clipboard.get_clipboard_manager()
        assert manager.get_pending_count() == 1

        # Restore
        clipboard._clipboard_manager = original_manager

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

    def test_returns_false_when_pil_unavailable_non_linux(self):
        """Test that function returns False when PIL is not available."""
        with (
            patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", False),
            patch("code_puppy.command_line.clipboard.sys.platform", "darwin"),
        ):
            from code_puppy.command_line.clipboard import has_image_in_clipboard

            result = has_image_in_clipboard()

        assert result is False

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

    def test_returns_true_when_image_present(self):
        """Test that function returns True when image is in clipboard."""
        from code_puppy.command_line.clipboard import has_image_in_clipboard

        mock_image = MagicMock()

        with (
            patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", True),
            patch("code_puppy.command_line.clipboard.sys.platform", "darwin"),
            patch("code_puppy.command_line.clipboard.ImageGrab") as mock_grab,
            patch("code_puppy.command_line.clipboard.Image") as mock_image_module,
        ):
            mock_image_module.Image = type(mock_image)
            mock_grab.grabclipboard.return_value = mock_image
            result = has_image_in_clipboard()

        assert result is True


class TestGetClipboardImage:
    """Tests for get_clipboard_image function."""

    def test_returns_none_when_pil_unavailable(self):
        """Test that function returns None when PIL is not available."""
        with (
            patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", False),
            patch("code_puppy.command_line.clipboard.sys.platform", "darwin"),
        ):
            from code_puppy.command_line.clipboard import get_clipboard_image

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


class TestGetClipboardImageAsBinaryContent:
    """Tests for get_clipboard_image_as_binary_content function."""

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


class TestLinuxClipboardSupport:
    """Tests for Linux clipboard support via xclip/wl-paste."""

    def test_check_linux_clipboard_tool_detects_wl_paste(self):
        """Test that wl-paste is detected when available."""
        from code_puppy.command_line.clipboard import _check_linux_clipboard_tool

        with patch("subprocess.run") as mock_run:
            # wl-paste succeeds
            mock_run.return_value = MagicMock(returncode=0)
            result = _check_linux_clipboard_tool()

        assert result == "wl-paste"

    def test_check_linux_clipboard_tool_detects_xclip(self):
        """Test that xclip is detected when wl-paste not available."""
        from code_puppy.command_line.clipboard import _check_linux_clipboard_tool

        def run_side_effect(cmd, **kwargs):
            if cmd[0] == "wl-paste":
                raise FileNotFoundError()
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=run_side_effect):
            result = _check_linux_clipboard_tool()

        assert result == "xclip"

    def test_check_linux_clipboard_tool_returns_none_when_no_tools(self):
        """Test that None is returned when no clipboard tools available."""
        from code_puppy.command_line.clipboard import _check_linux_clipboard_tool

        with patch("subprocess.run", side_effect=FileNotFoundError()):
            result = _check_linux_clipboard_tool()

        assert result is None

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

    def test_has_image_on_linux_returns_false_when_no_image_type(self):
        """Test that Linux returns False when no image MIME type."""
        from code_puppy.command_line.clipboard import has_image_in_clipboard

        mock_result = MagicMock()
        mock_result.stdout = "text/plain\napplication/json"
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

        assert result is False


class TestImageResizing:
    """Tests for image resizing functionality."""

    def test_resize_not_needed_for_small_image(self):
        """Test that small images are not resized."""
        from code_puppy.command_line.clipboard import _resize_image_if_needed

        # Create a mock small image
        mock_image = MagicMock()
        mock_image.width = 100
        mock_image.height = 100

        small_buffer = io.BytesIO()
        small_buffer.write(b"\x00" * 1000)  # 1KB

        def save_side_effect(buffer, **kwargs):
            buffer.write(b"\x00" * 1000)

        mock_image.save.side_effect = save_side_effect

        with patch("code_puppy.command_line.clipboard.Image") as mock_image_module:
            mock_image_module.Image = type(mock_image)
            result = _resize_image_if_needed(mock_image, 10 * 1024 * 1024)  # 10MB limit

        # Should return the same image (not resized)
        assert result is mock_image

    def test_resize_called_for_large_image(self):
        """Test that large images trigger resize."""
        from code_puppy.command_line.clipboard import _resize_image_if_needed

        # Create a mock large image
        mock_image = MagicMock()
        mock_image.width = 5000
        mock_image.height = 5000

        call_count = [0]

        def save_side_effect(buffer, **kwargs):
            # First call: simulate large image (20MB)
            # Subsequent calls: simulate resized image (5MB)
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

        # Should have called resize
        assert mock_image.resize.called
        assert result is resized_mock


class TestSafeOpenImageEdgeCases:
    """Tests for _safe_open_image error handling branches."""

    def test_returns_none_when_pil_unavailable(self):
        from code_puppy.command_line.clipboard import _safe_open_image

        with patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", False):
            assert _safe_open_image(b"data") is None

    def test_decompression_bomb_error(self):
        from PIL import Image as RealImage

        from code_puppy.command_line.clipboard import _safe_open_image

        with patch("code_puppy.command_line.clipboard.Image") as mock_img:
            mock_img.DecompressionBombError = RealImage.DecompressionBombError
            mock_img.UnidentifiedImageError = RealImage.UnidentifiedImageError
            mock_img.open.side_effect = RealImage.DecompressionBombError("bomb")
            assert _safe_open_image(b"data") is None

    def test_unidentified_image_error(self):
        from PIL import Image as RealImage

        from code_puppy.command_line.clipboard import _safe_open_image

        mock_opened = MagicMock()
        mock_opened.verify.side_effect = RealImage.UnidentifiedImageError("unknown")

        with patch("code_puppy.command_line.clipboard.Image") as mock_img:
            mock_img.DecompressionBombError = RealImage.DecompressionBombError
            mock_img.UnidentifiedImageError = RealImage.UnidentifiedImageError
            mock_img.open.return_value = mock_opened
            assert _safe_open_image(b"data") is None

    def test_os_error(self):
        from PIL import Image as RealImage

        from code_puppy.command_line.clipboard import _safe_open_image

        with patch("code_puppy.command_line.clipboard.Image") as mock_img:
            mock_img.DecompressionBombError = RealImage.DecompressionBombError
            mock_img.UnidentifiedImageError = RealImage.UnidentifiedImageError
            mock_img.open.side_effect = OSError("bad")
            assert _safe_open_image(b"data") is None

    def test_generic_exception(self):
        from PIL import Image as RealImage

        from code_puppy.command_line.clipboard import _safe_open_image

        with patch("code_puppy.command_line.clipboard.Image") as mock_img:
            mock_img.DecompressionBombError = RealImage.DecompressionBombError
            mock_img.UnidentifiedImageError = RealImage.UnidentifiedImageError
            mock_img.open.side_effect = RuntimeError("weird")
            assert _safe_open_image(b"data") is None

    def test_success_path(self):
        from PIL import Image as RealImage

        from code_puppy.command_line.clipboard import _safe_open_image

        mock_verified = MagicMock()
        mock_result = MagicMock()

        with patch("code_puppy.command_line.clipboard.Image") as mock_img:
            mock_img.DecompressionBombError = RealImage.DecompressionBombError
            mock_img.UnidentifiedImageError = RealImage.UnidentifiedImageError
            mock_img.open.side_effect = [mock_verified, mock_result]
            result = _safe_open_image(b"data")
        assert result is mock_result
        mock_verified.verify.assert_called_once()


class TestGetLinuxClipboardImage:
    """Tests for _get_linux_clipboard_image."""

    def test_returns_none_when_no_tool(self):
        from code_puppy.command_line.clipboard import _get_linux_clipboard_image

        with patch(
            "code_puppy.command_line.clipboard._check_linux_clipboard_tool",
            return_value=None,
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

    def test_wl_paste_failure(self):
        from code_puppy.command_line.clipboard import _get_linux_clipboard_image

        mock_result = MagicMock(returncode=1, stdout=b"")
        with (
            patch(
                "code_puppy.command_line.clipboard._check_linux_clipboard_tool",
                return_value="wl-paste",
            ),
            patch("subprocess.run", return_value=mock_result),
        ):
            assert _get_linux_clipboard_image() is None

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

    def test_xclip_failure(self):
        from code_puppy.command_line.clipboard import _get_linux_clipboard_image

        mock_result = MagicMock(returncode=1, stdout=b"")
        with (
            patch(
                "code_puppy.command_line.clipboard._check_linux_clipboard_tool",
                return_value="xclip",
            ),
            patch("subprocess.run", return_value=mock_result),
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


class TestCheckLinuxClipboardToolTimeout:
    """Tests for timeout handling in _check_linux_clipboard_tool."""

    def test_wl_paste_timeout_falls_through_to_xclip(self):
        from code_puppy.command_line.clipboard import _check_linux_clipboard_tool

        def run_side_effect(cmd, **kwargs):
            if cmd[0] == "wl-paste":
                raise subprocess.TimeoutExpired("wl-paste", 5)
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=run_side_effect):
            assert _check_linux_clipboard_tool() == "xclip"

    def test_xclip_timeout_returns_none(self):
        from code_puppy.command_line.clipboard import _check_linux_clipboard_tool

        def run_side_effect(cmd, **kwargs):
            if cmd[0] == "wl-paste":
                raise FileNotFoundError()
            raise subprocess.TimeoutExpired("xclip", 5)

        with patch("subprocess.run", side_effect=run_side_effect):
            assert _check_linux_clipboard_tool() is None


class TestResizeImageEdgeCases:
    """Tests for edge cases in _resize_image_if_needed."""

    def test_returns_image_when_image_module_is_none(self):
        from code_puppy.command_line.clipboard import _resize_image_if_needed

        mock_img = MagicMock()
        with patch("code_puppy.command_line.clipboard.Image", None):
            assert _resize_image_if_needed(mock_img, 1000) is mock_img

    def test_caps_height_dimension(self):
        """Test height capping when it exceeds MAX_IMAGE_DIMENSION."""
        from code_puppy.command_line.clipboard import _resize_image_if_needed

        mock_image = MagicMock()
        mock_image.width = 1000
        mock_image.height = 10000  # Very tall

        call_count = [0]

        def save_side_effect(buffer, **kwargs):
            if call_count[0] == 0:
                buffer.write(b"\x00" * (20 * 1024 * 1024))  # 20MB
            else:
                buffer.write(b"\x00" * (5 * 1024 * 1024))
            call_count[0] += 1

        mock_image.save.side_effect = save_side_effect
        resized_mock = MagicMock()
        mock_image.resize.return_value = resized_mock

        with patch("code_puppy.command_line.clipboard.Image") as mock_img_mod:
            mock_img_mod.Image = type(mock_image)
            mock_img_mod.Resampling.LANCZOS = "lanczos"
            result = _resize_image_if_needed(mock_image, 10 * 1024 * 1024)

        assert result is resized_mock

    def test_caps_width_dimension(self):
        """Test width capping when it exceeds MAX_IMAGE_DIMENSION."""
        from code_puppy.command_line.clipboard import _resize_image_if_needed

        mock_image = MagicMock()
        mock_image.width = 10000  # Very wide
        mock_image.height = 1000

        call_count = [0]

        def save_side_effect(buffer, **kwargs):
            if call_count[0] == 0:
                buffer.write(b"\x00" * (20 * 1024 * 1024))
            else:
                buffer.write(b"\x00" * (5 * 1024 * 1024))
            call_count[0] += 1

        mock_image.save.side_effect = save_side_effect
        resized_mock = MagicMock()
        mock_image.resize.return_value = resized_mock

        with patch("code_puppy.command_line.clipboard.Image") as mock_img_mod:
            mock_img_mod.Image = type(mock_image)
            mock_img_mod.Resampling.LANCZOS = "lanczos"
            result = _resize_image_if_needed(mock_image, 10 * 1024 * 1024)

        assert result is resized_mock


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

    def test_linux_xclip_no_image(self):
        from code_puppy.command_line.clipboard import has_image_in_clipboard

        mock_result = MagicMock(stdout="text/plain", returncode=0)
        with (
            patch("code_puppy.command_line.clipboard.sys.platform", "linux"),
            patch(
                "code_puppy.command_line.clipboard._check_linux_clipboard_tool",
                return_value="xclip",
            ),
            patch("subprocess.run", return_value=mock_result),
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

    def test_linux_exception_returns_false(self):
        from code_puppy.command_line.clipboard import has_image_in_clipboard

        with (
            patch("code_puppy.command_line.clipboard.sys.platform", "linux"),
            patch(
                "code_puppy.command_line.clipboard._check_linux_clipboard_tool",
                return_value="wl-paste",
            ),
            patch("subprocess.run", side_effect=RuntimeError("err")),
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


class TestGetClipboardImageLinux:
    """Tests for get_clipboard_image on Linux."""

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

    def test_linux_small_image_pil_unavailable(self):
        from code_puppy.command_line.clipboard import get_clipboard_image

        small_bytes = b"pngdata" * 10
        with (
            patch("code_puppy.command_line.clipboard.sys.platform", "linux"),
            patch(
                "code_puppy.command_line.clipboard._get_linux_clipboard_image",
                return_value=small_bytes,
            ),
            patch("code_puppy.command_line.clipboard.PIL_AVAILABLE", False),
        ):
            result = get_clipboard_image()
        assert result == small_bytes

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

    def test_la_mode_kept(self):
        from code_puppy.command_line.clipboard import get_clipboard_image

        mock_image = self._make_mock_image("LA")
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

    def test_p_mode_with_transparency_kept(self):
        from code_puppy.command_line.clipboard import get_clipboard_image

        mock_image = self._make_mock_image("P", has_transparency=True)
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


class TestGetPendingImagesNoBinaryContent:
    """Test get_pending_images when BinaryContent unavailable."""

    def test_returns_empty_list(self):
        from code_puppy.command_line.clipboard import ClipboardAttachmentManager

        manager = ClipboardAttachmentManager()
        manager.add_image(b"data")

        with patch("code_puppy.command_line.clipboard.BINARY_CONTENT_AVAILABLE", False):
            assert manager.get_pending_images() == []


class TestClearPendingNoImages:
    """Test clear_pending when no images are pending."""

    def test_clear_when_empty(self):
        from code_puppy.command_line.clipboard import ClipboardAttachmentManager

        manager = ClipboardAttachmentManager()
        manager.clear_pending()  # Should not error
        assert manager.get_pending_count() == 0


class TestMaxImageSizeConstant:
    """Tests for MAX_IMAGE_SIZE_BYTES constant."""

    def test_max_size_is_10mb(self):
        """Test that max image size is 10MB."""
        from code_puppy.command_line.clipboard import MAX_IMAGE_SIZE_BYTES

        assert MAX_IMAGE_SIZE_BYTES == 10 * 1024 * 1024

    def test_max_dimension_is_4096(self):
        """Test that max dimension is 4096."""
        from code_puppy.command_line.clipboard import MAX_IMAGE_DIMENSION

        assert MAX_IMAGE_DIMENSION == 4096


class TestPILAvailableFlag:
    """Tests for PIL_AVAILABLE flag behavior."""

    def test_pil_available_is_bool(self):
        """Test that PIL_AVAILABLE is a boolean."""
        from code_puppy.command_line.clipboard import PIL_AVAILABLE

        assert isinstance(PIL_AVAILABLE, bool)

    def test_binary_content_available_is_bool(self):
        """Test that BINARY_CONTENT_AVAILABLE is a boolean."""
        from code_puppy.command_line.clipboard import BINARY_CONTENT_AVAILABLE

        assert isinstance(BINARY_CONTENT_AVAILABLE, bool)


class TestSecurityFeatures:
    """Tests for security features (SEC-CLIP-001 through SEC-CLIP-004)."""

    def test_max_pending_images_constant_exists(self):
        """Test that MAX_PENDING_IMAGES constant is defined."""
        from code_puppy.command_line.clipboard import MAX_PENDING_IMAGES

        assert MAX_PENDING_IMAGES == 10

    def test_rate_limit_constant_exists(self):
        """Test that CLIPBOARD_RATE_LIMIT_SECONDS constant is defined."""
        from code_puppy.command_line.clipboard import CLIPBOARD_RATE_LIMIT_SECONDS

        assert CLIPBOARD_RATE_LIMIT_SECONDS == 0.5

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

    def test_clear_allows_adding_again(self):
        """Test that clearing the queue allows adding images again."""
        from code_puppy.command_line.clipboard import (
            MAX_PENDING_IMAGES,
            ClipboardAttachmentManager,
        )

        manager = ClipboardAttachmentManager()
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        # Fill up to the limit
        for _ in range(MAX_PENDING_IMAGES):
            manager.add_image(fake_png)

        # Clear the queue
        manager.clear_pending()

        # Should be able to add again
        placeholder = manager.add_image(fake_png)
        assert placeholder is not None
        assert manager.get_pending_count() == 1

    def test_safe_open_image_returns_none_for_invalid_data(self):
        """Test that _safe_open_image rejects invalid image data."""
        from code_puppy.command_line.clipboard import _safe_open_image

        # Invalid data that's not an image
        invalid_data = b"not an image at all"
        result = _safe_open_image(invalid_data)

        assert result is None

    def test_safe_open_image_handles_truncated_png(self):
        """Test that _safe_open_image handles truncated PNG gracefully."""
        from code_puppy.command_line.clipboard import _safe_open_image

        # Truncated PNG header
        truncated_png = b"\x89PNG\r\n\x1a\n"
        result = _safe_open_image(truncated_png)

        assert result is None

    def test_pil_max_pixels_is_set(self):
        """Test SEC-CLIP-002: PIL MAX_IMAGE_PIXELS is explicitly set."""
        from code_puppy.command_line.clipboard import PIL_AVAILABLE

        if PIL_AVAILABLE:
            from PIL import Image

            # Should be set to the PIL default value
            assert Image.MAX_IMAGE_PIXELS == 178956970
