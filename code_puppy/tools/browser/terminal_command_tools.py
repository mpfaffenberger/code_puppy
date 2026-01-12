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
import re
from typing import Any, Dict, List, Optional

from pydantic_ai import RunContext

from rich.text import Text

from code_puppy.messaging import emit_error, emit_info, emit_success
from code_puppy.tools.browser import format_terminal_banner
from code_puppy.tools.common import generate_group_id

from .terminal_screenshot_tools import terminal_read_output, terminal_screenshot
from .terminal_tools import get_session_manager

logger = logging.getLogger(__name__)

# Timeout defaults (seconds)
DEFAULT_COMMAND_TIMEOUT = 30.0
DEFAULT_OUTPUT_TIMEOUT = 30.0

# Time to wait for prompt to reappear after command (ms)
PROMPT_WAIT_MS = 500

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

# JavaScript to robustly focus the xterm.js terminal
# xterm.js uses a hidden textarea to capture keyboard input
FOCUS_TERMINAL_JS = """
() => {
    // Method 1: Find and focus the xterm helper textarea directly
    // This is the element that actually receives keyboard input in xterm.js
    const textareas = document.querySelectorAll('textarea.xterm-helper-textarea');
    for (const textarea of textareas) {
        textarea.focus();
        // Also click on the parent to ensure xterm knows it's active
        const xterm = textarea.closest('.xterm');
        if (xterm) {
            xterm.click();
        }
        return { success: true, method: 'textarea_focus', found: textareas.length };
    }
    
    // Method 2: Click on the xterm viewport/screen to trigger focus
    const viewport = document.querySelector('.xterm-viewport') || 
                     document.querySelector('.xterm-screen');
    if (viewport) {
        viewport.click();
        // Try textarea again after click
        const ta = document.querySelector('textarea.xterm-helper-textarea');
        if (ta) ta.focus();
        return { success: true, method: 'viewport_click' };
    }
    
    // Method 3: Find any xterm element and click it
    const xterm = document.querySelector('.xterm');
    if (xterm) {
        xterm.click();
        const ta = xterm.querySelector('textarea');
        if (ta) ta.focus();
        return { success: true, method: 'xterm_click' };
    }
    
    // Method 4: Try the terminal container
    const container = document.getElementById('terminal');
    if (container) {
        container.click();
        return { success: true, method: 'container_click' };
    }
    
    return { success: false, error: 'Could not find terminal element' };
}
"""


async def _focus_terminal(page) -> Dict[str, Any]:
    """Focus the xterm.js terminal to receive keyboard input.

    xterm.js uses a hidden textarea element to capture keyboard events.
    We need to ensure this textarea is focused for keys to work.
    """
    try:
        # First, try the JavaScript approach which is most reliable
        result = await page.evaluate(FOCUS_TERMINAL_JS)

        if result.get("success"):
            # Give the browser a moment to process the focus
            await asyncio.sleep(0.15)
            return result

        # Fallback: Try clicking on known selectors
        selectors_to_try = [
            "textarea.xterm-helper-textarea",
            ".xterm-viewport",
            ".xterm-screen",
            ".xterm",
            "#terminal",
        ]

        for selector in selectors_to_try:
            element = await page.query_selector(selector)
            if element:
                await element.click()
                await asyncio.sleep(0.1)
                # If we clicked something other than textarea, try to focus textarea
                if "textarea" not in selector:
                    textarea = await page.query_selector(
                        "textarea.xterm-helper-textarea"
                    )
                    if textarea:
                        await textarea.focus()
                return {"success": True, "method": f"fallback_{selector}"}

        return {"success": False, "error": "Could not find terminal element to focus"}

    except Exception as e:
        logger.warning(f"Error focusing terminal: {e}")
        return {"success": False, "error": str(e)}


def _normalize_modifier(modifier: str) -> str:
    """Normalize modifier name to Playwright format."""
    return MODIFIER_MAP.get(modifier.lower(), modifier)


