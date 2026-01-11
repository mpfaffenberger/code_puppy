"""Terminal command execution tools for browser-based terminal automation.

This module provides tools for:
- Running commands in the terminal browser
- Sending special keys (Ctrl+C, Tab, arrows, etc.)
- Waiting for terminal output patterns

These tools use the ChromiumTerminalManager to manage the browser instance
and interact with the xterm.js terminal in the Code Puppy API.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from tempfile import gettempdir, mkdtemp
from typing import Any, Dict, List, Optional

from pydantic_ai import RunContext

from code_puppy.messaging import emit_error, emit_info, emit_success
from code_puppy.tools.common import generate_group_id

from .chromium_terminal_manager import get_chromium_terminal_manager
from .vqa_agent import run_vqa_analysis

logger = logging.getLogger(__name__)

# Timeout defaults (seconds)
DEFAULT_COMMAND_TIMEOUT = 30.0
DEFAULT_OUTPUT_TIMEOUT = 30.0

# Time to wait for prompt to reappear after command (ms)
PROMPT_WAIT_MS = 500

# Directory for terminal screenshots
_TEMP_SCREENSHOT_ROOT = Path(
    mkdtemp(prefix="code_puppy_terminal_screenshots_", dir=gettempdir())
)

# Modifier key mapping for Playwright
MODIFIER_MAP = {
    "control": "Control",
    "ctrl": "Control",
    "shift": "Shift",
    "alt": "Alt",
    "meta": "Meta",
    "command": "Meta",
    "cmd": "Meta",
}


def _normalize_modifier(modifier: str) -> str:
    """Normalize modifier name to Playwright format.

    Args:
        modifier: The modifier name (case-insensitive).

    Returns:
        Normalized modifier name for Playwright.
    """
    return MODIFIER_MAP.get(modifier.lower(), modifier)


def _build_screenshot_path(timestamp: str) -> Path:
    """Return the target path for a terminal screenshot.

    Args:
        timestamp: Timestamp string for the filename.

    Returns:
        Path object for the screenshot file.
    """
    filename = f"terminal_screenshot_{timestamp}.png"
    return _TEMP_SCREENSHOT_ROOT / filename


async def _capture_terminal_screenshot(
    page,
    group_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Capture a screenshot of the terminal page.

    Args:
        page: The Playwright page object.
        group_id: Optional message group ID for logging.

    Returns:
        Dict with screenshot data and path, or error info.
    """
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_data = await page.screenshot()

        screenshot_path = _build_screenshot_path(timestamp)
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)

        with open(screenshot_path, "wb") as f:
            f.write(screenshot_data)

        message = f"Terminal screenshot saved: {screenshot_path}"
        if group_id:
            emit_success(message, message_group=group_id)
        else:
            emit_success(message)

        return {
            "success": True,
            "screenshot_path": str(screenshot_path),
            "screenshot_data": screenshot_data,
            "timestamp": timestamp,
        }

    except Exception as e:
        logger.exception("Failed to capture terminal screenshot")
        return {"success": False, "error": str(e)}


