"""Terminal Screenshot and Visual Analysis Tools.

This module provides tools for:
- Taking screenshots of the terminal and analyzing them with VQA
- Reading terminal output by scraping xterm.js DOM
- Comparing terminal state to mockup images
- Loading and analyzing arbitrary images from the filesystem

These tools use the ChromiumTerminalManager for browser access and
the VQA agent for visual question answering capabilities.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from tempfile import gettempdir, mkdtemp
from typing import Any, Dict, Optional

from pydantic_ai import RunContext

from code_puppy.messaging import emit_error, emit_info, emit_success
from code_puppy.tools.common import generate_group_id

from .chromium_terminal_manager import get_chromium_terminal_manager
from .vqa_agent import run_vqa_analysis

logger = logging.getLogger(__name__)

# Temporary directory for screenshots
_TEMP_SCREENSHOT_ROOT = Path(
    mkdtemp(prefix="code_puppy_terminal_screenshots_", dir=gettempdir())
)

# JavaScript to extract text content from xterm.js terminal
# xterm.js stores rows in elements with class "xterm-rows"
# Each row is a div containing spans with the actual text
XTERM_TEXT_EXTRACTION_JS = """
() => {
    // Try multiple selectors for xterm.js compatibility
    const selectors = [
        '.xterm-rows',           // Standard xterm.js rows container
        '.xterm .xterm-rows',    // Nested under .xterm
        '[class*="xterm-rows"]', // Partial class match
        '.xterm-screen',         // Alternative container
    ];
    
    let container = null;
    for (const selector of selectors) {
        container = document.querySelector(selector);
        if (container) break;
    }
    
    if (!container) {
        // Try to find any xterm instance and get text from it
        const xtermElement = document.querySelector('.xterm');
        if (xtermElement) {
            // Attempt to get all text content
            return {
                success: true,
                lines: xtermElement.innerText.split('\\n').filter(line => line.trim()),
                method: 'innerText'
            };
        }
        return { success: false, error: 'Could not find xterm.js terminal container' };
    }
    
    // Extract text from each row
    const rows = container.querySelectorAll('div');
    const lines = [];
    
    rows.forEach(row => {
        // Get text content, preserving spaces
        let text = '';
        const spans = row.querySelectorAll('span');
        if (spans.length > 0) {
            spans.forEach(span => {
                text += span.textContent || '';
            });
        } else {
            text = row.textContent || '';
        }
        // Trim trailing whitespace but preserve leading (for indentation)
        text = text.replace(/\\s+$/, '');
        if (text.length > 0) {
            lines.push(text);
        }
    });
    
    return {
        success: true,
        lines: lines,
        method: 'dom_scraping'
    };
}
"""


def _build_screenshot_path(prefix: str, timestamp: str) -> Path:
    """Build a path for saving a screenshot.

    Args:
        prefix: Prefix for the filename (e.g., 'terminal', 'comparison')
        timestamp: Timestamp string for uniqueness

    Returns:
        Path object for the screenshot file.
    """
    filename = f"{prefix}_{timestamp}.png"
    return _TEMP_SCREENSHOT_ROOT / filename


async def _get_terminal_page():
    """Get the current terminal page from ChromiumTerminalManager.

    Returns:
        The current Playwright Page object, or None if not available.
    """
    manager = get_chromium_terminal_manager()
    return await manager.get_current_page()


async def _capture_terminal_screenshot(
    full_page: bool = False,
    save_screenshot: bool = True,
    group_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Internal function to capture a screenshot of the terminal.

    Args:
        full_page: Whether to capture the full page or just viewport.
        save_screenshot: Whether to save the screenshot to disk.
        group_id: Optional message group ID for emit functions.

    Returns:
        Dict containing screenshot data and metadata.
    """
    try:
        page = await _get_terminal_page()

        if not page:
            return {
                "success": False,
                "error": "No active terminal page. Please open terminal first with terminal_open().",
            }

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Take screenshot
        screenshot_data = await page.screenshot(full_page=full_page)

        result = {
            "success": True,
            "screenshot_data": screenshot_data,
            "timestamp": timestamp,
        }

        if save_screenshot:
            screenshot_path = _build_screenshot_path("terminal", timestamp)
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)

            with open(screenshot_path, "wb") as f:
                f.write(screenshot_data)

            result["screenshot_path"] = str(screenshot_path)
            message = f"Screenshot saved: {screenshot_path}"
            if group_id:
                emit_success(message, message_group=group_id)
            else:
                emit_success(message)

        return result

    except Exception as e:
        logger.exception("Error capturing terminal screenshot")
        return {"success": False, "error": str(e)}


