"""Clipboard image reading and management utilities.

Provides cross-platform clipboard image capture:
- Windows/macOS: Uses PIL.ImageGrab (native)
- Linux: Falls back to xclip or wl-paste via subprocess

Also provides a thread-safe ClipboardAttachmentManager for managing
pending clipboard image attachments in the CLI.
"""

import logging
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

# Try to import PIL - it's optional but needed for clipboard image support
try:
    from PIL import Image, ImageGrab

    PIL_AVAILABLE = True
    # Note: Image.MAX_IMAGE_PIXELS is set by image_utils on import (SEC-CLIP-002)
except ImportError:
    PIL_AVAILABLE = False
    Image = None  # type: ignore[misc, assignment]
    ImageGrab = None  # type: ignore[misc, assignment]

# Shared resize/verify helpers and limits — single source of truth.
from code_puppy.command_line.image_utils import (  # noqa: E402
    ImageTooLargeError,
    _encode_image,
    _safe_open_image,
    normalize_image_bytes,
)

# Import BinaryContent for pydantic-ai integration
try:
    from pydantic_ai import BinaryContent

    BINARY_CONTENT_AVAILABLE = True
except ImportError:
    BINARY_CONTENT_AVAILABLE = False
    BinaryContent = None  # type: ignore[misc, assignment]

logger = logging.getLogger(__name__)

# Constants
MAX_PENDING_IMAGES = (
    10  # SEC-CLIP-001: Limit pending images to prevent memory exhaustion
)
MAX_IMAGE_FILE_SIZE_BYTES = 50 * 1024 * 1024  # Local image files only
CLIPBOARD_RATE_LIMIT_SECONDS: float = 0.5  # SEC-CLIP-004: Max 2 captures per second
_IMAGE_FILE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
_IMAGE_SUFFIX_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
}

# Rate limiting state
_last_clipboard_capture: float = 0.0


def _check_linux_clipboard_tool() -> Optional[str]:
    """Check which Linux clipboard tool is available.

    Returns:
        'xclip', 'wl-paste', or None if neither is available.
    """
    # Check for wl-paste first (Wayland)
    try:
        subprocess.run(
            ["wl-paste", "--version"],
            capture_output=True,
            timeout=5,
        )
        return "wl-paste"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Check for xclip (X11)
    try:
        subprocess.run(
            ["xclip", "-version"],
            capture_output=True,
            timeout=5,
        )
        return "xclip"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return None