async def run_terminal_command(
    command: str,
    wait_for_prompt: bool = True,
    timeout: float = DEFAULT_COMMAND_TIMEOUT,
    capture_screenshot: bool = False,
) -> Dict[str, Any]:
    """Execute a command in the terminal browser.

    Types the command into the xterm.js terminal and presses Enter to execute.
    Optionally captures a screenshot that multimodal models can see directly.

    Args:
        command: The command string to execute.
        wait_for_prompt: If True, wait briefly for command to process.
            Defaults to True.
        timeout: Maximum wait time in seconds. Defaults to 30.0.
        capture_screenshot: If True, take a screenshot after execution.
            The screenshot is returned as base64 data. Defaults to False.

    Returns:
        A dictionary containing:
            - success (bool): True if command was sent.
            - command (str): The command that was executed.
            - base64_image (str, optional): Screenshot as base64 PNG (if captured).
            - screenshot_path (str, optional): Path to saved screenshot.
            - error (str, optional): Error message if unsuccessful.
    """
    group_id = generate_group_id("terminal_run_command", command[:50])
    banner = format_terminal_banner("TERMINAL RUN COMMAND 💻")
    emit_info(
        Text.from_markup(f"{banner} [dim]{command}[/dim]"), message_group=group_id
    )

    try:
        manager = get_session_manager()
        page = await manager.get_current_page()

        if not page:
            error_msg = "No active terminal page. Open terminal first."
            emit_error(error_msg, message_group=group_id)
            return {"success": False, "error": error_msg, "command": command}

        # Focus the terminal before typing
        focus_result = await _focus_terminal(page)
        if not focus_result.get("success"):
            emit_info(
                f"Warning: Could not focus terminal: {focus_result.get('error')}",
                message_group=group_id,
            )

        # Type and execute command
        await page.keyboard.type(command)
        await page.keyboard.press("Enter")
        emit_info(f"Command sent: {command}", message_group=group_id)

        # Wait for command to process
        if wait_for_prompt:
            await asyncio.sleep(min(PROMPT_WAIT_MS / 1000, timeout))

        result: Dict[str, Any] = {
            "success": True,
            "command": command,
        }

        # Capture screenshot if requested
        if capture_screenshot:
            screenshot_result = await terminal_screenshot()
            if screenshot_result["success"]:
                result["base64_image"] = screenshot_result["base64_image"]
                result["screenshot_path"] = screenshot_result.get("screenshot_path")
                result["media_type"] = "image/png"

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
    repeat: int = 1,
    delay_ms: int = 50,
) -> Dict[str, Any]:
    """Send special keys or key combinations to the terminal.

    Sends keyboard input to the xterm.js terminal, supporting special keys
    and modifier combinations like Ctrl+C, Ctrl+D, Tab, Arrow keys, etc.

    Args:
        keys: The key(s) to send. Can be a single character or special key
            like "Enter", "Tab", "ArrowUp", "ArrowDown", "ArrowLeft",
            "ArrowRight", "Escape", "Backspace", "Delete", etc.
        modifiers: Optional modifier keys to hold. Supported:
            "Control"/"Ctrl", "Shift", "Alt", "Meta"/"Command"/"Cmd".
        repeat: Number of times to press the key. Defaults to 1.
            Use this to navigate multiple items, e.g., repeat=5 for ArrowDown.
        delay_ms: Delay in milliseconds between repeated keypresses.
            Defaults to 50ms. Increase if the TUI needs time to update.

    Returns:
        Dict with success, keys_sent, modifiers, repeat_count, and optional error.

    Examples:
        >>> await send_terminal_keys("c", modifiers=["Control"])  # Ctrl+C
        >>> await send_terminal_keys("Tab")  # Tab completion
        >>> await send_terminal_keys("ArrowUp")  # Previous command
        >>> await send_terminal_keys("ArrowDown", repeat=5)  # Navigate down 5 items
        >>> await send_terminal_keys("ArrowRight", repeat=3, delay_ms=100)  # Move right 3 times
    """
    modifiers = modifiers or []
    repeat = max(1, repeat)  # Ensure at least 1
    normalized_modifiers = [_normalize_modifier(m) for m in modifiers]
    modifier_str = "+".join(normalized_modifiers) if normalized_modifiers else ""
    key_combo = f"{modifier_str}+{keys}" if modifier_str else keys

    repeat_str = f" x{repeat}" if repeat > 1 else ""
    group_id = generate_group_id("terminal_send_keys", f"{key_combo}{repeat_str}")
    banner = format_terminal_banner("TERMINAL SEND KEYS ⌨️")
    emit_info(
        Text.from_markup(f"{banner} [bold cyan]{key_combo}{repeat_str}[/bold cyan]"),
        message_group=group_id,
    )

    try:
        manager = get_session_manager()
        page = await manager.get_current_page()

        if not page:
            error_msg = "No active terminal page. Open terminal first."
            emit_error(error_msg, message_group=group_id)
            return {
                "success": False,
                "error": error_msg,
                "keys_sent": keys,
                "modifiers": modifiers,
            }

        # Focus terminal before sending keys
        await _focus_terminal(page)

        # Send key(s) the specified number of times
        for i in range(repeat):
            # Hold modifiers and press key
            for modifier in normalized_modifiers:
                await page.keyboard.down(modifier)

            try:
                if len(keys) > 1 or keys[0].isupper():
                    await page.keyboard.press(keys)
                else:
                    await page.keyboard.type(keys)
            finally:
                for modifier in reversed(normalized_modifiers):
                    await page.keyboard.up(modifier)

            # Delay between repeated keypresses (but not after the last one)
            if repeat > 1 and i < repeat - 1:
                await asyncio.sleep(delay_ms / 1000)

        emit_success(f"Keys sent: {key_combo}{repeat_str}", message_group=group_id)
        return {
            "success": True,
            "keys_sent": keys,
            "modifiers": modifiers,
            "repeat_count": repeat,
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
            "repeat_count": repeat,
        }


