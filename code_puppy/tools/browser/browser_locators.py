"""Browser element discovery tools using semantic locators and XPath."""

from typing import Any, Dict, Optional

from pydantic_ai import RunContext

from code_puppy.messaging import emit_info, emit_success
from code_puppy.tools.common import generate_group_id

from .camoufox_manager import get_camoufox_manager


async def find_by_role(
    role: str,
    name: Optional[str] = None,
    exact: bool = False,
    timeout: int = 10000,
) -> Dict[str, Any]:
    """Find elements by ARIA role."""
    group_id = generate_group_id("browser_find_by_role", f"{role}_{name or 'any'}")
    emit_info(
        f"BROWSER FIND BY ROLE 🎨 role={role} name={name}",
        message_group=group_id,
    )
    try:
        browser_manager = get_camoufox_manager()
        page = await browser_manager.get_current_page()

        if not page:
            return {"success": False, "error": "No active browser page available"}

        # Build locator
        locator = page.get_by_role(role, name=name, exact=exact)

        # Wait for at least one element
        await locator.first.wait_for(state="visible", timeout=timeout)

        # Count elements
        count = await locator.count()

        # Get element info
        elements = []
        for i in range(min(count, 10)):  # Limit to first 10 elements
            element = locator.nth(i)
            if await element.is_visible():
                text = await element.text_content()
                elements.append({"index": i, "text": text, "visible": True})

        emit_success(
            f"Found {count} elements with role '{role}'",
            message_group=group_id,
        )

        return {
            "success": True,
            "role": role,
            "name": name,
            "count": count,
            "elements": elements,
        }

    except Exception as e:
        return {"success": False, "error": str(e), "role": role, "name": name}


async def find_by_text(
    text: str,
    exact: bool = False,
    timeout: int = 10000,
) -> Dict[str, Any]:
    """Find elements containing specific text."""
    group_id = generate_group_id("browser_find_by_text", text[:50])
    emit_info(
        f"BROWSER FIND BY TEXT 🔍 text='{text}' exact={exact}",
        message_group=group_id,
    )
    try:
        browser_manager = get_camoufox_manager()
        page = await browser_manager.get_current_page()

        if not page:
            return {"success": False, "error": "No active browser page available"}

        locator = page.get_by_text(text, exact=exact)

        # Wait for at least one element
        await locator.first.wait_for(state="visible", timeout=timeout)

        count = await locator.count()

        elements = []
        for i in range(min(count, 10)):
            element = locator.nth(i)
            if await element.is_visible():
                tag_name = await element.evaluate("el => el.tagName.toLowerCase()")
                full_text = await element.text_content()
                elements.append(
                    {"index": i, "tag": tag_name, "text": full_text, "visible": True}
                )

        emit_success(
            f"Found {count} elements containing text '{text}'",
            message_group=group_id,
        )

        return {
            "success": True,
            "search_text": text,
            "exact": exact,
            "count": count,
            "elements": elements,
        }

    except Exception as e:
        return {"success": False, "error": str(e), "search_text": text}


async def find_by_label(
    text: str,
    exact: bool = False,
    timeout: int = 10000,
) -> Dict[str, Any]:
    """Find form elements by their associated label text."""
    group_id = generate_group_id("browser_find_by_label", text[:50])
    emit_info(
        f"BROWSER FIND BY LABEL 🏷️ label='{text}' exact={exact}",
        message_group=group_id,
    )
    try:
        browser_manager = get_camoufox_manager()
        page = await browser_manager.get_current_page()

        if not page:
            return {"success": False, "error": "No active browser page available"}

        locator = page.get_by_label(text, exact=exact)

        await locator.first.wait_for(state="visible", timeout=timeout)

        count = await locator.count()

        elements = []
        for i in range(min(count, 10)):
            element = locator.nth(i)
            if await element.is_visible():
                tag_name = await element.evaluate("el => el.tagName.toLowerCase()")
                input_type = await element.get_attribute("type")
                value = (
                    await element.input_value()
                    if tag_name in ["input", "textarea"]
                    else None
                )

                elements.append(
                    {
                        "index": i,
                        "tag": tag_name,
                        "type": input_type,
                        "value": value,
                        "visible": True,
                    }
                )

        emit_success(
            f"Found {count} elements with label '{text}'",
            message_group=group_id,
        )

        return {
            "success": True,
            "label_text": text,
            "exact": exact,
            "count": count,
            "elements": elements,
        }

    except Exception as e:
        return {"success": False, "error": str(e), "label_text": text}


