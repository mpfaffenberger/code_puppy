"""JavaScript execution and advanced page manipulation tools."""

from typing import Any, Dict, Optional

from pydantic_ai import RunContext

from code_puppy.messaging import emit_error, emit_info, emit_success
from code_puppy.tools.common import generate_group_id

from .camoufox_manager import get_camoufox_manager


async def execute_javascript(
    script: str,
    timeout: int = 30000,
) -> Dict[str, Any]:
    """Execute JavaScript code in the browser context."""
    group_id = generate_group_id("browser_execute_js", script[:100])
    emit_info(
        f"BROWSER EXECUTE JS 📜 script='{script[:100]}{'...' if len(script) > 100 else ''}'",
        message_group=group_id,
    )
    try:
        browser_manager = get_camoufox_manager()
        page = await browser_manager.get_current_page()

        if not page:
            return {"success": False, "error": "No active browser page available"}

        # Execute JavaScript
        result = await page.evaluate(script, timeout=timeout)

        emit_success("JavaScript executed successfully", message_group=group_id)

        return {"success": True, "script": script, "result": result}

    except Exception as e:
        emit_error(f"JavaScript execution failed: {str(e)}", message_group=group_id)
        return {"success": False, "error": str(e), "script": script}


async def scroll_page(
    direction: str = "down",
    amount: int = 3,
    element_selector: Optional[str] = None,
) -> Dict[str, Any]:
    """Scroll the page or a specific element."""
    target = element_selector or "page"
    group_id = generate_group_id("browser_scroll", f"{direction}_{amount}_{target}")
    emit_info(
        f"BROWSER SCROLL 📋 direction={direction} amount={amount} target='{target}'",
        message_group=group_id,
    )
    try:
        browser_manager = get_camoufox_manager()
        page = await browser_manager.get_current_page()

        if not page:
            return {"success": False, "error": "No active browser page available"}

        if element_selector:
            # Scroll specific element
            element = page.locator(element_selector)
            await element.scroll_into_view_if_needed()

            # Get element's current scroll position and dimensions
            scroll_info = await element.evaluate("""
                el => {
                    const rect = el.getBoundingClientRect();
                    return {
                        scrollTop: el.scrollTop,
                        scrollLeft: el.scrollLeft,
                        scrollHeight: el.scrollHeight,
                        scrollWidth: el.scrollWidth,
                        clientHeight: el.clientHeight,
                        clientWidth: el.clientWidth
                    };
                }
            """)

            # Calculate scroll amount based on element size
            scroll_amount = scroll_info["clientHeight"] * amount / 3

            if direction.lower() == "down":
                await element.evaluate(f"el => el.scrollTop += {scroll_amount}")
            elif direction.lower() == "up":
                await element.evaluate(f"el => el.scrollTop -= {scroll_amount}")
            elif direction.lower() == "left":
                await element.evaluate(f"el => el.scrollLeft -= {scroll_amount}")
            elif direction.lower() == "right":
                await element.evaluate(f"el => el.scrollLeft += {scroll_amount}")

            target = f"element '{element_selector}'"

        else:
            # Scroll page
            viewport_height = await page.evaluate("() => window.innerHeight")
            scroll_amount = viewport_height * amount / 3

            if direction.lower() == "down":
                await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
            elif direction.lower() == "up":
                await page.evaluate(f"window.scrollBy(0, -{scroll_amount})")
            elif direction.lower() == "left":
                await page.evaluate(f"window.scrollBy(-{scroll_amount}, 0)")
            elif direction.lower() == "right":
                await page.evaluate(f"window.scrollBy({scroll_amount}, 0)")

            target = "page"

        # Get current scroll position
        scroll_pos = await page.evaluate("""
            () => ({
                x: window.pageXOffset,
                y: window.pageYOffset
            })
        """)

        emit_success(f"Scrolled {target} {direction}", message_group=group_id)

        return {
            "success": True,
            "direction": direction,
            "amount": amount,
            "target": target,
            "scroll_position": scroll_pos,
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "direction": direction,
            "element_selector": element_selector,
        }