async def wait_for_terminal_output(
    pattern: Optional[str] = None,
    timeout: float = DEFAULT_OUTPUT_TIMEOUT,
    capture_screenshot: bool = False,
) -> Dict[str, Any]:
    """Wait for terminal output, optionally matching a pattern.

    Reads the terminal text output and checks for a pattern match.
    Uses DOM scraping to get actual text content.

    Args:
        pattern: Optional regex or text pattern to match.
            If None, just reads current output.
        timeout: Maximum wait time in seconds. Defaults to 30.0.
        capture_screenshot: If True, include a screenshot. Defaults to False.

    Returns:
        Dict with:
            - success (bool): True if output was read.
            - matched (bool): True if pattern was found (when pattern given).
            - output (str): The terminal text content.
            - base64_image (str, optional): Screenshot if captured.
            - error (str, optional): Error message if unsuccessful.
    """
    pattern_display = pattern[:50] if pattern else "any"
    group_id = generate_group_id("terminal_wait_output", pattern_display)
    banner = format_terminal_banner("TERMINAL WAIT OUTPUT 👁️")
    emit_info(
        Text.from_markup(f"{banner} [dim]pattern={pattern_display}[/dim]"),
        message_group=group_id,
    )

    try:
        # Read terminal text output
        read_result = await terminal_read_output(lines=100)

        if not read_result["success"]:
            emit_error(
                read_result.get("error", "Failed to read output"),
                message_group=group_id,
            )
            return {
                "success": False,
                "error": read_result.get("error"),
                "matched": False,
            }

        output_text = read_result["output"]

        result: Dict[str, Any] = {
            "success": True,
            "output": output_text,
            "line_count": read_result.get("line_count", 0),
        }

        # Check pattern match
        if pattern:
            try:
                # Try regex match first
                matched = bool(re.search(pattern, output_text, re.IGNORECASE))
            except re.error:
                # Fall back to simple substring match
                matched = pattern.lower() in output_text.lower()

            result["matched"] = matched
            if matched:
                emit_success(f"Pattern matched: {pattern}", message_group=group_id)
            else:
                emit_info(f"Pattern not found: {pattern}", message_group=group_id)
        else:
            result["matched"] = bool(output_text.strip())

        # Capture screenshot if requested
        if capture_screenshot:
            screenshot_result = await terminal_screenshot()
            if screenshot_result["success"]:
                result["base64_image"] = screenshot_result["base64_image"]
                result["screenshot_path"] = screenshot_result.get("screenshot_path")
                result["media_type"] = "image/png"

        return result

    except Exception as e:
        error_msg = f"Failed to wait for terminal output: {str(e)}"
        emit_error(error_msg, message_group=group_id)
        logger.exception("Error waiting for terminal output")
        return {"success": False, "error": error_msg, "matched": False}


