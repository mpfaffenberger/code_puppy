"""Clipboard image reading and management utilities.

Provides cross-platform clipboard image capture:
- Windows/macOS: Uses PIL.ImageGrab (native)
- Linux: Falls back to xclip or wl-paste via subprocess

Also provides a thread-safe ClipboardAttachmentManager for managing
pending clipboard image attachments in the CLI.
"""

import io
import logging
import subprocess
import sys
import threading
import time
from typing import Optional

# Try to import PIL - it's optional but needed for clipboard image support
try:
    from PIL import Image, ImageGrab

    PIL_AVAILABLE = True
    # SEC-CLIP-002: Protect against decompression bombs
    # Set explicit limit (PIL default) to prevent memory exhaustion from malicious images
    Image.MAX_IMAGE_PIXELS = 178956970
except ImportError:
    PIL_AVAILABLE = False
    Image = None  # type: ignore[misc, assignment]
    ImageGrab = None  # type: ignore[misc, assignment]

# Import BinaryContent for pydantic-ai integration
try:
    from pydantic_ai import BinaryContent

    BINARY_CONTENT_AVAILABLE = True
except ImportError:
    BINARY_CONTENT_AVAILABLE = False
    BinaryContent = None  # type: ignore[misc, assignment]

logger = logging.getLogger(__name__)

# Constants
MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024  # 10MB
MAX_IMAGE_DIMENSION = 4096  # Max width/height for resize
MAX_PENDING_IMAGES = (
    10  # SEC-CLIP-001: Limit pending images to prevent memory exhaustion
)
CLIPBOARD_RATE_LIMIT_SECONDS: float = 0.5  # SEC-CLIP-004: Max 2 captures per second

# Rate limiting state
_last_clipboard_capture: float = 0.0


def _safe_open_image(image_bytes: bytes) -> Optional["Image.Image"]:
    """Safely open and verify an image from bytes.

    Verifies image integrity to protect against malicious images.

    Args:
        image_bytes: Raw image bytes to open.

    Returns:
        PIL Image if valid, None if verification fails.
    """
    if not PIL_AVAILABLE or Image is None:
        return None

    try:
        # First pass: verify integrity without fully loading
        verify_image = Image.open(io.BytesIO(image_bytes))
        verify_image.verify()  # Checks for corruption/malicious data

        # Re-open after verify (verify() closes the image)
        image = Image.open(io.BytesIO(image_bytes))
        return image
    except Image.DecompressionBombError as e:
        logger.warning(f"Rejected decompression bomb image: {e}")
        return None
    except Image.UnidentifiedImageError as e:
        logger.warning(f"Rejected unidentified image format: {e}")
        return None
    except OSError as e:
        logger.warning(f"Rejected potentially malicious image: {e}")
        return None
    except Exception as e:
        logger.warning(f"Failed to open/verify image: {type(e).__name__}: {e}")
        return None


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


def _resize_image_if_needed(image: "Image.Image", max_bytes: int) -> "Image.Image":
    """Resize image if it exceeds max size when saved as PNG.

    Args:
        image: PIL Image to potentially resize.
        max_bytes: Maximum allowed size in bytes.

    Returns:
        Original or resized image.
    """
    if Image is None:
        return image

    # Check current size
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    current_size = buffer.tell()

    if current_size <= max_bytes:
        return image

    logger.info(
        f"Image size ({current_size / 1024 / 1024:.2f}MB) exceeds limit "
        f"({max_bytes / 1024 / 1024:.2f}MB), resizing..."
    )

    # Calculate scale factor to reduce size
    # Rough estimate: size scales with area (width * height)
    scale_factor = (max_bytes / current_size) ** 0.5 * 0.9  # 0.9 for safety margin

    new_width = int(image.width * scale_factor)
    new_height = int(image.height * scale_factor)

    # Ensure we don't go below minimum dimensions
    new_width = max(new_width, 100)
    new_height = max(new_height, 100)

    # Also cap at max dimension
    if new_width > MAX_IMAGE_DIMENSION:
        ratio = MAX_IMAGE_DIMENSION / new_width
        new_width = MAX_IMAGE_DIMENSION
        new_height = int(new_height * ratio)
    if new_height > MAX_IMAGE_DIMENSION:
        ratio = MAX_IMAGE_DIMENSION / new_height
        new_height = MAX_IMAGE_DIMENSION
        new_width = int(new_width * ratio)

    resized = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    logger.info(
        f"Resized image from {image.width}x{image.height} to {new_width}x{new_height}"
    )

    return resized


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


