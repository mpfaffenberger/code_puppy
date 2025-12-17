"""Browser element interaction tools for clicking, typing, and form manipulation."""

from typing import Any, Dict, List, Optional, Literal

from pydantic_ai import RunContext

from rich.text import Text

from code_puppy.messaging import emit_error, emit_info, emit_success
from code_puppy.tools.common import generate_group_id

from .camoufox_manager import get_camoufox_manager


# --- Click Helper Functions ---


def _classify_click_error(error: str) -> str:
    """Classify the type of click error for better debugging."""
    error_lower = error.lower()
    if "timeout" in error_lower:
        return "timeout"
    if "intercept" in error_lower or "obscured" in error_lower:
        return "intercepted"
    if "detached" in error_lower:
        return "detached"
    if "not visible" in error_lower or "hidden" in error_lower:
        return "not_visible"
    if "disabled" in error_lower:
        return "disabled"
    if "outside" in error_lower or "viewport" in error_lower:
        return "outside_viewport"
    return "unknown"


async def _gather_element_diagnostics(element) -> Dict[str, Any]:
    """Gather diagnostic info about why a click might have failed."""
    try:
        diagnostics = {}
        try:
            diagnostics["visible"] = await element.is_visible()
        except Exception:
            diagnostics["visible"] = None
        try:
            diagnostics["enabled"] = await element.is_enabled()
        except Exception:
            diagnostics["enabled"] = None
        try:
            diagnostics["bounding_box"] = await element.bounding_box()
        except Exception:
            diagnostics["bounding_box"] = None
        return diagnostics
    except Exception:
        return {}


async def click_element(
    selector: str,
    timeout: int = 10000,
    force: bool = False,
    button: str = "left",
    modifiers: Optional[List[str]] = None,
    scroll_behavior: Literal["center", "nearest", "none"] = "center",
    max_retries: int = 2,
) -> Dict[str, Any]:
    """Click on an element with smart scrolling and retry logic.

    This function handles common click failures like:
    - Elements obscured by sticky headers/footers (scrolls to center)
    - Transient failures during animations (retries)
    - Elements that haven't stabilized yet (waits between retries)

    Args:
        selector: CSS or XPath selector for the element
        timeout: Timeout in milliseconds to wait for element
        force: Skip actionability checks and force the click
        button: Mouse button to click (left, right, middle)
        modifiers: Modifier keys to hold (Alt, Control, Meta, Shift)
        scroll_behavior: How to scroll element into view:
            - "center": Scroll to center of viewport (avoids sticky headers/footers)
            - "nearest": Scroll minimum distance needed
            - "none": Don't scroll before clicking
        max_retries: Number of retry attempts for transient failures (default: 2)

    Returns:
        Dict with click results including diagnostics on failure
    """
    group_id = generate_group_id("browser_click", selector[:100])
    emit_info(
        f"BROWSER CLICK 🖱️ selector='{selector}' button={button}",
        message_group=group_id,
    )

    try:
        browser_manager = get_camoufox_manager()
        page = await browser_manager.get_current_page()

        if not page:
            return {"success": False, "error": "No active browser page available"}

        element = page.locator(selector)

        # Pre-flight check: does element exist at all?
        count = await element.count()
        if count == 0:
            emit_info(
                Text.from_markup(f"[red]✗ No elements found: {selector}[/red]"), message_group=group_id
            )
            return {
                "success": False,
                "error": f"No elements found matching selector: {selector}",
                "error_type": "not_found",
                "selector": selector,
            }

        if count > 1:
            emit_info(
                Text.from_markup(f"[yellow]⚠ {count} elements match selector, clicking first[/yellow]"),
                message_group=group_id,
            )
            element = element.first

        last_error: Optional[Exception] = None
        diagnostics: Dict[str, Any] = {}

        for attempt in range(max_retries + 1):
            try:
                # Smart scroll to avoid sticky headers/footers
                if scroll_behavior != "none" and not force:
                    try:
                        await element.evaluate(
                            f"el => el.scrollIntoView({{block: '{scroll_behavior}', behavior: 'instant'}})"
                        )
                        # Brief settle time for scroll to complete
                        await page.wait_for_timeout(100)
                    except Exception:
                        # Scroll failure is not fatal - element might already be visible
                        pass

                # Build click options (no redundant wait_for - click() does its own checks)
                click_options: Dict[str, Any] = {
                    "force": force,
                    "button": button,
                    "timeout": timeout,
                }
                if modifiers:
                    click_options["modifiers"] = modifiers

                await element.click(**click_options)

                emit_info(
                    Text.from_markup(f"[green]✓ Clicked element: {selector}[/green]"),
                    message_group=group_id,
                )
                return {
                    "success": True,
                    "selector": selector,
                    "action": f"{button}_click",
                    "attempts": attempt + 1,
                }

            except Exception as e:
                last_error = e
                error_str = str(e).lower()

                # Determine if this is a retriable error
                retriable_patterns = [
                    "intercept",
                    "obscured",
                    "not stable",
                    "animating",
                    "moving",
                    "outside",  # outside viewport - might fix with scroll retry
                ]
                is_retriable = any(
                    pattern in error_str for pattern in retriable_patterns
                )

                if is_retriable and attempt < max_retries:
                    emit_info(
                        Text.from_markup(f"[yellow]⚠ Click attempt {attempt + 1} failed, retrying... ({type(e).__name__})[/yellow]"),
                        message_group=group_id,
                    )
                    # Wait for animations/transitions to settle
                    await page.wait_for_timeout(300)
                    continue

                # Final failure - gather diagnostics
                diagnostics = await _gather_element_diagnostics(element)
                break

        # Classify the error for structured debugging
        error_type = _classify_click_error(str(last_error))

        emit_info(
            Text.from_markup(f"[red]✗ Click failed after {max_retries + 1} attempts: {last_error}[/red]"),
            message_group=group_id,
        )

        return {
            "success": False,
            "error": str(last_error),
            "error_type": error_type,
            "selector": selector,
            "attempts": max_retries + 1,
            "diagnostics": diagnostics,
        }

    except Exception as e:
        emit_info(Text.from_markup(f"[red]✗ Click failed: {e}[/red]"), message_group=group_id)
        return {
            "success": False,
            "error": str(e),
            "error_type": _classify_click_error(str(e)),
            "selector": selector,
        }