# =============================================================================
# Tool Registration Functions
# =============================================================================


def register_run_terminal_command(agent):
    """Register the terminal command execution tool."""

    @agent.tool
    async def terminal_run_command(
        context: RunContext,
        command: str,
        wait_for_prompt: bool = True,
        capture_screenshot: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute a command in the terminal browser.

        Types the command and presses Enter. Optionally captures a screenshot
        that you can see directly as base64 image data.

        Args:
            command: The command to execute.
            wait_for_prompt: Wait briefly for command to process (default: True).
            capture_screenshot: Capture screenshot after execution (default: False).
                Set True if you need to see the terminal output visually.

        Returns:
            Dict with success, command, and optionally base64_image you can see.
        """
        # Session is set by invoke_agent via contextvar
        return await run_terminal_command(
            command=command,
            wait_for_prompt=wait_for_prompt,
            capture_screenshot=capture_screenshot,
        )


def register_send_terminal_keys(agent):
    """Register the terminal key sending tool."""

    @agent.tool
    async def terminal_send_keys(
        context: RunContext,
        keys: str,
        modifiers: Optional[List[str]] = None,
        repeat: int = 1,
        delay_ms: int = 50,
    ) -> Dict[str, Any]:
        """
        Send special keys or key combinations to the terminal.

        Args:
            keys: Key to send (e.g., "Enter", "Tab", "ArrowUp", "ArrowDown", "c").
            modifiers: Modifier keys like ["Control"] for Ctrl+C.
            repeat: Number of times to press the key. Use this to navigate
                multiple items instead of calling this function multiple times!
                Example: repeat=5 to press ArrowDown 5 times.
            delay_ms: Milliseconds to wait between repeated keypresses (default 50).

        Returns:
            Dict with success, keys_sent, modifiers, repeat_count.

        Examples:
            - Navigate down 5 items: keys="ArrowDown", repeat=5
            - Navigate right 3 times: keys="ArrowRight", repeat=3
            - Ctrl+C: keys="c", modifiers=["Control"]
            - Tab: keys="Tab"
        """
        # Session is set by invoke_agent via contextvar
        return await send_terminal_keys(
            keys=keys, modifiers=modifiers, repeat=repeat, delay_ms=delay_ms
        )


def register_wait_terminal_output(agent):
    """Register the terminal output waiting tool."""

    @agent.tool
    async def terminal_wait_output(
        context: RunContext,
        pattern: Optional[str] = None,
        capture_screenshot: bool = False,
    ) -> Dict[str, Any]:
        """
        Read terminal output and optionally match a pattern.

        Extracts text from the terminal. Can check for pattern matches.

        Args:
            pattern: Optional regex or text to search for.
            capture_screenshot: Include a screenshot you can see (default: False).

        Returns:
            Dict with output (text), matched (if pattern given), optionally base64_image.
        """
        # Session is set by invoke_agent via contextvar
        return await wait_for_terminal_output(
            pattern=pattern,
            capture_screenshot=capture_screenshot,
        )