async def scroll_to_element(
    selector: str,
    timeout: int = 10000,
) -> Dict[str, Any]:
    """Scroll to bring an element into view."""
    group_id = generate_group_id("browser_scroll_to_element", selector[:100])
    emit_info(
        f"BROWSER SCROLL TO ELEMENT 🎯 selector='{selector}'",
        message_group=group_id,
    )
    try:
        browser_manager = get_camoufox_manager()
        page = await browser_manager.get_current_page()

        if not page:
            return {"success": False, "error": "No active browser page available"}

        element = page.locator(selector)
        await element.wait_for(state="attached", timeout=timeout)
        await element.scroll_into_view_if_needed()

        # Check if element is now visible
        is_visible = await element.is_visible()

        emit_success(f"Scrolled to element: {selector}", message_group=group_id)

        return {"success": True, "selector": selector, "visible": is_visible}

    except Exception as e:
        return {"success": False, "error": str(e), "selector": selector}


async def set_viewport_size(
    width: int,
    height: int,
) -> Dict[str, Any]:
    """Set the viewport size."""
    group_id = generate_group_id("browser_set_viewport", f"{width}x{height}")
    emit_info(
        f"BROWSER SET VIEWPORT 🖥️ size={width}x{height}",
        message_group=group_id,
    )
    try:
        browser_manager = get_camoufox_manager()
        page = await browser_manager.get_current_page()

        if not page:
            return {"success": False, "error": "No active browser page available"}

        await page.set_viewport_size({"width": width, "height": height})

        emit_success(
            f"Set viewport size to {width}x{height}",
            message_group=group_id,
        )

        return {"success": True, "width": width, "height": height}

    except Exception as e:
        return {"success": False, "error": str(e), "width": width, "height": height}


async def wait_for_element(
    selector: str,
    state: str = "visible",
    timeout: int = 30000,
) -> Dict[str, Any]:
    """Wait for an element to reach a specific state."""
    group_id = generate_group_id("browser_wait_for_element", f"{selector[:50]}_{state}")
    emit_info(
        f"BROWSER WAIT FOR ELEMENT ⏱️ selector='{selector}' state={state} timeout={timeout}ms",
        message_group=group_id,
    )
    try:
        browser_manager = get_camoufox_manager()
        page = await browser_manager.get_current_page()

        if not page:
            return {"success": False, "error": "No active browser page available"}

        element = page.locator(selector)
        await element.wait_for(state=state, timeout=timeout)

        emit_success(f"Element {selector} is now {state}", message_group=group_id)

        return {"success": True, "selector": selector, "state": state}

    except Exception as e:
        return {"success": False, "error": str(e), "selector": selector, "state": state}


async def highlight_element(
    selector: str,
    color: str = "red",
    timeout: int = 10000,
) -> Dict[str, Any]:
    """Highlight an element with a colored border."""
    group_id = generate_group_id(
        "browser_highlight_element", f"{selector[:50]}_{color}"
    )
    emit_info(
        f"BROWSER HIGHLIGHT ELEMENT 🔦 selector='{selector}' color={color}",
        message_group=group_id,
    )
    try:
        browser_manager = get_camoufox_manager()
        page = await browser_manager.get_current_page()

        if not page:
            return {"success": False, "error": "No active browser page available"}

        element = page.locator(selector)
        await element.wait_for(state="visible", timeout=timeout)

        # Add highlight style
        highlight_script = f"""
            el => {{
                el.style.outline = '3px solid {color}';
                el.style.outlineOffset = '2px';
                el.style.backgroundColor = '{color}20';  // 20% opacity
                el.setAttribute('data-highlighted', 'true');
            }}
        """

        await element.evaluate(highlight_script)

        emit_success(f"Highlighted element: {selector}", message_group=group_id)

        return {"success": True, "selector": selector, "color": color}

    except Exception as e:
        return {"success": False, "error": str(e), "selector": selector}