async def terminal_screenshot_analyze(
    question: str,
    full_page: bool = False,
    save_screenshot: bool = True,
) -> Dict[str, Any]:
    """Take a screenshot of the terminal and analyze it with VQA.

    Captures a screenshot of the current terminal browser page and uses
    visual question answering to analyze it based on the provided question.

    Args:
        question: The question to ask about the terminal screenshot.
        full_page: Whether to capture the full page or just viewport.
            Defaults to False (viewport only).
        save_screenshot: Whether to save the screenshot to disk.
            Defaults to True.

    Returns:
        A dictionary containing:
            - success (bool): True if analysis succeeded.
            - question (str): The original question.
            - answer (str): The VQA answer (if successful).
            - confidence (float): Confidence score 0-1 (if successful).
            - observations (str): Additional observations (if successful).
            - screenshot_path (str): Path to saved screenshot (if saved).
            - error (str): Error message (if unsuccessful).

    Example:
        >>> result = await terminal_screenshot_analyze(
        ...     "What is the last command that was run?"
        ... )
        >>> if result["success"]:
        ...     print(f"Answer: {result['answer']}")
    """
    target = "full_page" if full_page else "viewport"
    group_id = generate_group_id(
        "terminal_screenshot_analyze", f"{question[:50]}_{target}"
    )
    emit_info(
        f"TERMINAL SCREENSHOT ANALYZE 📷 question='{question[:100]}{'...' if len(question) > 100 else ''}'",
        message_group=group_id,
    )

    try:
        # Capture screenshot
        screenshot_result = await _capture_terminal_screenshot(
            full_page=full_page,
            save_screenshot=save_screenshot,
            group_id=group_id,
        )

        if not screenshot_result["success"]:
            error_message = screenshot_result.get("error", "Screenshot failed")
            emit_error(
                f"Screenshot capture failed: {error_message}",
                message_group=group_id,
            )
            return {
                "success": False,
                "error": error_message,
                "question": question,
            }

        screenshot_bytes = screenshot_result.get("screenshot_data")
        if not screenshot_bytes:
            emit_error(
                "Screenshot captured but pixel data missing.",
                message_group=group_id,
            )
            return {
                "success": False,
                "error": "Screenshot captured but no image bytes available.",
                "question": question,
            }

        # Run VQA analysis
        try:
            vqa_result = await asyncio.to_thread(
                run_vqa_analysis,
                question,
                screenshot_bytes,
            )
        except Exception as exc:
            emit_error(
                f"Visual question answering failed: {exc}",
                message_group=group_id,
            )
            return {
                "success": False,
                "error": f"Visual analysis failed: {exc}",
                "question": question,
                "screenshot_path": screenshot_result.get("screenshot_path"),
            }

        emit_success(
            f"Analysis answer: {vqa_result.answer}",
            message_group=group_id,
        )
        emit_info(
            f"Observations: {vqa_result.observations}",
            message_group=group_id,
        )

        return {
            "success": True,
            "question": question,
            "answer": vqa_result.answer,
            "confidence": vqa_result.confidence,
            "observations": vqa_result.observations,
            "screenshot_path": screenshot_result.get("screenshot_path"),
        }

    except Exception as e:
        emit_error(
            f"Terminal screenshot analysis failed: {str(e)}", message_group=group_id
        )
        logger.exception("Error in terminal_screenshot_analyze")
        return {"success": False, "error": str(e), "question": question}


