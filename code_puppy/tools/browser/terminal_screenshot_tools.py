"""Terminal Screenshot Tools.

This module provides tools for:
- Taking screenshots of the terminal browser
- Reading terminal output by scraping xterm.js DOM
- Loading images from the filesystem

Screenshots are returned as base64-encoded data that multimodal models
can directly see and analyze - no separate VQA agent needed.

Screenshots are automatically resized to reduce token usage.
"""

import base64
import io
import logging
from datetime import datetime
from pathlib import Path
from tempfile import gettempdir, mkdtemp
from typing import Any, Dict

from PIL import Image
from pydantic_ai import RunContext
from rich.text import Text

from code_puppy.messaging import emit_error, emit_info, emit_success
from code_puppy.tools.browser import format_terminal_banner
from code_puppy.tools.common import generate_group_id

from .terminal_tools import get_session_manager

logger = logging.getLogger(__name__)

# Default max height for screenshots (reduces token usage significantly)
DEFAULT_MAX_HEIGHT = 768

# Temporary directory for screenshots
_TEMP_SCREENSHOT_ROOT = Path(
    mkdtemp(prefix="code_puppy_terminal_screenshots_", dir=gettempdir())
)

# JavaScript to extract text content from xterm.js terminal
XTERM_TEXT_EXTRACTION_JS = """
() => {
    const selectors = [
        '.xterm-rows',
        '.xterm .xterm-rows',
        '[class*="xterm-rows"]',
        '.xterm-screen',
    ];
    
    let container = null;
    for (const selector of selectors) {
        container = document.querySelector(selector);
        if (container) break;
    }
    
    if (!container) {
        const xtermElement = document.querySelector('.xterm');
        if (xtermElement) {
            return {
                success: true,
                lines: xtermElement.innerText.split('\\n').filter(line => line.trim()),
                method: 'innerText'
            };
        }
        return { success: false, error: 'Could not find xterm.js terminal container' };
    }
    
    const rows = container.querySelectorAll('div');
    const lines = [];
    
    rows.forEach(row => {
        let text = '';
        const spans = row.querySelectorAll('span');
        if (spans.length > 0) {
            spans.forEach(span => {
                text += span.textContent || '';
            });
        } else {
            text = row.textContent || '';
        }
        if (text.trim()) {
            lines.push(text);
        }
    });
    
    return {
        success: true,
        lines: lines,
        method: 'row_extraction'
    };
}
"""


def _build_screenshot_path(prefix: str = "terminal_screenshot") -> Path:
    """Generate a unique screenshot path."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return _TEMP_SCREENSHOT_ROOT / f"{prefix}_{timestamp}.png"


def _resize_image(image_bytes: bytes, max_height: int = DEFAULT_MAX_HEIGHT) -> bytes:
    """Resize image to max height while maintaining aspect ratio.

    This dramatically reduces token usage for multimodal models.

    Args:
        image_bytes: Original PNG image bytes.
        max_height: Maximum height in pixels (default 384).

    Returns:
        Resized PNG image bytes.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))

        # Only resize if image is taller than max_height
        if img.height <= max_height:
            return image_bytes

        # Calculate new dimensions maintaining aspect ratio
        ratio = max_height / img.height
        new_width = int(img.width * ratio)
        new_height = max_height

        # Resize with high quality resampling
        resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # Save to bytes
        output = io.BytesIO()
        resized.save(output, format="PNG", optimize=True)
        output.seek(0)

        logger.debug(
            f"Resized image from {img.width}x{img.height} to {new_width}x{new_height}"
        )
        return output.read()

    except Exception as e:
        logger.warning(f"Failed to resize image: {e}, using original")
        return image_bytes


async def _capture_terminal_screenshot(
    full_page: bool = False,
    save_to_disk: bool = True,
    group_id: str | None = None,
    max_height: int = DEFAULT_MAX_HEIGHT,
) -> Dict[str, Any]:
    """Internal function to capture terminal screenshot.

    Args:
        full_page: Whether to capture full page or just viewport.
        save_to_disk: Whether to save screenshot to disk.
        group_id: Optional message group for logging.
        max_height: Maximum height for resizing (default 768px).

    Returns:
        Dict with screenshot_bytes, screenshot_path, base64_data, and success status.
    """
    try:
        manager = get_session_manager()
        page = await manager.get_current_page()

        if not page:
            return {
                "success": False,
                "error": "No active terminal page. Open terminal first.",
            }

        # Capture screenshot as bytes
        original_bytes = await page.screenshot(full_page=full_page, type="png")

        # Resize to reduce token usage for multimodal models
        screenshot_bytes = _resize_image(original_bytes, max_height=max_height)

        result: Dict[str, Any] = {
            "success": True,
            "screenshot_bytes": screenshot_bytes,
            "base64_data": base64.b64encode(screenshot_bytes).decode("utf-8"),
        }

        # Save to disk if requested (save the resized version)
        if save_to_disk:
            screenshot_path = _build_screenshot_path()
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            with open(screenshot_path, "wb") as f:
                f.write(screenshot_bytes)
            result["screenshot_path"] = str(screenshot_path)

            if group_id:
                emit_success(
                    f"Terminal screenshot saved: {screenshot_path}",
                    message_group=group_id,
                )

        return result

    except Exception as e:
        logger.exception("Error capturing terminal screenshot")
        return {"success": False, "error": str(e)}