async def find_by_placeholder(
    text: str,
    exact: bool = False,
    timeout: int = 10000,
) -> Dict[str, Any]:
    """Find elements by placeholder text."""
    group_id = generate_group_id("browser_find_by_placeholder", text[:50])
    emit_info(
        f"BROWSER FIND BY PLACEHOLDER 📝 placeholder='{text}' exact={exact}",
        message_group=group_id,
    )
    try:
        browser_manager = get_camoufox_manager()
        page = await browser_manager.get_current_page()

        if not page:
            return {"success": False, "error": "No active browser page available"}

        locator = page.get_by_placeholder(text, exact=exact)

        await locator.first.wait_for(state="visible", timeout=timeout)

        count = await locator.count()

        elements = []
        for i in range(min(count, 10)):
            element = locator.nth(i)
            if await element.is_visible():
                tag_name = await element.evaluate("el => el.tagName.toLowerCase()")
                placeholder = await element.get_attribute("placeholder")
                value = await element.input_value()

                elements.append(
                    {
                        "index": i,
                        "tag": tag_name,
                        "placeholder": placeholder,
                        "value": value,
                        "visible": True,
                    }
                )

        emit_success(
            f"Found {count} elements with placeholder '{text}'",
            message_group=group_id,
        )

        return {
            "success": True,
            "placeholder_text": text,
            "exact": exact,
            "count": count,
            "elements": elements,
        }

    except Exception as e:
        return {"success": False, "error": str(e), "placeholder_text": text}


async def find_by_test_id(
    test_id: str,
    timeout: int = 10000,
) -> Dict[str, Any]:
    """Find elements by test ID attribute."""
    group_id = generate_group_id("browser_find_by_test_id", test_id)
    emit_info(
        f"BROWSER FIND BY TEST ID 🧪 test_id='{test_id}'",
        message_group=group_id,
    )
    try:
        browser_manager = get_camoufox_manager()
        page = await browser_manager.get_current_page()

        if not page:
            return {"success": False, "error": "No active browser page available"}

        locator = page.get_by_test_id(test_id)

        await locator.first.wait_for(state="visible", timeout=timeout)

        count = await locator.count()

        elements = []
        for i in range(min(count, 10)):
            element = locator.nth(i)
            if await element.is_visible():
                tag_name = await element.evaluate("el => el.tagName.toLowerCase()")
                text = await element.text_content()

                elements.append(
                    {
                        "index": i,
                        "tag": tag_name,
                        "text": text,
                        "test_id": test_id,
                        "visible": True,
                    }
                )

        emit_success(
            f"Found {count} elements with test-id '{test_id}'",
            message_group=group_id,
        )

        return {
            "success": True,
            "test_id": test_id,
            "count": count,
            "elements": elements,
        }

    except Exception as e:
        return {"success": False, "error": str(e), "test_id": test_id}


