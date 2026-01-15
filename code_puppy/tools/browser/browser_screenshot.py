"""Screenshot tool for browser automation.

Captures screenshots and returns them via ToolReturn with BinaryContent
so multimodal models can directly see and analyze - no separate VQA agent needed.
"""

import time
from datetime import datetime
from pathlib import Path
from tempfile import gettempdir, mkdtemp
from typing import Any, Dict, Optional, Union

from pydantic_ai import BinaryContent, RunContext, ToolReturn

from code_puppy.messaging import emit_error, emit_info, emit_success
from code_puppy.tools.common import generate_group_id

from .camoufox_manager import get_session_browser_manager

_TEMP_SCREENSHOT_ROOT = Path(
    mkdtemp(prefix="code_puppy_screenshots_", dir=gettempdir())
)


def _build_screenshot_path(timestamp: str) -> Path:
    """Return the target path for a screenshot."""
    filename = f"screenshot_{timestamp}.png"
    return _TEMP_SCREENSHOT_ROOT / filename


async def _capture_screenshot(
    page,
    full_page: bool = False,
    element_selector: Optional[str] = None,
    save_screenshot: bool = True,
    group_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Internal screenshot capture function."""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

        # Take screenshot
        if element_selector:
            element = await page.locator(element_selector).first
            if not await element.is_visible():
                return {
                    "success": False,
                    "error": f"Element '{element_selector}' is not visible",
                }
            screenshot_bytes = await element.screenshot()
        else:
            screenshot_bytes = await page.screenshot(full_page=full_page)

        result: Dict[str, Any] = {
            "success": True,
            "screenshot_bytes": screenshot_bytes,
            "timestamp": timestamp,
        }

        if save_screenshot:
            screenshot_path = _build_screenshot_path(timestamp)
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            with open(screenshot_path, "wb") as f:
                f.write(screenshot_bytes)
            result["screenshot_path"] = str(screenshot_path)

            if group_id:
                emit_success(
                    f"Screenshot saved: {screenshot_path}", message_group=group_id
                )

        return result

    except Exception as e:
        return {"success": False, "error": str(e)}


async def take_screenshot(
    full_page: bool = False,
    element_selector: Optional[str] = None,
    save_screenshot: bool = True,
) -> Union[ToolReturn, Dict[str, Any]]:
    """Take a screenshot of the browser page.

    Returns a ToolReturn with BinaryContent so multimodal models can
    directly see and analyze the screenshot.

    Args:
        full_page: Whether to capture full page or just viewport.
        element_selector: Optional selector to screenshot specific element.
        save_screenshot: Whether to save the screenshot to disk.

    Returns:
        ToolReturn containing:
            - return_value: Success message with screenshot path
            - content: List with description and BinaryContent image
            - metadata: Screenshot details (path, target, timestamp)
        Or Dict with error info if failed.
    """
    target = element_selector or ("full_page" if full_page else "viewport")
    group_id = generate_group_id("browser_screenshot", target)
    emit_info(f"BROWSER SCREENSHOT 📷 target={target}", message_group=group_id)

    try:
        browser_manager = get_session_browser_manager()
        page = await browser_manager.get_current_page()

        if not page:
            error_msg = "No active browser page. Navigate to a webpage first."
            emit_error(error_msg, message_group=group_id)
            return {"success": False, "error": error_msg}

        result = await _capture_screenshot(
            page,
            full_page=full_page,
            element_selector=element_selector,
            save_screenshot=save_screenshot,
            group_id=group_id,
        )

        if not result["success"]:
            emit_error(result.get("error", "Screenshot failed"), message_group=group_id)
            return {"success": False, "error": result.get("error")}

        screenshot_path = result.get("screenshot_path", "(not saved)")

        # Return as ToolReturn with BinaryContent so the model can SEE the image!
        return ToolReturn(
            return_value=f"Screenshot captured successfully. Saved to: {screenshot_path}",
            content=[
                f"Here's the browser screenshot ({target}):",
                BinaryContent(
                    data=result["screenshot_bytes"],
                    media_type="image/png",
                ),
                "Please analyze what you see and describe any relevant details.",
            ],
            metadata={
                "success": True,
                "screenshot_path": screenshot_path,
                "target": target,
                "full_page": full_page,
                "element_selector": element_selector,
                "timestamp": time.time(),
            },
        )

    except Exception as e:
        error_msg = f"Screenshot failed: {str(e)}"
        emit_error(error_msg, message_group=group_id)
        return {"success": False, "error": error_msg}


def register_take_screenshot_and_analyze(agent):
    """Register the screenshot tool."""

    @agent.tool
    async def browser_screenshot_analyze(
        context: RunContext,
        full_page: bool = False,
        element_selector: Optional[str] = None,
    ) -> Union[ToolReturn, Dict[str, Any]]:
        """
        Take a screenshot of the browser page.

        Returns the screenshot via ToolReturn with BinaryContent that you can
        see directly. Use this to see what's displayed in the browser.

        Args:
            full_page: Capture full page (True) or just viewport (False).
            element_selector: Optional CSS selector to screenshot specific element.

        Returns:
            ToolReturn with the screenshot image you can analyze, or error dict.
        """
        return await take_screenshot(
            full_page=full_page,
            element_selector=element_selector,
        )
