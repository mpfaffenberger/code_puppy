"""Screenshot and visual analysis tool with VQA capabilities."""

import asyncio
from datetime import datetime
from pathlib import Path
from tempfile import gettempdir, mkdtemp
from typing import Any, Dict, Optional

from pydantic import BaseModel
from pydantic_ai import RunContext

from code_puppy.messaging import emit_error, emit_info, emit_success
from code_puppy.tools.common import generate_group_id

from .camoufox_manager import get_camoufox_manager
from .vqa_agent import run_vqa_analysis

_TEMP_SCREENSHOT_ROOT = Path(
    mkdtemp(prefix="code_puppy_screenshots_", dir=gettempdir())
)


def _build_screenshot_path(timestamp: str) -> Path:
    """Return the target path for a screenshot using a shared temp directory."""
    filename = f"screenshot_{timestamp}.png"
    return _TEMP_SCREENSHOT_ROOT / filename


class ScreenshotResult(BaseModel):
    """Result from screenshot operation."""

    success: bool
    screenshot_path: Optional[str] = None
    screenshot_data: Optional[bytes] = None
    timestamp: Optional[str] = None
    error: Optional[str] = None


async def _capture_screenshot(
    page,
    full_page: bool = False,
    element_selector: Optional[str] = None,
    save_screenshot: bool = True,
    group_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Internal screenshot capture function."""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Take screenshot
        if element_selector:
            # Screenshot specific element
            element = await page.locator(element_selector).first
            if not await element.is_visible():
                return {
                    "success": False,
                    "error": f"Element '{element_selector}' is not visible",
                }
            screenshot_data = await element.screenshot()
        else:
            # Screenshot page or full page
            screenshot_data = await page.screenshot(full_page=full_page)

        result = {
            "success": True,
            "screenshot_data": screenshot_data,
            "timestamp": timestamp,
        }

        if save_screenshot:
            screenshot_path = _build_screenshot_path(timestamp)
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
        return {"success": False, "error": str(e)}


async def take_screenshot_and_analyze(
    question: str,
    full_page: bool = False,
    element_selector: Optional[str] = None,
    save_screenshot: bool = True,
) -> Dict[str, Any]:
    """
    Take a screenshot and analyze it using visual understanding.

    Args:
        question: The specific question to ask about the screenshot
        full_page: Whether to capture the full page or just viewport
        element_selector: Optional selector to screenshot just a specific element
        save_screenshot: Whether to save the screenshot to disk

    Returns:
        Dict containing analysis results and screenshot info
    """
    target = element_selector or ("full_page" if full_page else "viewport")
    group_id = generate_group_id(
        "browser_screenshot_analyze", f"{question[:50]}_{target}"
    )
    emit_info(
        f"BROWSER SCREENSHOT ANALYZE 📷 question='{question[:100]}{'...' if len(question) > 100 else ''}' target={target}",
        message_group=group_id,
    )
    try:
        # Get the current browser page
        browser_manager = get_camoufox_manager()
        page = await browser_manager.get_current_page()

        if not page:
            return {
                "success": False,
                "error": "No active browser page available. Please navigate to a webpage first.",
                "question": question,
            }

        # Take screenshot
        screenshot_result = await _capture_screenshot(
            page,
            full_page=full_page,
            element_selector=element_selector,
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
                "Screenshot captured but pixel data missing; cannot run visual analysis.",
                message_group=group_id,
            )
            return {
                "success": False,
                "error": "Screenshot captured but no image bytes available for analysis.",
                "question": question,
            }

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
                "screenshot_info": {
                    "path": screenshot_result.get("screenshot_path"),
                    "timestamp": screenshot_result.get("timestamp"),
                    "full_page": full_page,
                    "element_selector": element_selector,
                },
            }

        emit_success(
            f"Visual analysis answer: {vqa_result.answer}",
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
            "screenshot_info": {
                "path": screenshot_result.get("screenshot_path"),
                "size": len(screenshot_bytes),
                "timestamp": screenshot_result.get("timestamp"),
                "full_page": full_page,
                "element_selector": element_selector,
            },
        }

    except Exception as e:
        emit_error(f"Screenshot analysis failed: {str(e)}", message_group=group_id)
        return {"success": False, "error": str(e), "question": question}


def register_take_screenshot_and_analyze(agent):
    """Register the screenshot analysis tool."""

    @agent.tool
    async def browser_screenshot_analyze(
        context: RunContext,
        question: str,
        full_page: bool = False,
        element_selector: Optional[str] = None,
        save_screenshot: bool = True,
    ) -> Dict[str, Any]:
        """
        Take a screenshot and analyze it to answer a specific question.

        Args:
            question: The specific question to ask about the screenshot
            full_page: Whether to capture the full page or just viewport
            element_selector: Optional CSS/XPath selector to screenshot specific element
            save_screenshot: Whether to save the screenshot to disk

        Returns:
            Dict with analysis results including answer, confidence, and observations
        """
        return await take_screenshot_and_analyze(
            question=question,
            full_page=full_page,
            element_selector=element_selector,
            save_screenshot=save_screenshot,
        )