async def double_click_element(
    selector: str,
    timeout: int = 10000,
    force: bool = False,
    scroll_behavior: Literal["center", "nearest", "none"] = "center",
    max_retries: int = 2,
) -> Dict[str, Any]:
    """Double-click on an element with smart scrolling and retry logic."""
    group_id = generate_group_id("browser_double_click", selector[:100])
    emit_info(
        f"BROWSER DOUBLE CLICK 🖱️🖱️ selector='{selector}'",
        message_group=group_id,
    )

    try:
        browser_manager = get_camoufox_manager()
        page = await browser_manager.get_current_page()

        if not page:
            return {"success": False, "error": "No active browser page available"}

        element = page.locator(selector)

        # Pre-flight check
        count = await element.count()
        if count == 0:
            emit_info(
                Text.from_markup(f"[red]✗ No elements found: {selector}[/red]"), message_group=group_id
            )
            return {
                "success": False,
                "error": f"No elements found matching selector: {selector}",
                "error_type": "not_found",
                "selector": selector,
            }

        if count > 1:
            emit_info(
                Text.from_markup(f"[yellow]⚠ {count} elements match, double-clicking first[/yellow]"),
                message_group=group_id,
            )
            element = element.first

        last_error: Optional[Exception] = None
        diagnostics: Dict[str, Any] = {}

        for attempt in range(max_retries + 1):
            try:
                # Smart scroll
                if scroll_behavior != "none" and not force:
                    try:
                        await element.evaluate(
                            f"el => el.scrollIntoView({{block: '{scroll_behavior}', behavior: 'instant'}})"
                        )
                        await page.wait_for_timeout(100)
                    except Exception:
                        pass

                await element.dblclick(force=force, timeout=timeout)

                emit_info(
                    Text.from_markup(f"[green]✓ Double-clicked element: {selector}[/green]"),
                    message_group=group_id,
                )
                return {
                    "success": True,
                    "selector": selector,
                    "action": "double_click",
                    "attempts": attempt + 1,
                }

            except Exception as e:
                last_error = e
                error_str = str(e).lower()

                retriable_patterns = [
                    "intercept",
                    "obscured",
                    "not stable",
                    "animating",
                    "moving",
                    "outside",
                ]
                is_retriable = any(
                    pattern in error_str for pattern in retriable_patterns
                )

                if is_retriable and attempt < max_retries:
                    emit_info(
                        Text.from_markup(f"[yellow]⚠ Double-click attempt {attempt + 1} failed, retrying...[/yellow]"),
                        message_group=group_id,
                    )
                    await page.wait_for_timeout(300)
                    continue

                diagnostics = await _gather_element_diagnostics(element)
                break

        error_type = _classify_click_error(str(last_error))
        emit_info(
            Text.from_markup(f"[red]✗ Double-click failed: {last_error}[/red]"), message_group=group_id
        )

        return {
            "success": False,
            "error": str(last_error),
            "error_type": error_type,
            "selector": selector,
            "attempts": max_retries + 1,
            "diagnostics": diagnostics,
        }

    except Exception as e:
        emit_info(Text.from_markup(f"[red]✗ Double-click failed: {e}[/red]"), message_group=group_id)
        return {
            "success": False,
            "error": str(e),
            "error_type": _classify_click_error(str(e)),
            "selector": selector,
        }