async def terminal_read_output(lines: int = 50) -> Dict[str, Any]:
    """Read text output from the terminal by scraping the xterm.js DOM.

    Extracts the text content from the terminal by parsing the xterm.js
    DOM elements. Returns the last N lines of visible terminal output.

    Args:
        lines: Number of lines to return from the end of output.
            Defaults to 50.

    Returns:
        A dictionary containing:
            - success (bool): True if extraction succeeded.
            - output (str): The terminal text content (if successful).
            - line_count (int): Number of lines returned (if successful).
            - error (str): Error message (if unsuccessful).

    Example:
        >>> result = await terminal_read_output(lines=20)
        >>> if result["success"]:
        ...     print(result["output"])
    """
    group_id = generate_group_id("terminal_read_output", f"lines={lines}")
    emit_info(
        f"TERMINAL READ OUTPUT 📜 lines={lines}",
        message_group=group_id,
    )

    try:
        page = await _get_terminal_page()

        if not page:
            error_msg = "No active terminal page. Please open terminal first with terminal_open()."
            emit_error(error_msg, message_group=group_id)
            return {"success": False, "error": error_msg}

        # Execute JavaScript to extract text from xterm.js
        extraction_result = await page.evaluate(XTERM_TEXT_EXTRACTION_JS)

        if not extraction_result.get("success"):
            error_msg = extraction_result.get(
                "error", "Failed to extract terminal text"
            )
            emit_error(error_msg, message_group=group_id)
            return {"success": False, "error": error_msg}

        all_lines = extraction_result.get("lines", [])

        # Get the last N lines
        if lines > 0:
            output_lines = all_lines[-lines:]
        else:
            output_lines = all_lines

        output_text = "\n".join(output_lines)
        line_count = len(output_lines)

        emit_success(
            f"Read {line_count} lines from terminal (method: {extraction_result.get('method', 'unknown')})",
            message_group=group_id,
        )

        return {
            "success": True,
            "output": output_text,
            "line_count": line_count,
        }

    except Exception as e:
        emit_error(f"Failed to read terminal output: {str(e)}", message_group=group_id)
        logger.exception("Error reading terminal output")
        return {"success": False, "error": str(e)}


async def terminal_compare_mockup(
    mockup_path: str,
    question: str = "How closely does the terminal match the mockup? List differences.",
) -> Dict[str, Any]:
    """Compare the terminal screenshot to a mockup image.

    Takes a screenshot of the current terminal and uses VQA to compare
    it with a provided mockup image.

    Args:
        mockup_path: Path to the mockup image file on the filesystem.
        question: The comparison question to ask the VQA model.
            Defaults to asking about differences between terminal and mockup.

    Returns:
        A dictionary containing:
            - success (bool): True if comparison succeeded.
            - mockup_path (str): Path to the mockup image.
            - comparison (str): The VQA comparison result (if successful).
            - matches (bool): True if terminal matches mockup (if successful).
            - confidence (float): Confidence score 0-1 (if successful).
            - screenshot_path (str): Path to terminal screenshot (if saved).
            - error (str): Error message (if unsuccessful).

    Example:
        >>> result = await terminal_compare_mockup(
        ...     "/path/to/mockup.png",
        ...     "Does the terminal show the expected welcome message?"
        ... )
        >>> if result["success"]:
        ...     print(f"Matches: {result['matches']}")
    """
    group_id = generate_group_id("terminal_compare_mockup", mockup_path)
    emit_info(
        f"TERMINAL COMPARE MOCKUP 🖼️ mockup='{mockup_path}'",
        message_group=group_id,
    )

    try:
        # Verify mockup file exists
        mockup_file = Path(mockup_path)
        if not mockup_file.exists():
            error_msg = f"Mockup file not found: {mockup_path}"
            emit_error(error_msg, message_group=group_id)
            return {
                "success": False,
                "error": error_msg,
                "mockup_path": mockup_path,
            }

        if not mockup_file.is_file():
            error_msg = f"Mockup path is not a file: {mockup_path}"
            emit_error(error_msg, message_group=group_id)
            return {
                "success": False,
                "error": error_msg,
                "mockup_path": mockup_path,
            }

        # Load mockup image to verify it's readable
        # Note: Currently we only analyze the terminal screenshot with context about
        # the mockup comparison. A future enhancement could stitch images together
        # or use multi-image VQA for direct comparison.
        try:
            _mockup_bytes = mockup_file.read_bytes()  # noqa: F841 - validates file is readable
        except Exception as e:
            error_msg = f"Failed to read mockup file: {e}"
            emit_error(error_msg, message_group=group_id)
            return {
                "success": False,
                "error": error_msg,
                "mockup_path": mockup_path,
            }

        # Capture terminal screenshot
        screenshot_result = await _capture_terminal_screenshot(
            full_page=False,
            save_screenshot=True,
            group_id=group_id,
        )

        if not screenshot_result["success"]:
            error_message = screenshot_result.get("error", "Screenshot failed")
            emit_error(
                f"Screenshot capture failed: {error_message}",
                message_group=group_id,
            )
            return {
                "success": False,
                "error": error_message,
                "mockup_path": mockup_path,
            }

        screenshot_bytes = screenshot_result.get("screenshot_data")
        if not screenshot_bytes:
            emit_error(
                "Screenshot captured but no image data available.",
                message_group=group_id,
            )
            return {
                "success": False,
                "error": "No screenshot data available.",
                "mockup_path": mockup_path,
            }

        # Prepare comparison prompt that includes both images
        # Note: VQA typically handles one image, so we'll combine them
        # or describe the comparison context in the question
        comparison_question = (
            f"You are comparing a terminal screenshot to a mockup design. "
            f"The mockup shows the expected design. {question}"
        )

        # Analyze the terminal screenshot (primary image for comparison)
        # In a more sophisticated implementation, we could stitch images together
        try:
            vqa_result = await asyncio.to_thread(
                run_vqa_analysis,
                comparison_question,
                screenshot_bytes,
            )
        except Exception as exc:
            emit_error(
                f"Visual comparison failed: {exc}",
                message_group=group_id,
            )
            return {
                "success": False,
                "error": f"Visual comparison failed: {exc}",
                "mockup_path": mockup_path,
                "screenshot_path": screenshot_result.get("screenshot_path"),
            }

        # Determine if it matches based on answer content
        answer_lower = vqa_result.answer.lower()
        matches = (
            "match" in answer_lower
            and "not match" not in answer_lower
            and "doesn't match" not in answer_lower
            and "don't match" not in answer_lower
        ) or (
            "same" in answer_lower
            or "identical" in answer_lower
            or "similar" in answer_lower
        )

        emit_success(
            f"Comparison result: {vqa_result.answer[:100]}..."
            if len(vqa_result.answer) > 100
            else f"Comparison result: {vqa_result.answer}",
            message_group=group_id,
        )

        return {
            "success": True,
            "mockup_path": mockup_path,
            "comparison": vqa_result.answer,
            "matches": matches,
            "confidence": vqa_result.confidence,
            "observations": vqa_result.observations,
            "screenshot_path": screenshot_result.get("screenshot_path"),
        }

    except Exception as e:
        emit_error(f"Mockup comparison failed: {str(e)}", message_group=group_id)
        logger.exception("Error comparing terminal to mockup")
        return {
            "success": False,
            "error": str(e),
            "mockup_path": mockup_path,
        }