async def run_xpath_query(
    xpath: str,
    timeout: int = 10000,
) -> Dict[str, Any]:
    """Find elements using XPath selector."""
    group_id = generate_group_id("browser_xpath_query", xpath[:100])
    emit_info(
        f"BROWSER XPATH QUERY 🔍 xpath='{xpath}'",
        message_group=group_id,
    )
    try:
        browser_manager = get_camoufox_manager()
        page = await browser_manager.get_current_page()

        if not page:
            return {"success": False, "error": "No active browser page available"}

        # Use page.locator with xpath
        locator = page.locator(f"xpath={xpath}")

        # Wait for at least one element
        await locator.first.wait_for(state="visible", timeout=timeout)

        count = await locator.count()

        elements = []
        for i in range(min(count, 10)):
            element = locator.nth(i)
            if await element.is_visible():
                tag_name = await element.evaluate("el => el.tagName.toLowerCase()")
                text = await element.text_content()
                class_name = await element.get_attribute("class")
                element_id = await element.get_attribute("id")

                elements.append(
                    {
                        "index": i,
                        "tag": tag_name,
                        "text": text[:100] if text else None,  # Truncate long text
                        "class": class_name,
                        "id": element_id,
                        "visible": True,
                    }
                )

        emit_success(
            f"Found {count} elements with XPath '{xpath}'",
            message_group=group_id,
        )

        return {"success": True, "xpath": xpath, "count": count, "elements": elements}

    except Exception as e:
        return {"success": False, "error": str(e), "xpath": xpath}


async def find_buttons(
    text_filter: Optional[str] = None, timeout: int = 10000
) -> Dict[str, Any]:
    """Find all button elements on the page."""
    group_id = generate_group_id("browser_find_buttons", text_filter or "all")
    emit_info(
        f"BROWSER FIND BUTTONS 🔘 filter='{text_filter or 'none'}'",
        message_group=group_id,
    )
    try:
        browser_manager = get_camoufox_manager()
        page = await browser_manager.get_current_page()

        if not page:
            return {"success": False, "error": "No active browser page available"}

        # Find buttons by role
        locator = page.get_by_role("button")

        count = await locator.count()

        buttons = []
        for i in range(min(count, 20)):  # Limit to 20 buttons
            button = locator.nth(i)
            if await button.is_visible():
                text = await button.text_content()
                if text_filter and text_filter.lower() not in text.lower():
                    continue

                buttons.append({"index": i, "text": text, "visible": True})

        filtered_count = len(buttons)

        emit_success(
            f"Found {filtered_count} buttons"
            + (f" containing '{text_filter}'" if text_filter else ""),
            message_group=group_id,
        )

        return {
            "success": True,
            "text_filter": text_filter,
            "total_count": count,
            "filtered_count": filtered_count,
            "buttons": buttons,
        }

    except Exception as e:
        return {"success": False, "error": str(e), "text_filter": text_filter}


async def find_links(
    text_filter: Optional[str] = None, timeout: int = 10000
) -> Dict[str, Any]:
    """Find all link elements on the page."""
    group_id = generate_group_id("browser_find_links", text_filter or "all")
    emit_info(
        f"BROWSER FIND LINKS 🔗 filter='{text_filter or 'none'}'",
        message_group=group_id,
    )
    try:
        browser_manager = get_camoufox_manager()
        page = await browser_manager.get_current_page()

        if not page:
            return {"success": False, "error": "No active browser page available"}

        # Find links by role
        locator = page.get_by_role("link")

        count = await locator.count()

        links = []
        for i in range(min(count, 20)):  # Limit to 20 links
            link = locator.nth(i)
            if await link.is_visible():
                text = await link.text_content()
                href = await link.get_attribute("href")

                if text_filter and text_filter.lower() not in text.lower():
                    continue

                links.append({"index": i, "text": text, "href": href, "visible": True})

        filtered_count = len(links)

        emit_success(
            f"Found {filtered_count} links"
            + (f" containing '{text_filter}'" if text_filter else ""),
            message_group=group_id,
        )

        return {
            "success": True,
            "text_filter": text_filter,
            "total_count": count,
            "filtered_count": filtered_count,
            "links": links,
        }

    except Exception as e:
        return {"success": False, "error": str(e), "text_filter": text_filter}