async def hover_element(
    selector: str,
    timeout: int = 10000,
    force: bool = False,
    scroll_behavior: Literal["center", "nearest", "none"] = "center",
    max_retries: int = 2,
) -> Dict[str, Any]:
    """Hover over an element with smart scrolling and retry logic."""
    group_id = generate_group_id("browser_hover", selector[:100])
    emit_info(
        f"BROWSER HOVER 👆 selector='{selector}'",
        message_group=group_id,
    )

    try:
        browser_manager = get_camoufox_manager()
        page = await browser_manager.get_current_page()

        if not page:
            return {"success": False, "error": "No active browser page available"}

        element = page.locator(selector)

        # Pre-flight check
        count = await element.count()
        if count == 0:
            emit_info(
                Text.from_markup(f"[red]✗ No elements found: {selector}[/red]"), message_group=group_id
            )
            return {
                "success": False,
                "error": f"No elements found matching selector: {selector}",
                "error_type": "not_found",
                "selector": selector,
            }

        if count > 1:
            emit_info(
                Text.from_markup(f"[yellow]⚠ {count} elements match, hovering first[/yellow]"),
                message_group=group_id,
            )
            element = element.first

        last_error: Optional[Exception] = None
        diagnostics: Dict[str, Any] = {}

        for attempt in range(max_retries + 1):
            try:
                # Smart scroll
                if scroll_behavior != "none" and not force:
                    try:
                        await element.evaluate(
                            f"el => el.scrollIntoView({{block: '{scroll_behavior}', behavior: 'instant'}})"
                        )
                        await page.wait_for_timeout(100)
                    except Exception:
                        pass

                await element.hover(force=force, timeout=timeout)

                emit_info(
                    Text.from_markup(f"[green]✓ Hovered over element: {selector}[/green]"),
                    message_group=group_id,
                )
                return {
                    "success": True,
                    "selector": selector,
                    "action": "hover",
                    "attempts": attempt + 1,
                }

            except Exception as e:
                last_error = e
                error_str = str(e).lower()

                retriable_patterns = [
                    "intercept",
                    "obscured",
                    "not stable",
                    "animating",
                    "moving",
                    "outside",
                ]
                is_retriable = any(
                    pattern in error_str for pattern in retriable_patterns
                )

                if is_retriable and attempt < max_retries:
                    emit_info(
                        Text.from_markup(f"[yellow]⚠ Hover attempt {attempt + 1} failed, retrying...[/yellow]"),
                        message_group=group_id,
                    )
                    await page.wait_for_timeout(300)
                    continue

                diagnostics = await _gather_element_diagnostics(element)
                break

        error_type = _classify_click_error(str(last_error))
        emit_info(Text.from_markup(f"[red]✗ Hover failed: {last_error}[/red]"), message_group=group_id)

        return {
            "success": False,
            "error": str(last_error),
            "error_type": error_type,
            "selector": selector,
            "attempts": max_retries + 1,
            "diagnostics": diagnostics,
        }

    except Exception as e:
        emit_info(Text.from_markup(f"[red]✗ Hover failed: {e}[/red]"), message_group=group_id)
        return {
            "success": False,
            "error": str(e),
            "error_type": _classify_click_error(str(e)),
            "selector": selector,
        }