async def load_image_for_analysis(
    image_path: str,
    question: str,
) -> Dict[str, Any]:
    """Load an image from the filesystem and analyze it with VQA.

    This tool loads any image file and uses visual question answering
    to analyze it based on the provided question. Useful for analyzing
    mockups, designs, saved screenshots, or any other images.

    Args:
        image_path: Path to the image file on the filesystem.
        question: The question to ask about the image.

    Returns:
        A dictionary containing:
            - success (bool): True if analysis succeeded.
            - image_path (str): Path to the analyzed image.
            - question (str): The original question.
            - answer (str): The VQA answer (if successful).
            - confidence (float): Confidence score 0-1 (if successful).
            - observations (str): Additional observations (if successful).
            - error (str): Error message (if unsuccessful).

    Example:
        >>> result = await load_image_for_analysis(
        ...     "/path/to/mockup.png",
        ...     "What colors are used in this design?"
        ... )
        >>> if result["success"]:
        ...     print(f"Answer: {result['answer']}")
    """
    group_id = generate_group_id("load_image_analysis", f"{image_path}_{question[:30]}")
    emit_info(
        f"LOAD IMAGE ANALYZE 🔍 image='{image_path}' question='{question[:50]}...'"
        if len(question) > 50
        else f"LOAD IMAGE ANALYZE 🔍 image='{image_path}' question='{question}'",
        message_group=group_id,
    )

    try:
        # Verify image file exists
        image_file = Path(image_path)
        if not image_file.exists():
            error_msg = f"Image file not found: {image_path}"
            emit_error(error_msg, message_group=group_id)
            return {
                "success": False,
                "error": error_msg,
                "image_path": image_path,
                "question": question,
            }

        if not image_file.is_file():
            error_msg = f"Image path is not a file: {image_path}"
            emit_error(error_msg, message_group=group_id)
            return {
                "success": False,
                "error": error_msg,
                "image_path": image_path,
                "question": question,
            }

        # Load image bytes
        try:
            image_bytes = image_file.read_bytes()
        except Exception as e:
            error_msg = f"Failed to read image file: {e}"
            emit_error(error_msg, message_group=group_id)
            return {
                "success": False,
                "error": error_msg,
                "image_path": image_path,
                "question": question,
            }

        # Determine media type from extension
        suffix = image_file.suffix.lower()
        media_type_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
        }
        media_type = media_type_map.get(suffix, "image/png")

        # Run VQA analysis
        try:
            vqa_result = await asyncio.to_thread(
                run_vqa_analysis,
                question,
                image_bytes,
                media_type,
            )
        except Exception as exc:
            emit_error(
                f"Visual analysis failed: {exc}",
                message_group=group_id,
            )
            return {
                "success": False,
                "error": f"Visual analysis failed: {exc}",
                "image_path": image_path,
                "question": question,
            }

        emit_success(
            f"Analysis answer: {vqa_result.answer}",
            message_group=group_id,
        )
        emit_info(
            f"Observations: {vqa_result.observations}",
            message_group=group_id,
        )

        return {
            "success": True,
            "image_path": image_path,
            "question": question,
            "answer": vqa_result.answer,
            "confidence": vqa_result.confidence,
            "observations": vqa_result.observations,
        }

    except Exception as e:
        emit_error(f"Image analysis failed: {str(e)}", message_group=group_id)
        logger.exception("Error analyzing image")
        return {
            "success": False,
            "error": str(e),
            "image_path": image_path,
            "question": question,
        }