async def terminal_screenshot(
    full_page: bool = False,
    save_to_disk: bool = True,
) -> Dict[str, Any]:
    """Take a screenshot of the terminal browser.

    Captures a screenshot and returns it as base64-encoded PNG data.
    Multimodal models can directly see and analyze this image.

    Args:
        full_page: Whether to capture the full page or just viewport.
            Defaults to False (viewport only - what's visible on screen).
        save_to_disk: Whether to save the screenshot to disk.
            Defaults to True.

    Returns:
        A dictionary containing:
            - success (bool): True if screenshot was captured.
            - base64_image (str): Base64-encoded PNG image data.
            - media_type (str): Always "image/png".
            - screenshot_path (str): Path to saved file (if save_to_disk=True).
            - error (str): Error message if unsuccessful.

    Example:
        >>> result = await terminal_screenshot()
        >>> if result["success"]:
        ...     # The base64_image can be shown to multimodal models
        ...     print(f"Screenshot saved to: {result['screenshot_path']}")
    """
    target = "full_page" if full_page else "viewport"
    group_id = generate_group_id("terminal_screenshot", target)
    banner = format_terminal_banner("TERMINAL SCREENSHOT 📷")
    emit_info(
        Text.from_markup(f"{banner} [bold cyan]{target}[/bold cyan]"),
        message_group=group_id,
    )

    result = await _capture_terminal_screenshot(
        full_page=full_page,
        save_to_disk=save_to_disk,
        group_id=group_id,
    )

    if not result["success"]:
        emit_error(result.get("error", "Screenshot failed"), message_group=group_id)
        return result

    # Return clean result with base64 image for model consumption
    return {
        "success": True,
        "base64_image": result["base64_data"],
        "media_type": "image/png",
        "screenshot_path": result.get("screenshot_path"),
        "message": "Screenshot captured. The base64_image contains the terminal view.",
    }


async def terminal_read_output(lines: int = 50) -> Dict[str, Any]:
    """Read text output from the terminal by scraping the xterm.js DOM.

    Extracts text content from the terminal by parsing xterm.js DOM.
    This is useful when you need the actual text rather than an image.

    Args:
        lines: Number of lines to return from the end. Defaults to 50.

    Returns:
        A dictionary containing:
            - success (bool): True if text was extracted.
            - output (str): The terminal text content.
            - line_count (int): Number of lines extracted.
            - error (str): Error message if unsuccessful.
    """
    group_id = generate_group_id("terminal_read_output", f"lines_{lines}")
    banner = format_terminal_banner("TERMINAL READ OUTPUT 📖")
    emit_info(
        Text.from_markup(f"{banner} [dim]last {lines} lines[/dim]"),
        message_group=group_id,
    )

    try:
        manager = get_session_manager()
        page = await manager.get_current_page()

        if not page:
            error_msg = "No active terminal page. Open terminal first."
            emit_error(error_msg, message_group=group_id)
            return {"success": False, "error": error_msg}

        # Execute JavaScript to extract text
        result = await page.evaluate(XTERM_TEXT_EXTRACTION_JS)

        if not result.get("success"):
            error_msg = result.get("error", "Failed to extract terminal text")
            emit_error(error_msg, message_group=group_id)
            return {"success": False, "error": error_msg}

        extracted_lines = result.get("lines", [])

        # Get the last N lines
        if len(extracted_lines) > lines:
            extracted_lines = extracted_lines[-lines:]

        output_text = "\n".join(extracted_lines)

        emit_success(
            f"Extracted {len(extracted_lines)} lines from terminal",
            message_group=group_id,
        )

        return {
            "success": True,
            "output": output_text,
            "line_count": len(extracted_lines),
        }

    except Exception as e:
        error_msg = f"Failed to read terminal output: {str(e)}"
        emit_error(error_msg, message_group=group_id)
        logger.exception("Error reading terminal output")
        return {"success": False, "error": error_msg}