async def set_element_text(
    selector: str,
    text: str,
    clear_first: bool = True,
    timeout: int = 10000,
) -> Dict[str, Any]:
    """Set text in an input element."""
    group_id = generate_group_id("browser_set_text", f"{selector[:50]}_{text[:30]}")
    emit_info(
        f"BROWSER SET TEXT ✏️ selector='{selector}' text='{text[:50]}{'...' if len(text) > 50 else ''}'",
        message_group=group_id,
    )
    try:
        browser_manager = get_camoufox_manager()
        page = await browser_manager.get_current_page()

        if not page:
            return {"success": False, "error": "No active browser page available"}

        element = page.locator(selector)
        await element.wait_for(state="visible", timeout=timeout)

        if clear_first:
            await element.clear(timeout=timeout)

        await element.fill(text, timeout=timeout)

        emit_success(f"Set text in element: {selector}", message_group=group_id)

        return {
            "success": True,
            "selector": selector,
            "text": text,
            "action": "set_text",
        }

    except Exception as e:
        emit_error(f"Set text failed: {str(e)}", message_group=group_id)
        return {"success": False, "error": str(e), "selector": selector, "text": text}


async def get_element_text(
    selector: str,
    timeout: int = 10000,
) -> Dict[str, Any]:
    """Get text content from an element."""
    group_id = generate_group_id("browser_get_text", selector[:100])
    emit_info(
        f"BROWSER GET TEXT 📝 selector='{selector}'",
        message_group=group_id,
    )
    try:
        browser_manager = get_camoufox_manager()
        page = await browser_manager.get_current_page()

        if not page:
            return {"success": False, "error": "No active browser page available"}

        element = page.locator(selector)
        await element.wait_for(state="visible", timeout=timeout)

        text = await element.text_content()

        return {"success": True, "selector": selector, "text": text}

    except Exception as e:
        return {"success": False, "error": str(e), "selector": selector}


async def get_element_value(
    selector: str,
    timeout: int = 10000,
) -> Dict[str, Any]:
    """Get value from an input element."""
    group_id = generate_group_id("browser_get_value", selector[:100])
    emit_info(
        f"BROWSER GET VALUE 📎 selector='{selector}'",
        message_group=group_id,
    )
    try:
        browser_manager = get_camoufox_manager()
        page = await browser_manager.get_current_page()

        if not page:
            return {"success": False, "error": "No active browser page available"}

        element = page.locator(selector)
        await element.wait_for(state="visible", timeout=timeout)

        value = await element.input_value()

        return {"success": True, "selector": selector, "value": value}

    except Exception as e:
        return {"success": False, "error": str(e), "selector": selector}


async def select_option(
    selector: str,
    value: Optional[str] = None,
    label: Optional[str] = None,
    index: Optional[int] = None,
    timeout: int = 10000,
) -> Dict[str, Any]:
    """Select an option in a dropdown/select element."""
    option_desc = value or label or str(index) if index is not None else "unknown"
    group_id = generate_group_id(
        "browser_select_option", f"{selector[:50]}_{option_desc}"
    )
    emit_info(
        f"BROWSER SELECT OPTION 📄 selector='{selector}' option='{option_desc}'",
        message_group=group_id,
    )
    try:
        browser_manager = get_camoufox_manager()
        page = await browser_manager.get_current_page()

        if not page:
            return {"success": False, "error": "No active browser page available"}

        element = page.locator(selector)
        await element.wait_for(state="visible", timeout=timeout)

        if value is not None:
            await element.select_option(value=value, timeout=timeout)
            selection = value
        elif label is not None:
            await element.select_option(label=label, timeout=timeout)
            selection = label
        elif index is not None:
            await element.select_option(index=index, timeout=timeout)
            selection = str(index)
        else:
            return {
                "success": False,
                "error": "Must specify value, label, or index",
                "selector": selector,
            }

        emit_success(
            f"Selected option in {selector}: {selection}",
            message_group=group_id,
        )

        return {"success": True, "selector": selector, "selection": selection}

    except Exception as e:
        return {"success": False, "error": str(e), "selector": selector}


