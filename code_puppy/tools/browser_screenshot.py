"""Screenshot and visual analysis tool with VQA capabilities."""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel
from pydantic_ai import RunContext

from code_puppy.messaging import emit_info
from code_puppy.tools.common import generate_group_id

from .camoufox_manager import get_camoufox_manager


class VisualAnalysisResult(BaseModel):
    """Result from visual analysis."""

    answer: str
    confidence: float
    observations: str


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

        # Save to disk if requested
        if save_screenshot:
            screenshot_dir = Path("screenshots")
            screenshot_dir.mkdir(exist_ok=True)

            filename = f"screenshot_{timestamp}.png"
            screenshot_path = screenshot_dir / filename

            with open(screenshot_path, "wb") as f:
                f.write(screenshot_data)

            result["screenshot_path"] = str(screenshot_path)
            if group_id:
                emit_info(
                    f"[green]Screenshot saved: {screenshot_path}[/green]",
                    message_group=group_id,
                )
            else:
                emit_info(f"[green]Screenshot saved: {screenshot_path}[/green]")

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
        f"[bold white on blue] BROWSER SCREENSHOT ANALYZE [/bold white on blue] 📷 question='{question[:100]}{'...' if len(question) > 100 else ''}' target={target}",
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
            return {
                "success": False,
                "error": screenshot_result.get("error", "Screenshot failed"),
                "question": question,
            }

        # For now, return screenshot info without VQA analysis
        # VQA would require integration with vision models
        emit_info(
            f"[yellow]Screenshot captured for question: {question}[/yellow]",
            message_group=group_id,
        )
        emit_info(
            "[dim]Note: Visual question answering requires vision model integration[/dim]"
        )

        return {
            "success": True,
            "question": question,
            "answer": "Screenshot captured successfully. Visual analysis requires vision model integration.",
            "confidence": 1.0,
            "observations": "Screenshot taken and saved to disk.",
            "screenshot_info": {
                "path": screenshot_result.get("screenshot_path"),
                "size": len(screenshot_result["screenshot_data"])
                if screenshot_result["screenshot_data"]
                else 0,
                "timestamp": screenshot_result.get("timestamp"),
                "full_page": full_page,
                "element_selector": element_selector,
            },
        }

    except Exception as e:
        emit_info(
            f"[red]Screenshot analysis failed: {str(e)}[/red]", message_group=group_id
        )
        return {"success": False, "error": str(e), "question": question}


async def simple_screenshot(
    full_page: bool = False,
    element_selector: Optional[str] = None,
    save_screenshot: bool = True,
) -> Dict[str, Any]:
    """
    Take a simple screenshot without analysis.

    Args:
        full_page: Whether to capture the full page or just viewport
        element_selector: Optional selector to screenshot just a specific element
        save_screenshot: Whether to save the screenshot to disk

    Returns:
        Dict containing screenshot info
    """
    target = element_selector or ("full_page" if full_page else "viewport")
    group_id = generate_group_id("browser_screenshot", target)
    emit_info(
        f"[bold white on blue] BROWSER SCREENSHOT [/bold white on blue] 📷 target={target} save={save_screenshot}",
        message_group=group_id,
    )
    try:
        browser_manager = get_camoufox_manager()
        page = await browser_manager.get_current_page()

        if not page:
            return {"success": False, "error": "No active browser page available"}

        screenshot_result = await _capture_screenshot(
            page,
            full_page=full_page,
            element_selector=element_selector,
            save_screenshot=save_screenshot,
            group_id=group_id,
        )

        return screenshot_result

    except Exception as e:
        return {"success": False, "error": str(e)}


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


def register_simple_screenshot(agent):
    """Register the simple screenshot tool."""

    @agent.tool
    async def browser_simple_screenshot(
        context: RunContext,
        full_page: bool = False,
        element_selector: Optional[str] = None,
        save_screenshot: bool = True,
    ) -> Dict[str, Any]:
        """
        Take a simple screenshot without analysis.

        Args:
            full_page: Whether to capture the full page or just viewport
            element_selector: Optional CSS/XPath selector to screenshot specific element
            save_screenshot: Whether to save the screenshot to disk

        Returns:
            Dict with screenshot info including path and metadata
        """
        return await simple_screenshot(
            full_page=full_page,
            element_selector=element_selector,
            save_screenshot=save_screenshot,
        )