async def clear_highlights() -> Dict[str, Any]:
    """Clear all element highlights."""
    group_id = generate_group_id("browser_clear_highlights")
    emit_info(
        "BROWSER CLEAR HIGHLIGHTS 🧹",
        message_group=group_id,
    )
    try:
        browser_manager = get_camoufox_manager()
        page = await browser_manager.get_current_page()

        if not page:
            return {"success": False, "error": "No active browser page available"}

        # Remove all highlights
        clear_script = """
            () => {
                const highlighted = document.querySelectorAll('[data-highlighted="true"]');
                highlighted.forEach(el => {
                    el.style.outline = '';
                    el.style.outlineOffset = '';
                    el.style.backgroundColor = '';
                    el.removeAttribute('data-highlighted');
                });
                return highlighted.length;
            }
        """

        count = await page.evaluate(clear_script)

        emit_success(f"Cleared {count} highlights", message_group=group_id)

        return {"success": True, "cleared_count": count}

    except Exception as e:
        return {"success": False, "error": str(e)}


# Tool registration functions
def register_execute_javascript(agent):
    """Register the JavaScript execution tool."""

    @agent.tool
    async def browser_execute_js(
        context: RunContext,
        script: str,
        timeout: int = 30000,
    ) -> Dict[str, Any]:
        """
        Execute JavaScript code in the browser context.

        Args:
            script: JavaScript code to execute
            timeout: Timeout in milliseconds

        Returns:
            Dict with execution results
        """
        return await execute_javascript(script, timeout)


def register_scroll_page(agent):
    """Register the scroll page tool."""

    @agent.tool
    async def browser_scroll(
        context: RunContext,
        direction: str = "down",
        amount: int = 3,
        element_selector: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Scroll the page or a specific element.

        Args:
            direction: Scroll direction (up, down, left, right)
            amount: Scroll amount multiplier (1-10)
            element_selector: Optional selector to scroll specific element

        Returns:
            Dict with scroll results
        """
        return await scroll_page(direction, amount, element_selector)


def register_scroll_to_element(agent):
    """Register the scroll to element tool."""

    @agent.tool
    async def browser_scroll_to_element(
        context: RunContext,
        selector: str,
        timeout: int = 10000,
    ) -> Dict[str, Any]:
        """
        Scroll to bring an element into view.

        Args:
            selector: CSS or XPath selector for the element
            timeout: Timeout in milliseconds

        Returns:
            Dict with scroll results
        """
        return await scroll_to_element(selector, timeout)


def register_set_viewport_size(agent):
    """Register the viewport size tool."""

    @agent.tool
    async def browser_set_viewport(
        context: RunContext,
        width: int,
        height: int,
    ) -> Dict[str, Any]:
        """
        Set the browser viewport size.

        Args:
            width: Viewport width in pixels
            height: Viewport height in pixels

        Returns:
            Dict with viewport size results
        """
        return await set_viewport_size(width, height)


def register_wait_for_element(agent):
    """Register the wait for element tool."""

    @agent.tool
    async def browser_wait_for_element(
        context: RunContext,
        selector: str,
        state: str = "visible",
        timeout: int = 30000,
    ) -> Dict[str, Any]:
        """
        Wait for an element to reach a specific state.

        Args:
            selector: CSS or XPath selector for the element
            state: State to wait for (visible, hidden, attached, detached)
            timeout: Timeout in milliseconds

        Returns:
            Dict with wait results
        """
        return await wait_for_element(selector, state, timeout)


def register_browser_highlight_element(agent):
    """Register the element highlighting tool."""

    @agent.tool
    async def browser_highlight_element(
        context: RunContext,
        selector: str,
        color: str = "red",
        timeout: int = 10000,
    ) -> Dict[str, Any]:
        """
        Highlight an element with a colored border for visual identification.

        Args:
            selector: CSS or XPath selector for the element
            color: Highlight color (red, blue, green, yellow, etc.)
            timeout: Timeout in milliseconds

        Returns:
            Dict with highlight results
        """
        return await highlight_element(selector, color, timeout)


def register_browser_clear_highlights(agent):
    """Register the clear highlights tool."""

    @agent.tool
    async def browser_clear_highlights(context: RunContext) -> Dict[str, Any]:
        """
        Clear all element highlights from the page.

        Returns:
            Dict with clear results
        """
        return await clear_highlights()