async def check_element(
    selector: str,
    timeout: int = 10000,
) -> Dict[str, Any]:
    """Check a checkbox or radio button."""
    group_id = generate_group_id("browser_check", selector[:100])
    emit_info(
        f"BROWSER CHECK ☑️ selector='{selector}'",
        message_group=group_id,
    )
    try:
        browser_manager = get_camoufox_manager()
        page = await browser_manager.get_current_page()

        if not page:
            return {"success": False, "error": "No active browser page available"}

        element = page.locator(selector)
        await element.wait_for(state="visible", timeout=timeout)
        await element.check(timeout=timeout)

        emit_success(f"Checked element: {selector}", message_group=group_id)

        return {"success": True, "selector": selector, "action": "check"}

    except Exception as e:
        return {"success": False, "error": str(e), "selector": selector}


async def uncheck_element(
    selector: str,
    timeout: int = 10000,
) -> Dict[str, Any]:
    """Uncheck a checkbox."""
    group_id = generate_group_id("browser_uncheck", selector[:100])
    emit_info(
        f"BROWSER UNCHECK ☐️ selector='{selector}'",
        message_group=group_id,
    )
    try:
        browser_manager = get_camoufox_manager()
        page = await browser_manager.get_current_page()

        if not page:
            return {"success": False, "error": "No active browser page available"}

        element = page.locator(selector)
        await element.wait_for(state="visible", timeout=timeout)
        await element.uncheck(timeout=timeout)

        emit_success(f"Unchecked element: {selector}", message_group=group_id)

        return {"success": True, "selector": selector, "action": "uncheck"}

    except Exception as e:
        return {"success": False, "error": str(e), "selector": selector}


# Tool registration functions
def register_click_element(agent):
    """Register the click element tool."""

    @agent.tool
    async def browser_click(
        context: RunContext,
        selector: str,
        timeout: int = 10000,
        force: bool = False,
        button: str = "left",
        modifiers: Optional[List[str]] = None,
        scroll_behavior: str = "center",
        max_retries: int = 2,
    ) -> Dict[str, Any]:
        """
        Click on an element in the browser with smart scrolling and retry logic.

        This handles common click failures like elements obscured by sticky
        headers/footers, transient animation issues, and elements that need
        time to stabilize.

        Args:
            selector: CSS or XPath selector for the element
            timeout: Timeout in milliseconds to wait for element
            force: Skip actionability checks and force the click
            button: Mouse button to click (left, right, middle)
            modifiers: Modifier keys to hold (Alt, Control, Meta, Shift)
            scroll_behavior: How to scroll element into view:
                - "center": Scroll to center of viewport (default, avoids sticky headers)
                - "nearest": Minimum scroll distance
                - "none": Don't scroll before clicking
            max_retries: Number of retry attempts for transient failures (default: 2)

        Returns:
            Dict with click results. On failure, includes:
                - error_type: classified error (timeout, intercepted, not_visible, etc.)
                - diagnostics: element state info (visible, enabled, bounding_box)
                - attempts: number of attempts made
        """
        # Validate scroll_behavior
        valid_scroll = ("center", "nearest", "none")
        if scroll_behavior not in valid_scroll:
            scroll_behavior = "center"

        return await click_element(
            selector, timeout, force, button, modifiers, scroll_behavior, max_retries
        )


def register_double_click_element(agent):
    """Register the double-click element tool."""

    @agent.tool
    async def browser_double_click(
        context: RunContext,
        selector: str,
        timeout: int = 10000,
        force: bool = False,
        scroll_behavior: str = "center",
        max_retries: int = 2,
    ) -> Dict[str, Any]:
        """
        Double-click on an element with smart scrolling and retry logic.

        Args:
            selector: CSS or XPath selector for the element
            timeout: Timeout in milliseconds to wait for element
            force: Skip actionability checks and force the double-click
            scroll_behavior: "center", "nearest", or "none"
            max_retries: Number of retry attempts for transient failures

        Returns:
            Dict with double-click results and diagnostics on failure
        """
        valid_scroll = ("center", "nearest", "none")
        if scroll_behavior not in valid_scroll:
            scroll_behavior = "center"
        return await double_click_element(
            selector, timeout, force, scroll_behavior, max_retries
        )