def get_clipboard_image() -> Optional[bytes]:
    """Get clipboard image as PNG bytes.

    Handles cross-platform clipboard access:
    - Windows/macOS: Uses PIL.ImageGrab
    - Linux: Uses xclip or wl-paste

    Images larger than 10MB are automatically resized.

    Returns:
        PNG bytes if clipboard contains an image, None otherwise.
    """
    image_bytes: Optional[bytes] = None

    # Linux path - use command line tools
    if sys.platform == "linux":
        image_bytes = _get_linux_clipboard_image()
        if image_bytes is None:
            return None

        # Check size and resize if needed
        if len(image_bytes) > MAX_IMAGE_SIZE_BYTES:
            if not PIL_AVAILABLE:
                logger.warning(
                    f"Image size ({len(image_bytes) / 1024 / 1024:.2f}MB) exceeds limit, "
                    "but PIL not available for resizing."
                )
                return None

            try:
                # Use safe image opening with verification
                image = _safe_open_image(image_bytes)
                if image is None:
                    logger.warning(
                        "Image verification failed for Linux clipboard image"
                    )
                    return None
                image = _resize_image_if_needed(image, MAX_IMAGE_SIZE_BYTES)
                buffer = io.BytesIO()
                image.save(buffer, format="PNG", optimize=True)
                image_bytes = buffer.getvalue()
            except Exception as e:
                logger.warning(f"Error resizing Linux clipboard image: {e}")
                return None
        else:
            # Verify even small images for safety
            if PIL_AVAILABLE:
                image = _safe_open_image(image_bytes)
                if image is None:
                    logger.warning(
                        "Image verification failed for Linux clipboard image"
                    )
                    return None

        return image_bytes

    # Windows/macOS path - use PIL
    if not PIL_AVAILABLE:
        logger.warning("PIL/Pillow not available. Install with: pip install Pillow")
        return None

    try:
        image = ImageGrab.grabclipboard()

        if image is None:
            return None

        if not isinstance(image, Image.Image):
            # Could be a list of file paths on some systems
            logger.debug(f"Clipboard contains non-image data: {type(image)}")
            return None

        # Log original dimensions
        logger.info(f"Captured clipboard image: {image.width}x{image.height}")

        # Convert to RGB if necessary (handles RGBA, P mode, etc.)
        if image.mode in ("RGBA", "LA") or (
            image.mode == "P" and "transparency" in image.info
        ):
            # Keep alpha channel for PNG
            pass
        elif image.mode != "RGB":
            image = image.convert("RGB")

        # Resize if needed
        image = _resize_image_if_needed(image, MAX_IMAGE_SIZE_BYTES)

        # Convert to PNG bytes
        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        image_bytes = buffer.getvalue()

        logger.info(f"Clipboard image size: {len(image_bytes) / 1024:.1f}KB")
        return image_bytes

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

    image_bytes = get_clipboard_image()
    if image_bytes is None:
        return None

    return BinaryContent(data=image_bytes, media_type="image/png")


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
        self._pending_images: list[bytes] = []
        self._lock = threading.Lock()
        self._counter = 0

    def add_image(self, image_bytes: bytes) -> str:
        """Add image bytes to pending attachments.

        Args:
            image_bytes: PNG image bytes to add.

        Returns:
            Placeholder ID string like '[📋 clipboard image 1]'

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
            self._pending_images.append(image_bytes)
            placeholder = f"[📋 clipboard image {self._counter}]"
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
                BinaryContent(data=img_bytes, media_type="image/png")
                for img_bytes in self._pending_images
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

    image_bytes = get_clipboard_image()
    if image_bytes is None:
        return None

    manager = get_clipboard_manager()
    placeholder = manager.add_image(image_bytes)

    # Update timestamp on successful capture
    _last_clipboard_capture = now
    return placeholder