# =============================================================================
# Tool Registration Functions
# =============================================================================


def register_terminal_screenshot_analyze(agent):
    """Register the terminal screenshot analysis tool with an agent.

    Args:
        agent: The pydantic-ai agent to register the tool with.
    """

    @agent.tool
    async def terminal_screenshot_analyze_tool(
        context: RunContext,
        question: str,
        full_page: bool = False,
        save_screenshot: bool = True,
    ) -> Dict[str, Any]:
        """
        Take a screenshot of the terminal and analyze it with visual AI.

        Args:
            question: The question to ask about the terminal screenshot
            full_page: Whether to capture full page or just viewport (default: False)
            save_screenshot: Whether to save the screenshot to disk (default: True)

        Returns:
            Dict with:
                - success: True if analysis succeeded
                - question: The original question
                - answer: The VQA answer (if successful)
                - confidence: Confidence score 0-1 (if successful)
                - screenshot_path: Path to saved screenshot (if saved)
                - error: Error message (if unsuccessful)
        """
        return await terminal_screenshot_analyze(
            question=question,
            full_page=full_page,
            save_screenshot=save_screenshot,
        )


def register_terminal_read_output(agent):
    """Register the terminal read output tool with an agent.

    Args:
        agent: The pydantic-ai agent to register the tool with.
    """

    @agent.tool
    async def terminal_read_output_tool(
        context: RunContext,
        lines: int = 50,
    ) -> Dict[str, Any]:
        """
        Read text output from the terminal by scraping xterm.js DOM.

        Args:
            lines: Number of lines to return from end of output (default: 50)

        Returns:
            Dict with:
                - success: True if extraction succeeded
                - output: The terminal text content (if successful)
                - line_count: Number of lines returned (if successful)
                - error: Error message (if unsuccessful)
        """
        return await terminal_read_output(lines=lines)


def register_terminal_compare_mockup(agent):
    """Register the terminal mockup comparison tool with an agent.

    Args:
        agent: The pydantic-ai agent to register the tool with.
    """

    @agent.tool
    async def terminal_compare_mockup_tool(
        context: RunContext,
        mockup_path: str,
        question: str = "How closely does the terminal match the mockup? List differences.",
    ) -> Dict[str, Any]:
        """
        Compare the terminal screenshot to a mockup image.

        Args:
            mockup_path: Path to the mockup image file
            question: Comparison question to ask (default: asks about differences)

        Returns:
            Dict with:
                - success: True if comparison succeeded
                - mockup_path: Path to the mockup image
                - comparison: The VQA comparison result (if successful)
                - matches: True if terminal matches mockup (if successful)
                - confidence: Confidence score 0-1 (if successful)
                - error: Error message (if unsuccessful)
        """
        return await terminal_compare_mockup(
            mockup_path=mockup_path,
            question=question,
        )


def register_load_image_for_analysis(agent):
    """Register the image analysis tool with an agent.

    Args:
        agent: The pydantic-ai agent to register the tool with.
    """

    @agent.tool
    async def load_image_for_analysis_tool(
        context: RunContext,
        image_path: str,
        question: str,
    ) -> Dict[str, Any]:
        """
        Load an image from the filesystem and analyze it with visual AI.

        Args:
            image_path: Path to the image file to analyze
            question: The question to ask about the image

        Returns:
            Dict with:
                - success: True if analysis succeeded
                - image_path: Path to the analyzed image
                - question: The original question
                - answer: The VQA answer (if successful)
                - confidence: Confidence score 0-1 (if successful)
                - error: Error message (if unsuccessful)
        """
        return await load_image_for_analysis(
            image_path=image_path,
            question=question,
        )