def register_hover_element(agent):
    """Register the hover element tool."""

    @agent.tool
    async def browser_hover(
        context: RunContext,
        selector: str,
        timeout: int = 10000,
        force: bool = False,
        scroll_behavior: str = "center",
        max_retries: int = 2,
    ) -> Dict[str, Any]:
        """
        Hover over an element with smart scrolling and retry logic.

        Args:
            selector: CSS or XPath selector for the element
            timeout: Timeout in milliseconds to wait for element
            force: Skip actionability checks and force the hover
            scroll_behavior: "center", "nearest", or "none"
            max_retries: Number of retry attempts for transient failures

        Returns:
            Dict with hover results and diagnostics on failure
        """
        valid_scroll = ("center", "nearest", "none")
        if scroll_behavior not in valid_scroll:
            scroll_behavior = "center"
        return await hover_element(
            selector, timeout, force, scroll_behavior, max_retries
        )


def register_set_element_text(agent):
    """Register the set element text tool."""

    @agent.tool
    async def browser_set_text(
        context: RunContext,
        selector: str,
        text: str,
        clear_first: bool = True,
        timeout: int = 10000,
    ) -> Dict[str, Any]:
        """
        Set text in an input element.

        Args:
            selector: CSS or XPath selector for the input element
            text: Text to enter
            clear_first: Whether to clear existing text first
            timeout: Timeout in milliseconds to wait for element

        Returns:
            Dict with text input results
        """
        return await set_element_text(selector, text, clear_first, timeout)


def register_get_element_text(agent):
    """Register the get element text tool."""

    @agent.tool
    async def browser_get_text(
        context: RunContext,
        selector: str,
        timeout: int = 10000,
    ) -> Dict[str, Any]:
        """
        Get text content from an element.

        Args:
            selector: CSS or XPath selector for the element
            timeout: Timeout in milliseconds to wait for element

        Returns:
            Dict with element text content
        """
        return await get_element_text(selector, timeout)


def register_get_element_value(agent):
    """Register the get element value tool."""

    @agent.tool
    async def browser_get_value(
        context: RunContext,
        selector: str,
        timeout: int = 10000,
    ) -> Dict[str, Any]:
        """
        Get value from an input element.

        Args:
            selector: CSS or XPath selector for the input element
            timeout: Timeout in milliseconds to wait for element

        Returns:
            Dict with element value
        """
        return await get_element_value(selector, timeout)


def register_select_option(agent):
    """Register the select option tool."""

    @agent.tool
    async def browser_select_option(
        context: RunContext,
        selector: str,
        value: Optional[str] = None,
        label: Optional[str] = None,
        index: Optional[int] = None,
        timeout: int = 10000,
    ) -> Dict[str, Any]:
        """
        Select an option in a dropdown/select element.

        Args:
            selector: CSS or XPath selector for the select element
            value: Option value to select
            label: Option label text to select
            index: Option index to select (0-based)
            timeout: Timeout in milliseconds to wait for element

        Returns:
            Dict with selection results
        """
        return await select_option(selector, value, label, index, timeout)


def register_browser_check(agent):
    """Register checkbox/radio button check tool."""

    @agent.tool
    async def browser_check(
        context: RunContext,
        selector: str,
        timeout: int = 10000,
    ) -> Dict[str, Any]:
        """
        Check a checkbox or radio button.

        Args:
            selector: CSS or XPath selector for the checkbox/radio
            timeout: Timeout in milliseconds to wait for element

        Returns:
            Dict with check results
        """
        return await check_element(selector, timeout)


def register_browser_uncheck(agent):
    """Register checkbox uncheck tool."""

    @agent.tool
    async def browser_uncheck(
        context: RunContext,
        selector: str,
        timeout: int = 10000,
    ) -> Dict[str, Any]:
        """
        Uncheck a checkbox.

        Args:
            selector: CSS or XPath selector for the checkbox
            timeout: Timeout in milliseconds to wait for element

        Returns:
            Dict with uncheck results
        """
        return await uncheck_element(selector, timeout)