async def load_image(
    image_path: str,
    max_height: int = DEFAULT_MAX_HEIGHT,
) -> Dict[str, Any]:
    """Load an image from the filesystem as base64 data.

    Loads any image file, resizes it to reduce token usage, and returns
    it as base64-encoded data that multimodal models can directly see.

    Args:
        image_path: Path to the image file.
        max_height: Maximum height for resizing (default 768px).

    Returns:
        A dictionary containing:
            - success (bool): True if image was loaded.
            - base64_image (str): Base64-encoded image data (resized).
            - media_type (str): The image MIME type (e.g., "image/png").
            - image_path (str): The original path.
            - error (str): Error message if unsuccessful.
    """
    group_id = generate_group_id("load_image", image_path)
    emit_info(f"LOAD IMAGE 🖼️ {image_path}", message_group=group_id)

    try:
        image_file = Path(image_path)

        if not image_file.exists():
            error_msg = f"Image file not found: {image_path}"
            emit_error(error_msg, message_group=group_id)
            return {"success": False, "error": error_msg, "image_path": image_path}

        if not image_file.is_file():
            error_msg = f"Path is not a file: {image_path}"
            emit_error(error_msg, message_group=group_id)
            return {"success": False, "error": error_msg, "image_path": image_path}

        # Read image bytes
        original_bytes = image_file.read_bytes()

        # Resize to reduce token usage
        image_bytes = _resize_image(original_bytes, max_height=max_height)

        # Always return as PNG after resizing (consistent format)
        base64_data = base64.b64encode(image_bytes).decode("utf-8")

        emit_success(f"Loaded image: {image_path}", message_group=group_id)

        return {
            "success": True,
            "base64_image": base64_data,
            "media_type": "image/png",  # Always PNG after resize
            "image_path": image_path,
            "message": f"Image loaded (resized to max {max_height}px height for token efficiency).",
        }

    except Exception as e:
        error_msg = f"Failed to load image: {str(e)}"
        emit_error(error_msg, message_group=group_id)
        logger.exception("Error loading image")
        return {"success": False, "error": error_msg, "image_path": image_path}


# =============================================================================
# Tool Registration Functions
# =============================================================================


def register_terminal_screenshot(agent):
    """Register the terminal screenshot tool."""

    @agent.tool
    async def terminal_screenshot_analyze(
        context: RunContext,
        full_page: bool = False,
    ) -> Dict[str, Any]:
        """
        Take a screenshot of the terminal browser.

        Returns the screenshot as base64 image data that you can see directly.
        Use this to see what's displayed in the terminal.

        Args:
            full_page: Capture full page (True) or just viewport (False).

        Returns:
            Dict with base64_image (PNG data you can see), screenshot_path, etc.
        """
        # Session is set by invoke_agent via contextvar
        return await terminal_screenshot(full_page=full_page)


def register_terminal_read_output(agent):
    """Register the terminal text reading tool."""

    @agent.tool
    async def terminal_read_output(
        context: RunContext,
        lines: int = 50,
    ) -> Dict[str, Any]:
        """
        Read text from the terminal (scrapes xterm.js DOM).

        Use this when you need the actual text content, not just an image.

        Args:
            lines: Number of lines to read from end (default: 50).

        Returns:
            Dict with output (text content), line_count, success.
        """
        # Session is set by invoke_agent via contextvar
        from . import terminal_screenshot_tools

        return await terminal_screenshot_tools.terminal_read_output(lines=lines)


def register_load_image(agent):
    """Register the image loading tool."""

    @agent.tool
    async def load_image_for_analysis(
        context: RunContext,
        image_path: str,
    ) -> Dict[str, Any]:
        """
        Load an image file so you can see and analyze it.

        Returns the image as base64 data that you can see directly.

        Args:
            image_path: Path to the image file.

        Returns:
            Dict with base64_image (you can see this), media_type, etc.
        """
        # Session is set by invoke_agent via contextvar
        return await load_image(image_path=image_path)


def register_terminal_compare_mockup(agent):
    """Register the mockup comparison tool."""

    @agent.tool
    async def terminal_compare_mockup(
        context: RunContext,
        mockup_path: str,
    ) -> Dict[str, Any]:
        """
        Compare the terminal to a mockup image.

        Takes a screenshot of the terminal and loads the mockup image.
        Returns both as base64 so you can visually compare them.

        Args:
            mockup_path: Path to the mockup/expected image.

        Returns:
            Dict with terminal_image, mockup_image (both base64), paths, etc.
        """
        # Session is set by invoke_agent via contextvar
        group_id = generate_group_id("terminal_compare_mockup", mockup_path)
        banner = format_terminal_banner("TERMINAL COMPARE MOCKUP 🖼️")
        emit_info(
            Text.from_markup(f"{banner} [bold cyan]{mockup_path}[/bold cyan]"),
            message_group=group_id,
        )

        # Load the mockup
        mockup_result = await load_image(mockup_path)
        if not mockup_result["success"]:
            return mockup_result

        # Take terminal screenshot
        terminal_result = await terminal_screenshot(full_page=False)
        if not terminal_result["success"]:
            return terminal_result

        emit_success(
            "Both images loaded. Compare them visually.",
            message_group=group_id,
        )

        return {
            "success": True,
            "terminal_image": terminal_result["base64_image"],
            "mockup_image": mockup_result["base64_image"],
            "media_type": "image/png",
            "terminal_path": terminal_result.get("screenshot_path"),
            "mockup_path": mockup_path,
            "message": "Both images loaded. terminal_image shows the current terminal, "
            "mockup_image shows the expected design. Compare them visually.",
        }
