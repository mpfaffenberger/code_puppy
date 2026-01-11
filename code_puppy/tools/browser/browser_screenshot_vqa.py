"""VQA-based Screenshot tool for browser automation (qa-kitten).

This module provides screenshot analysis using a dedicated VQA agent.
Unlike browser_screenshot.py which returns raw base64 bytes for multimodal
models to see directly, this version offloads the visual analysis to a
separate VQA agent, helping manage context in the calling agent.

Use this for qa-kitten where context management is important.
Use browser_screenshot.py for terminal-qa where direct image viewing is needed.
"""

import asyncio
from typing import Any, Dict, Optional

from pydantic_ai import RunContext

from code_puppy.messaging import emit_error, emit_info, emit_success
from code_puppy.tools.common import generate_group_id

from .browser_screenshot import _capture_screenshot
from .camoufox_manager import get_camoufox_manager
from .vqa_agent import run_vqa_analysis


async def take_screenshot_and_analyze(
    question: str,
    full_page: bool = False,
    element_selector: Optional[str] = None,
    save_screenshot: bool = True,
) -> Dict[str, Any]:
    """Take a screenshot and analyze it using the VQA agent.

    This function captures a screenshot and passes it to a dedicated
    VQA (Visual Question Answering) agent for analysis. The VQA agent
    runs separately, keeping the image analysis out of the calling
    agent's context window.

    Args:
        question: The question to ask about the screenshot.
            Examples:
            - "What buttons are visible on this page?"
            - "Is there an error message displayed?"
            - "What is the main heading text?"
            - "Describe the layout of this form."
        full_page: Whether to capture full page or just viewport.
            Defaults to False (viewport only).
        element_selector: Optional CSS selector to screenshot a specific
            element instead of the whole page.
        save_screenshot: Whether to save the screenshot to disk.

    Returns:
        Dict containing:
            - success (bool): True if analysis succeeded.
            - answer (str): The VQA agent's answer to your question.
            - confidence (float): Confidence level from 0.0 to 1.0.
            - observations (str): Additional visual observations.
            - screenshot_info (dict): Path, timestamp, and other metadata.
            - error (str): Error message if unsuccessful.
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
        # Get the browser page
        browser_manager = get_camoufox_manager()
        page = await browser_manager.get_current_page()

        if not page:
            error_msg = "No active browser page. Navigate to a webpage first."
            emit_error(error_msg, message_group=group_id)
            return {"success": False, "error": error_msg, "question": question}

        # Capture the screenshot
        screenshot_result = await _capture_screenshot(
            page,
            full_page=full_page,
            element_selector=element_selector,
            save_screenshot=save_screenshot,
            group_id=group_id,
        )

        if not screenshot_result["success"]:
            error_msg = screenshot_result.get("error", "Screenshot failed")
            emit_error(
                f"Screenshot capture failed: {error_msg}", message_group=group_id
            )
            return {"success": False, "error": error_msg, "question": question}

        screenshot_bytes = screenshot_result.get("screenshot_bytes")
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

        # Run VQA analysis in a thread to not block the event loop
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
        error_msg = f"Screenshot analysis failed: {str(e)}"
        emit_error(error_msg, message_group=group_id)
        return {"success": False, "error": error_msg, "question": question}


def register_take_screenshot_and_analyze_vqa(agent):
    """Register the VQA-based screenshot tool.

    This tool takes a screenshot and analyzes it using a separate VQA agent.
    Use this for agents where context management is important (like qa-kitten).
    """

    @agent.tool
    async def browser_screenshot_vqa(
        context: RunContext,
        question: str,
        full_page: bool = False,
        element_selector: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Take a screenshot and analyze it with VQA.

        Captures a screenshot of the browser and uses a visual AI to
        answer your question about what's visible on the page.

        Args:
            question: What you want to know about the screenshot.
                Examples:
                - "What buttons are visible?"
                - "Is there an error message?"
                - "What is the page title?"
                - "Is the form filled out correctly?"
            full_page: Capture full page (True) or just viewport (False).
            element_selector: Optional CSS selector to screenshot specific element.

        Returns:
            Dict with:
            - answer: The answer to your question
            - confidence: How confident the AI is (0.0 to 1.0)
            - observations: Additional things noticed in the image
            - screenshot_info: Where the screenshot was saved, etc.
        """
        return await take_screenshot_and_analyze(
            question=question,
            full_page=full_page,
            element_selector=element_selector,
        )