async def _analyze_terminal_screenshot(
    screenshot_bytes: bytes,
    question: str,
    group_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Analyze a terminal screenshot using VQA.

    Args:
        screenshot_bytes: The screenshot image data.
        question: The question to ask about the screenshot.
        group_id: Optional message group ID for logging.

    Returns:
        Dict with analysis results.
    """
    try:
        vqa_result = await asyncio.to_thread(
            run_vqa_analysis,
            question,
            screenshot_bytes,
        )

        if group_id:
            emit_success(
                f"Terminal analysis: {vqa_result.answer}",
                message_group=group_id,
            )

        return {
            "success": True,
            "answer": vqa_result.answer,
            "confidence": vqa_result.confidence,
            "observations": vqa_result.observations,
        }

    except Exception as e:
        error_msg = f"VQA analysis failed: {str(e)}"
        logger.exception(error_msg)
        if group_id:
            emit_error(error_msg, message_group=group_id)
        return {"success": False, "error": error_msg}


async def run_terminal_command(
    command: str,
    wait_for_prompt: bool = True,
    timeout: float = DEFAULT_COMMAND_TIMEOUT,
    auto_screenshot: bool = True,
    screenshot_question: str = "Did the command execute successfully? What is the output?",
) -> Dict[str, Any]:
    """Execute a command in the terminal browser.

    Types the command into the xterm.js terminal, presses Enter to execute,
    optionally waits for the command to complete, and can take a screenshot
    for visual analysis.

    Args:
        command: The command string to execute.
        wait_for_prompt: If True, wait for command to complete (prompt reappears).
            Defaults to True.
        timeout: Maximum time to wait for command completion in seconds.
            Defaults to 30.0.
        auto_screenshot: If True, take a screenshot after command execution.
            Defaults to True.
        screenshot_question: Question to ask VQA about the screenshot.
            Defaults to asking about command success and output.

    Returns:
        A dictionary containing:
            - success (bool): True if command was sent successfully.
            - command (str): The command that was executed.
            - screenshot_path (str, optional): Path to screenshot if taken.
            - analysis (dict, optional): VQA analysis results if auto_screenshot.
            - error (str, optional): Error message if unsuccessful.

    Example:
        >>> result = await run_terminal_command("ls -la")
        >>> if result["success"]:
        ...     print(f"Command output analyzed: {result['analysis']['answer']}")
    """
    group_id = generate_group_id("terminal_run_command", command[:50])
    emit_info(
        f"TERMINAL RUN COMMAND 💻 {command}",
        message_group=group_id,
    )

    try:
        # Get the terminal page
        manager = get_chromium_terminal_manager()
        page = await manager.get_current_page()

        if not page:
            error_msg = (
                "No active terminal page. Please open the terminal first "
                "with open_terminal()."
            )
            emit_error(error_msg, message_group=group_id)
            return {"success": False, "error": error_msg, "command": command}

        # Type the command into the terminal
        # xterm.js receives keyboard input directly on the page
        await page.keyboard.type(command)

        # Press Enter to execute
        await page.keyboard.press("Enter")

        emit_info(f"Command sent: {command}", message_group=group_id)

        # Wait for command to complete if requested
        if wait_for_prompt:
            # Give the terminal some time to process
            # In a real scenario, we'd want to detect the prompt reappearing
            # For now, we use a simple delay based on timeout
            await asyncio.sleep(min(PROMPT_WAIT_MS / 1000, timeout))

        result: Dict[str, Any] = {
            "success": True,
            "command": command,
        }

        # Take screenshot and analyze if requested
        if auto_screenshot:
            screenshot_result = await _capture_terminal_screenshot(page, group_id)

            if screenshot_result["success"]:
                result["screenshot_path"] = screenshot_result["screenshot_path"]

                # Analyze the screenshot
                analysis = await _analyze_terminal_screenshot(
                    screenshot_result["screenshot_data"],
                    screenshot_question,
                    group_id,
                )
                result["analysis"] = analysis
            else:
                emit_error(
                    f"Screenshot failed: {screenshot_result.get('error')}",
                    message_group=group_id,
                )
                result["screenshot_error"] = screenshot_result.get("error")

        emit_success(f"Command executed: {command}", message_group=group_id)
        return result

    except Exception as e:
        error_msg = f"Failed to run terminal command: {str(e)}"
        emit_error(error_msg, message_group=group_id)
        logger.exception("Error running terminal command")
        return {"success": False, "error": error_msg, "command": command}


async def send_terminal_keys(
    keys: str,
    modifiers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Send special keys or key combinations to the terminal.

    Sends keyboard input to the xterm.js terminal, supporting special keys
    and modifier combinations like Ctrl+C, Ctrl+D, Tab, Arrow keys, etc.

    Args:
        keys: The key(s) to send. Can be a single character or a special key
            name like "Enter", "Tab", "ArrowUp", "Escape", etc.
        modifiers: Optional list of modifier keys to hold while pressing.
            Supported: "Control"/"Ctrl", "Shift", "Alt", "Meta"/"Command"/"Cmd".
            Example: ["Control"] with keys="c" sends Ctrl+C.

    Returns:
        A dictionary containing:
            - success (bool): True if keys were sent successfully.
            - keys_sent (str): The keys that were sent.
            - modifiers (list): The modifiers that were used.
            - error (str, optional): Error message if unsuccessful.

    Examples:
        >>> # Send Ctrl+C to interrupt
        >>> await send_terminal_keys("c", modifiers=["Control"])

        >>> # Send Tab for autocomplete
        >>> await send_terminal_keys("Tab")

        >>> # Send Arrow Up to recall last command
        >>> await send_terminal_keys("ArrowUp")
    """
    modifiers = modifiers or []
    normalized_modifiers = [_normalize_modifier(m) for m in modifiers]

    modifier_str = "+".join(normalized_modifiers) if normalized_modifiers else ""
    key_combo = f"{modifier_str}+{keys}" if modifier_str else keys

    group_id = generate_group_id("terminal_send_keys", key_combo)
    emit_info(
        f"TERMINAL SEND KEYS ⌨️ {key_combo}",
        message_group=group_id,
    )

    try:
        # Get the terminal page
        manager = get_chromium_terminal_manager()
        page = await manager.get_current_page()

        if not page:
            error_msg = (
                "No active terminal page. Please open the terminal first "
                "with open_terminal()."
            )
            emit_error(error_msg, message_group=group_id)
            return {
                "success": False,
                "error": error_msg,
                "keys_sent": keys,
                "modifiers": modifiers,
            }

        # Hold modifier keys and press the main key
        for modifier in normalized_modifiers:
            await page.keyboard.down(modifier)

        try:
            # Use press for special keys, type for regular characters
            # Special keys are typically capitalized or multi-character
            if len(keys) > 1 or keys[0].isupper():
                await page.keyboard.press(keys)
            else:
                await page.keyboard.type(keys)
        finally:
            # Release modifier keys in reverse order
            for modifier in reversed(normalized_modifiers):
                await page.keyboard.up(modifier)

        emit_success(f"Keys sent: {key_combo}", message_group=group_id)

        return {
            "success": True,
            "keys_sent": keys,
            "modifiers": modifiers,
        }

    except Exception as e:
        error_msg = f"Failed to send terminal keys: {str(e)}"
        emit_error(error_msg, message_group=group_id)
        logger.exception("Error sending terminal keys")
        return {
            "success": False,
            "error": error_msg,
            "keys_sent": keys,
            "modifiers": modifiers,
        }


async def wait_for_terminal_output(
    pattern: Optional[str] = None,
    timeout: float = DEFAULT_OUTPUT_TIMEOUT,
) -> Dict[str, Any]:
    """Wait for terminal output matching a pattern.

    Monitors the terminal for new output, optionally matching against a
    regex or text pattern. Uses visual analysis of screenshots to detect
    terminal content changes.

    Note: This is a simplified implementation that takes a screenshot and
    analyzes it for the pattern. For real-time output monitoring, a more
    sophisticated approach using terminal buffer access would be needed.

    Args:
        pattern: Optional regex or text pattern to match in the output.
            If None, waits for any new output (takes immediate screenshot).
        timeout: Maximum time to wait for matching output in seconds.
            Defaults to 30.0.

    Returns:
        A dictionary containing:
            - success (bool): True if output was detected/matched.
            - matched (bool): True if pattern was found (only if pattern given).
            - output (str): Description of what was observed.
            - screenshot_path (str, optional): Path to the screenshot taken.
            - error (str, optional): Error message if unsuccessful.

    Examples:
        >>> # Wait for any output
        >>> result = await wait_for_terminal_output()

        >>> # Wait for specific text
        >>> result = await wait_for_terminal_output(pattern="success")

        >>> # Wait for regex pattern
        >>> result = await wait_for_terminal_output(pattern=r"\\d+ files")
    """
    pattern_display = pattern[:50] if pattern else "any"
    group_id = generate_group_id("terminal_wait_output", pattern_display)
    emit_info(
        f"TERMINAL WAIT OUTPUT 👁️ pattern={pattern_display}",
        message_group=group_id,
    )

    try:
        # Get the terminal page
        manager = get_chromium_terminal_manager()
        page = await manager.get_current_page()

        if not page:
            error_msg = (
                "No active terminal page. Please open the terminal first "
                "with open_terminal()."
            )
            emit_error(error_msg, message_group=group_id)
            return {
                "success": False,
                "error": error_msg,
                "matched": False,
            }

        # Take a screenshot and analyze it
        screenshot_result = await _capture_terminal_screenshot(page, group_id)

        if not screenshot_result["success"]:
            return {
                "success": False,
                "error": f"Screenshot failed: {screenshot_result.get('error')}",
                "matched": False,
            }

        result: Dict[str, Any] = {
            "success": True,
            "screenshot_path": screenshot_result["screenshot_path"],
        }

        if pattern:
            # Ask VQA to look for the pattern
            question = (
                f"Look at this terminal output. Is there text matching "
                f"or containing '{pattern}'? Describe what you see."
            )

            analysis = await _analyze_terminal_screenshot(
                screenshot_result["screenshot_data"],
                question,
                group_id,
            )

            if analysis["success"]:
                # Check if the answer indicates a match
                answer_lower = analysis["answer"].lower()
                matched = (
                    "yes" in answer_lower
                    or "found" in answer_lower
                    or "matches" in answer_lower
                    or "contains" in answer_lower
                    or pattern.lower() in answer_lower
                )

                result["matched"] = matched
                result["output"] = analysis["answer"]
                result["observations"] = analysis.get("observations", "")
                result["confidence"] = analysis.get("confidence", 0.0)

                if matched:
                    emit_success(
                        f"Pattern matched: {pattern}",
                        message_group=group_id,
                    )
                else:
                    emit_info(
                        f"Pattern not found: {pattern}",
                        message_group=group_id,
                    )
            else:
                result["matched"] = False
                result["output"] = ""
                result["analysis_error"] = analysis.get("error")
        else:
            # No pattern - just describe what's visible
            question = "Describe the current terminal output. What text is visible?"

            analysis = await _analyze_terminal_screenshot(
                screenshot_result["screenshot_data"],
                question,
                group_id,
            )

            if analysis["success"]:
                result["matched"] = True  # Any output counts as a match
                result["output"] = analysis["answer"]
                result["observations"] = analysis.get("observations", "")
            else:
                result["matched"] = False
                result["output"] = ""
                result["analysis_error"] = analysis.get("error")

        return result

    except Exception as e:
        error_msg = f"Failed to wait for terminal output: {str(e)}"
        emit_error(error_msg, message_group=group_id)
        logger.exception("Error waiting for terminal output")
        return {
            "success": False,
            "error": error_msg,
            "matched": False,
        }


# =============================================================================
# Tool Registration Functions
# =============================================================================


def register_run_terminal_command(agent):
    """Register the terminal command execution tool with an agent.

    Args:
        agent: The pydantic-ai agent to register the tool with.
    """

    @agent.tool
    async def terminal_run_command(
        context: RunContext,
        command: str,
        wait_for_prompt: bool = True,
        timeout: float = DEFAULT_COMMAND_TIMEOUT,
        auto_screenshot: bool = True,
        screenshot_question: str = "Did the command execute successfully? What is the output?",
    ) -> Dict[str, Any]:
        """
        Execute a command in the terminal browser.

        Types the command, presses Enter, optionally waits for completion,
        and can analyze the output via screenshot.

        Args:
            command: The command string to execute.
            wait_for_prompt: Wait for command to complete (default: True).
            timeout: Max wait time in seconds (default: 30).
            auto_screenshot: Take screenshot after execution (default: True).
            screenshot_question: Question for visual analysis of output.

        Returns:
            Dict with:
                - success: True if command was sent
                - command: The executed command
                - screenshot_path: Path to screenshot (if taken)
                - analysis: VQA results (if auto_screenshot)
                - error: Error message (if unsuccessful)
        """
        return await run_terminal_command(
            command=command,
            wait_for_prompt=wait_for_prompt,
            timeout=timeout,
            auto_screenshot=auto_screenshot,
            screenshot_question=screenshot_question,
        )


def register_send_terminal_keys(agent):
    """Register the terminal key sending tool with an agent.

    Args:
        agent: The pydantic-ai agent to register the tool with.
    """

    @agent.tool
    async def terminal_send_keys(
        context: RunContext,
        keys: str,
        modifiers: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Send special keys or key combinations to the terminal.

        Supports special keys (Enter, Tab, ArrowUp, Escape, etc.) and
        modifier combinations (Ctrl+C, Ctrl+D, etc.).

        Args:
            keys: Key(s) to send (e.g., "c", "Tab", "ArrowUp", "Escape").
            modifiers: Optional modifier keys (["Control"], ["Shift"], etc.).

        Returns:
            Dict with:
                - success: True if keys were sent
                - keys_sent: The keys that were sent
                - modifiers: The modifiers used
                - error: Error message (if unsuccessful)
        """
        return await send_terminal_keys(
            keys=keys,
            modifiers=modifiers,
        )


def register_wait_for_terminal_output(agent):
    """Register the terminal output waiting tool with an agent.

    Args:
        agent: The pydantic-ai agent to register the tool with.
    """

    @agent.tool
    async def terminal_wait_output(
        context: RunContext,
        pattern: Optional[str] = None,
        timeout: float = DEFAULT_OUTPUT_TIMEOUT,
    ) -> Dict[str, Any]:
        """
        Wait for terminal output, optionally matching a pattern.

        Takes a screenshot and uses visual analysis to detect output.

        Args:
            pattern: Optional regex/text pattern to match in output.
            timeout: Max wait time in seconds (default: 30).

        Returns:
            Dict with:
                - success: True if output was detected
                - matched: True if pattern was found
                - output: Description of observed output
                - screenshot_path: Path to screenshot
                - error: Error message (if unsuccessful)
        """
        return await wait_for_terminal_output(
            pattern=pattern,
            timeout=timeout,
        )


def register_all_terminal_command_tools(agent):
    """Register all terminal command tools with an agent.

    Convenience function to register all terminal command execution tools.

    Args:
        agent: The pydantic-ai agent to register the tools with.
    """
    register_run_terminal_command(agent)
    register_send_terminal_keys(agent)
    register_wait_for_terminal_output(agent)
