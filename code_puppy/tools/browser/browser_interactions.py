"""Browser element interaction tools for clicking, typing, and form manipulation."""

from typing import Any, Dict, List, Optional

from pydantic_ai import RunContext

from code_puppy.messaging import emit_error, emit_info, emit_success
from code_puppy.tools.common import generate_group_id

from .camoufox_manager import get_camoufox_manager


async def click_element(
    selector: str,
    timeout: int = 10000,
    force: bool = False,
    button: str = "left",
    modifiers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Click on an element."""
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

        # Find element
        element = page.locator(selector)

        # Wait for element to be visible and enabled
        await element.wait_for(state="visible", timeout=timeout)

        # Click options
        click_options = {
            "force": force,
            "button": button,
            "timeout": timeout,
        }

        if modifiers:
            click_options["modifiers"] = modifiers

        await element.click(**click_options)

        emit_success(f"Clicked element: {selector}", message_group=group_id)

        return {"success": True, "selector": selector, "action": f"{button}_click"}

    except Exception as e:
        emit_error(f"Click failed: {str(e)}", message_group=group_id)
        return {"success": False, "error": str(e), "selector": selector}


async def double_click_element(
    selector: str,
    timeout: int = 10000,
    force: bool = False,
) -> Dict[str, Any]:
    """Double-click on an element."""
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
        await element.wait_for(state="visible", timeout=timeout)
        await element.dblclick(force=force, timeout=timeout)

        emit_success(f"Double-clicked element: {selector}", message_group=group_id)

        return {"success": True, "selector": selector, "action": "double_click"}

    except Exception as e:
        return {"success": False, "error": str(e), "selector": selector}


async def hover_element(
    selector: str,
    timeout: int = 10000,
    force: bool = False,
) -> Dict[str, Any]:
    """Hover over an element."""
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
        await element.wait_for(state="visible", timeout=timeout)
        await element.hover(force=force, timeout=timeout)

        emit_success(f"Hovered over element: {selector}", message_group=group_id)

        return {"success": True, "selector": selector, "action": "hover"}

    except Exception as e:
        return {"success": False, "error": str(e), "selector": selector}


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
    ) -> Dict[str, Any]:
        """
        Click on an element in the browser.

        Args:
            selector: CSS or XPath selector for the element
            timeout: Timeout in milliseconds to wait for element
            force: Skip actionability checks and force the click
            button: Mouse button to click (left, right, middle)
            modifiers: Modifier keys to hold (Alt, Control, Meta, Shift)

        Returns:
            Dict with click results
        """
        return await click_element(selector, timeout, force, button, modifiers)


def register_double_click_element(agent):
    """Register the double-click element tool."""

    @agent.tool
    async def browser_double_click(
        context: RunContext,
        selector: str,
        timeout: int = 10000,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Double-click on an element in the browser.

        Args:
            selector: CSS or XPath selector for the element
            timeout: Timeout in milliseconds to wait for element
            force: Skip actionability checks and force the double-click

        Returns:
            Dict with double-click results
        """
        return await double_click_element(selector, timeout, force)


def register_hover_element(agent):
    """Register the hover element tool."""

    @agent.tool
    async def browser_hover(
        context: RunContext,
        selector: str,
        timeout: int = 10000,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Hover over an element in the browser.

        Args:
            selector: CSS or XPath selector for the element
            timeout: Timeout in milliseconds to wait for element
            force: Skip actionability checks and force the hover

        Returns:
            Dict with hover results
        """
        return await hover_element(selector, timeout, force)


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