def _get_linux_clipboard_image() -> Optional[bytes]:
    """Get clipboard image on Linux using xclip or wl-paste.

    Returns:
        PNG bytes if image found, None otherwise.
    """
    tool = _check_linux_clipboard_tool()

    if tool is None:
        logger.warning(
            "No clipboard tool found on Linux. "
            "Install 'xclip' (X11) or 'wl-clipboard' (Wayland) for clipboard image support."
        )
        return None

    try:
        if tool == "wl-paste":
            # wl-paste for Wayland
            result = subprocess.run(
                ["wl-paste", "--type", "image/png"],
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout
        elif tool == "xclip":
            # xclip for X11
            result = subprocess.run(
                ["xclip", "-selection", "clipboard", "-t", "image/png", "-o"],
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout
    except subprocess.TimeoutExpired:
        logger.warning(f"Timeout reading clipboard with {tool}")
    except Exception as e:
        logger.warning(f"Error reading clipboard with {tool}: {e}")

    return None


def _image_to_attachment(image: "Image.Image", media_type: str = "image/png"):
    """Encode a PIL image and normalize it, returning ``(bytes, media_type)``.

    The source format is preserved where possible: clipboard screenshots stay
    PNG, and oversized images are re-encoded by
    :func:`normalize_image_bytes` (JPEG for opaque non-PNG sources).
    Returns ``None`` if the image cannot be made to fit.
    """
    if Image is None:
        return None
    try:
        encoded = normalize_image_bytes(_encode_image(image, "PNG"), media_type)
    except ImageTooLargeError as exc:
        logger.warning(f"Clipboard image is too large to attach: {exc}")
        return None
    except Exception as e:
        logger.warning(f"Failed to encode clipboard image: {e}")
        return None
    data, out_media_type = encoded
    logger.info(f"Clipboard image size: {len(data) / 1024:.1f}KB ({out_media_type})")
    return data, out_media_type


def get_image_file_bytes(file_path: str) -> Optional[tuple[bytes, str]]:
    """Read a local image file and normalize it, preserving its format."""
    if not PIL_AVAILABLE:
        return None
    try:
        path = Path(file_path).expanduser()
        suffix = path.suffix.lower()
        if not path.is_file() or suffix not in _IMAGE_FILE_SUFFIXES:
            return None
        if path.stat().st_size > MAX_IMAGE_FILE_SIZE_BYTES:
            logger.warning(f"Rejected oversized image file: {path}")
            return None
        data = path.read_bytes()
        if _safe_open_image(data) is None:
            return None
        return normalize_image_bytes(
            data, _IMAGE_SUFFIX_MEDIA_TYPES.get(suffix, "image/png")
        )
    except ImageTooLargeError as exc:
        logger.warning(f"Pasted image is too large to attach: {exc}")
        return None
    except Exception as e:
        logger.debug(f"Failed to read pasted image file {file_path!r}: {e}")
        return None


def _image_file_list_to_attachment(value) -> Optional[tuple[bytes, str]]:
    if not isinstance(value, (list, tuple)):
        return None
    for item in value:
        if isinstance(item, str):
            image = get_image_file_bytes(item)
            if image is not None:
                return image
    return None


def has_image_in_clipboard() -> bool:
    """Check if clipboard contains an image.

    Returns:
        True if clipboard contains an image, False otherwise.
    """
    if sys.platform == "linux":
        # For Linux, we need to actually try to get the image
        # since there's no lightweight "check" method
        tool = _check_linux_clipboard_tool()
        if tool is None:
            return False

        try:
            if tool == "wl-paste":
                result = subprocess.run(
                    ["wl-paste", "--list-types"],
                    capture_output=True,
                    timeout=5,
                    text=True,
                )
                return "image/png" in result.stdout or "image/" in result.stdout
            elif tool == "xclip":
                result = subprocess.run(
                    ["xclip", "-selection", "clipboard", "-t", "TARGETS", "-o"],
                    capture_output=True,
                    timeout=5,
                    text=True,
                )
                return "image/png" in result.stdout or "image/" in result.stdout
        except (subprocess.TimeoutExpired, Exception):
            return False

        return False

    # Windows/macOS - use PIL
    if not PIL_AVAILABLE:
        return False

    try:
        image = ImageGrab.grabclipboard()
        return image is not None and isinstance(image, Image.Image)
    except Exception as e:
        logger.debug(f"Error checking clipboard: {e}")
        return False


def get_clipboard_image() -> Optional[tuple[bytes, str]]:
    """Get the clipboard image as ``(bytes, media_type)``.

    Handles cross-platform clipboard access:
    - Windows/macOS: Uses PIL.ImageGrab
    - Linux: Uses xclip or wl-paste

    Images over the API's base64 payload budget are downscaled, keeping the
    source format (JPEG stays JPEG instead of ballooning into PNG).

    Returns:
        ``(image_bytes, media_type)`` if the clipboard holds an image, else
        ``None``.
    """
    image_bytes: Optional[bytes] = None

    # Linux path - use command line tools
    if sys.platform == "linux":
        image_bytes = _get_linux_clipboard_image()
        if image_bytes is None:
            return None

        if not PIL_AVAILABLE:
            logger.warning(
                "PIL not available; cannot verify or normalize clipboard image."
            )
            return None

        # Verify even small images for safety.
        if _safe_open_image(image_bytes) is None:
            logger.warning("Image verification failed for Linux clipboard image")
            return None

        try:
            return normalize_image_bytes(image_bytes, "image/png")
        except ImageTooLargeError as exc:
            logger.warning(f"Linux clipboard image is too large to attach: {exc}")
            return None
        except Exception as e:
            logger.warning(f"Error normalizing Linux clipboard image: {e}")
            return None

    # Windows/macOS path - use PIL
    if not PIL_AVAILABLE:
        logger.warning("PIL/Pillow not available. Install with: pip install Pillow")
        return None

    try:
        image = ImageGrab.grabclipboard()

        if image is None:
            return None

        if not isinstance(image, Image.Image):
            attachment = _image_file_list_to_attachment(image)
            if attachment is not None:
                return attachment
            logger.debug(f"Clipboard contains non-image data: {type(image)}")
            return None

        logger.info(f"Captured clipboard image: {image.width}x{image.height}")
        return _image_to_attachment(image)

    except Exception as e:
        logger.warning(f"Error reading clipboard image: {e}")
        return None


def get_clipboard_image_as_binary_content() -> Optional["BinaryContent"]:
    """Get clipboard image as pydantic-ai BinaryContent.

    This is the preferred method for integrating clipboard images
    with pydantic-ai agents.

    Returns:
        BinaryContent with PNG image if available, None otherwise.
    """
    if not BINARY_CONTENT_AVAILABLE:
        logger.warning("pydantic-ai BinaryContent not available")
        return None

    attachment = get_clipboard_image()
    if attachment is None:
        return None

    data, media_type = attachment
    return BinaryContent(data=data, media_type=media_type)


class ClipboardAttachmentManager:
    """Thread-safe manager for pending clipboard image attachments.

    This class manages clipboard images that have been captured but not yet
    sent to the AI model. It provides a simple interface for adding images,
    retrieving them as BinaryContent, and clearing the queue.

    Usage:
        manager = get_clipboard_manager()
        placeholder = manager.add_image(image_bytes)
        # Later, when sending to AI:
        images = manager.get_pending_images()
        manager.clear_pending()
    """

    def __init__(self) -> None:
        """Initialize the clipboard attachment manager."""
        # (data, media_type) pairs — format is preserved end to end.
        self._pending_images: list[tuple[bytes, str]] = []
        self._lock = threading.Lock()
        self._counter = 0

    def add_image(self, image_bytes: bytes, media_type: str = "image/png") -> str:
        """Add image bytes to pending attachments.

        Args:
            image_bytes: Encoded image bytes to add.
            media_type: MIME type of *image_bytes* (defaults to PNG).

        Returns:
            Placeholder ID string like '[clipboard image 1]'

        Raises:
            ValueError: If MAX_PENDING_IMAGES limit is reached.
        """
        with self._lock:
            # SEC-CLIP-001: Check limit BEFORE adding to prevent memory exhaustion
            if len(self._pending_images) >= MAX_PENDING_IMAGES:
                raise ValueError(
                    f"Maximum of {MAX_PENDING_IMAGES} pending images reached. "
                    "Send your message to clear the queue, or use /paste clear."
                )
            self._counter += 1
            self._pending_images.append((image_bytes, media_type))
            placeholder = f"[clipboard image {self._counter}]"
            logger.debug(
                f"Added clipboard image {self._counter} "
                f"({len(image_bytes) / 1024:.1f}KB)"
            )
            return placeholder

    def get_pending_images(self) -> list["BinaryContent"]:
        """Get all pending images as BinaryContent list.

        Returns:
            List of BinaryContent objects for each pending image.
            Returns empty list if BinaryContent not available.
        """
        if not BINARY_CONTENT_AVAILABLE:
            logger.warning("BinaryContent not available, returning empty list")
            return []

        with self._lock:
            return [
                BinaryContent(data=data, media_type=media_type)
                for data, media_type in self._pending_images
            ]

    def clear_pending(self) -> None:
        """Clear all pending images."""
        with self._lock:
            count = len(self._pending_images)
            self._pending_images.clear()
            if count > 0:
                logger.debug(f"Cleared {count} pending clipboard image(s)")

    def get_pending_count(self) -> int:
        """Get count of pending images.

        Returns:
            Number of images currently pending.
        """
        with self._lock:
            return len(self._pending_images)

    def has_pending(self) -> bool:
        """Check if there are any pending images.

        Returns:
            True if there are pending images, False otherwise.
        """
        with self._lock:
            return len(self._pending_images) > 0


# Global singleton instance
_clipboard_manager: Optional[ClipboardAttachmentManager] = None
_manager_lock = threading.Lock()


def get_clipboard_manager() -> ClipboardAttachmentManager:
    """Get or create the global clipboard manager singleton.

    Returns:
        The global ClipboardAttachmentManager instance.
    """
    global _clipboard_manager

    if _clipboard_manager is None:
        with _manager_lock:
            # Double-check locking pattern
            if _clipboard_manager is None:
                _clipboard_manager = ClipboardAttachmentManager()

    return _clipboard_manager


def capture_clipboard_image_to_pending() -> Optional[str]:
    """Convenience function to capture clipboard image and add to pending.

    This combines get_clipboard_image() and add_image() into a single call.
    Includes rate limiting to prevent rapid captures (SEC-CLIP-004).

    Returns:
        Placeholder string if image captured, None if no image or rate limited.
    """
    global _last_clipboard_capture

    # SEC-CLIP-004: Rate limiting to prevent rapid captures
    now = time.monotonic()
    if now - _last_clipboard_capture < CLIPBOARD_RATE_LIMIT_SECONDS:
        logger.debug("Clipboard capture rate limited")
        return None  # Rate limited, silently ignore

    attachment = get_clipboard_image()
    if attachment is None:
        return None

    data, media_type = attachment
    manager = get_clipboard_manager()
    placeholder = manager.add_image(data, media_type)

    # Update timestamp on successful capture
    _last_clipboard_capture = now
    return placeholder