# Tool registration functions
def register_find_by_role(agent):
    """Register the find by role tool."""

    @agent.tool
    async def browser_find_by_role(
        context: RunContext,
        role: str,
        name: Optional[str] = None,
        exact: bool = False,
        timeout: int = 10000,
    ) -> Dict[str, Any]:
        """
        Find elements by ARIA role (recommended for accessibility).

        Args:
            role: ARIA role (button, link, textbox, heading, etc.)
            name: Optional accessible name to filter by
            exact: Whether to match name exactly
            timeout: Timeout in milliseconds

        Returns:
            Dict with found elements and their properties
        """
        return await find_by_role(role, name, exact, timeout)


def register_find_by_text(agent):
    """Register the find by text tool."""

    @agent.tool
    async def browser_find_by_text(
        context: RunContext,
        text: str,
        exact: bool = False,
        timeout: int = 10000,
    ) -> Dict[str, Any]:
        """
        Find elements containing specific text content.

        Args:
            text: Text to search for
            exact: Whether to match text exactly
            timeout: Timeout in milliseconds

        Returns:
            Dict with found elements and their properties
        """
        return await find_by_text(text, exact, timeout)


def register_find_by_label(agent):
    """Register the find by label tool."""

    @agent.tool
    async def browser_find_by_label(
        context: RunContext,
        text: str,
        exact: bool = False,
        timeout: int = 10000,
    ) -> Dict[str, Any]:
        """
        Find form elements by their associated label text.

        Args:
            text: Label text to search for
            exact: Whether to match label exactly
            timeout: Timeout in milliseconds

        Returns:
            Dict with found form elements and their properties
        """
        return await find_by_label(text, exact, timeout)


def register_find_by_placeholder(agent):
    """Register the find by placeholder tool."""

    @agent.tool
    async def browser_find_by_placeholder(
        context: RunContext,
        text: str,
        exact: bool = False,
        timeout: int = 10000,
    ) -> Dict[str, Any]:
        """
        Find elements by placeholder text.

        Args:
            text: Placeholder text to search for
            exact: Whether to match placeholder exactly
            timeout: Timeout in milliseconds

        Returns:
            Dict with found elements and their properties
        """
        return await find_by_placeholder(text, exact, timeout)


def register_find_by_test_id(agent):
    """Register the find by test ID tool."""

    @agent.tool
    async def browser_find_by_test_id(
        context: RunContext,
        test_id: str,
        timeout: int = 10000,
    ) -> Dict[str, Any]:
        """
        Find elements by test ID attribute (data-testid).

        Args:
            test_id: Test ID to search for
            timeout: Timeout in milliseconds

        Returns:
            Dict with found elements and their properties
        """
        return await find_by_test_id(test_id, timeout)


def register_run_xpath_query(agent):
    """Register the XPath query tool."""

    @agent.tool
    async def browser_xpath_query(
        context: RunContext,
        xpath: str,
        timeout: int = 10000,
    ) -> Dict[str, Any]:
        """
        Find elements using XPath selector (fallback when semantic locators fail).

        Args:
            xpath: XPath expression
            timeout: Timeout in milliseconds

        Returns:
            Dict with found elements and their properties
        """
        return await run_xpath_query(xpath, timeout)


def register_find_buttons(agent):
    """Register the find buttons tool."""

    @agent.tool
    async def browser_find_buttons(
        context: RunContext,
        text_filter: Optional[str] = None,
        timeout: int = 10000,
    ) -> Dict[str, Any]:
        """
        Find all button elements on the page.

        Args:
            text_filter: Optional text to filter buttons by
            timeout: Timeout in milliseconds

        Returns:
            Dict with found buttons and their properties
        """
        return await find_buttons(text_filter, timeout)


def register_find_links(agent):
    """Register the find links tool."""

    @agent.tool
    async def browser_find_links(
        context: RunContext,
        text_filter: Optional[str] = None,
        timeout: int = 10000,
    ) -> Dict[str, Any]:
        """
        Find all link elements on the page.

        Args:
            text_filter: Optional text to filter links by
            timeout: Timeout in milliseconds

        Returns:
            Dict with found links and their properties
        """
        return await find_links(text_filter, timeout)
