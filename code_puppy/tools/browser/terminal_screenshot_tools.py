"""Terminal Screenshot Tools.

This module provides tools for:
- Taking screenshots of the terminal browser
- Reading terminal output by scraping xterm.js DOM
- Loading images from the filesystem

Screenshots and images are returned via ToolReturn with BinaryContent
so multimodal models can directly see and analyze them.

Images are automatically resized to reduce token usage.
"""

import io
import logging
import time
from datetime import datetime
from pathlib import Path
from tempfile import gettempdir, mkdtemp
from typing import Any, Dict, Union

from PIL import Image
from pydantic_ai import BinaryContent, RunContext, ToolReturn
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
) -> Union[ToolReturn, Dict[str, Any]]:
    """Take a screenshot of the terminal browser.

    Captures a screenshot and returns it via ToolReturn with BinaryContent
    so multimodal models can directly see and analyze the image.

    Args:
        full_page: Whether to capture the full page or just viewport.
            Defaults to False (viewport only - what's visible on screen).
        save_to_disk: Whether to save the screenshot to disk.
            Defaults to True.

    Returns:
        ToolReturn containing:
            - return_value: Success message with screenshot path
            - content: List with description and BinaryContent image
            - metadata: Screenshot details (path, target, timestamp)
        Or Dict with error info if failed.
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

    screenshot_path = result.get("screenshot_path", "(not saved)")

    # Return as ToolReturn with BinaryContent so the model can SEE the image!
    return ToolReturn(
        return_value=f"Terminal screenshot captured. Saved to: {screenshot_path}",
        content=[
            f"Here's the terminal screenshot ({target}):",
            BinaryContent(
                data=result["screenshot_bytes"],
                media_type="image/png",
            ),
            "Please analyze what you see in the terminal.",
        ],
        metadata={
            "success": True,
            "screenshot_path": screenshot_path,
            "target": target,
            "full_page": full_page,
            "timestamp": time.time(),
        },
    )


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
) -> Union[ToolReturn, Dict[str, Any]]:
    """Load an image from the filesystem for visual analysis.

    Loads any image file, resizes it to reduce token usage, and returns
    it via ToolReturn with BinaryContent so multimodal models can see it.

    Args:
        image_path: Path to the image file.
        max_height: Maximum height for resizing (default 768px).

    Returns:
        ToolReturn containing:
            - return_value: Success message with path info
            - content: List with description and BinaryContent image
            - metadata: Image details (path, resized height)
        Or Dict with error info if failed.
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

        emit_success(f"Loaded image: {image_path}", message_group=group_id)

        # Return as ToolReturn with BinaryContent so the model can SEE the image!
        return ToolReturn(
            return_value=f"Image loaded from: {image_path}",
            content=[
                f"Here's the image from {image_file.name}:",
                BinaryContent(
                    data=image_bytes,
                    media_type="image/png",  # Always PNG after resize
                ),
                "Please analyze what you see in this image.",
            ],
            metadata={
                "success": True,
                "image_path": image_path,
                "max_height": max_height,
                "timestamp": time.time(),
            },
        )

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
    ) -> Union[ToolReturn, Dict[str, Any]]:
        """
        Take a screenshot of the terminal browser.

        Returns the screenshot via ToolReturn with BinaryContent that you can
        see directly. Use this to see what's displayed in the terminal.

        Args:
            full_page: Capture full page (True) or just viewport (False).

        Returns:
            ToolReturn with the terminal screenshot you can analyze, or error dict.
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
    ) -> Union[ToolReturn, Dict[str, Any]]:
        """
        Load an image file so you can see and analyze it.

        Returns the image via ToolReturn with BinaryContent that you can
        see directly.

        Args:
            image_path: Path to the image file.

        Returns:
            ToolReturn with the image you can analyze, or error dict.
        """
        # Session is set by invoke_agent via contextvar
        return await load_image(image_path=image_path)


def register_terminal_compare_mockup(agent):
    """Register the mockup comparison tool."""

    @agent.tool
    async def terminal_compare_mockup(
        context: RunContext,
        mockup_path: str,
    ) -> Union[ToolReturn, Dict[str, Any]]:
        """
        Compare the terminal to a mockup image.

        Takes a screenshot of the terminal and loads the mockup image.
        Returns both via ToolReturn with BinaryContent so you can compare them.

        Args:
            mockup_path: Path to the mockup/expected image.

        Returns:
            ToolReturn with both images (terminal and mockup) you can compare.
        """
        # Session is set by invoke_agent via contextvar
        group_id = generate_group_id("terminal_compare_mockup", mockup_path)
        banner = format_terminal_banner("TERMINAL COMPARE MOCKUP 🖼️")
        emit_info(
            Text.from_markup(f"{banner} [bold cyan]{mockup_path}[/bold cyan]"),
            message_group=group_id,
        )

        # Capture terminal screenshot (get raw result for bytes)
        terminal_capture = await _capture_terminal_screenshot(
            full_page=False,
            save_to_disk=True,
            group_id=group_id,
        )
        if not terminal_capture["success"]:
            return terminal_capture

        # Load the mockup image
        mockup_file = Path(mockup_path)
        if not mockup_file.exists():
            error_msg = f"Mockup file not found: {mockup_path}"
            emit_error(error_msg, message_group=group_id)
            return {"success": False, "error": error_msg}

        mockup_bytes = _resize_image(mockup_file.read_bytes())

        emit_success(
            "Both images loaded. Compare them visually.",
            message_group=group_id,
        )

        terminal_path = terminal_capture.get("screenshot_path", "(not saved)")

        # Return as ToolReturn with BOTH images as BinaryContent!
        return ToolReturn(
            return_value=f"Comparison ready: terminal vs mockup ({mockup_path})",
            content=[
                "Here's the CURRENT terminal screenshot:",
                BinaryContent(
                    data=terminal_capture["screenshot_bytes"],
                    media_type="image/png",
                ),
                f"And here's the EXPECTED mockup ({mockup_file.name}):",
                BinaryContent(
                    data=mockup_bytes,
                    media_type="image/png",
                ),
                "Please compare these images and describe any differences.",
            ],
            metadata={
                "success": True,
                "terminal_path": terminal_path,
                "mockup_path": mockup_path,
                "timestamp": time.time(),
            },
        )
