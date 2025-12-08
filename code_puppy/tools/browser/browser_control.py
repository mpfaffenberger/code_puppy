"""Browser initialization and control tools."""

from typing import Any, Dict, Optional

from pydantic_ai import RunContext

from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning
from code_puppy.tools.common import generate_group_id

from .camoufox_manager import get_camoufox_manager


async def initialize_browser(
    headless: bool = False,
    browser_type: str = "chromium",
    homepage: str = "https://www.google.com",
) -> Dict[str, Any]:
    """Initialize the browser with specified settings."""
    group_id = generate_group_id("browser_initialize", f"{browser_type}_{homepage}")
    emit_info(
        f"BROWSER INITIALIZE 🌐 {browser_type} → {homepage}",
        message_group=group_id,
    )
    try:
        browser_manager = get_camoufox_manager()

        # Configure browser settings
        browser_manager.headless = headless
        browser_manager.browser_type = browser_type
        browser_manager.homepage = homepage

        # Initialize browser
        await browser_manager.async_initialize()

        # Get page info
        page = await browser_manager.get_current_page()
        if page:
            url = page.url
            title = await page.title()
        else:
            url = "Unknown"
            title = "Unknown"

        # emit_info(
        #     "[green]Browser initialized successfully[/green]", message_group=group_id
        # )  # Removed to reduce console spam

        return {
            "success": True,
            "browser_type": browser_type,
            "headless": headless,
            "homepage": homepage,
            "current_url": url,
            "current_title": title,
        }

    except Exception as e:
        emit_error(
            f"Browser initialization failed: {str(e)}",
            message_group=group_id,
        )
        return {
            "success": False,
            "error": str(e),
            "browser_type": browser_type,
            "headless": headless,
        }


async def close_browser() -> Dict[str, Any]:
    """Close the browser and clean up resources."""
    group_id = generate_group_id("browser_close")
    emit_info(
        "BROWSER CLOSE 🔒",
        message_group=group_id,
    )
    try:
        browser_manager = get_camoufox_manager()
        await browser_manager.close()

        emit_warning("Browser closed successfully", message_group=group_id)

        return {"success": True, "message": "Browser closed"}

    except Exception as e:
        return {"success": False, "error": str(e)}


async def get_browser_status() -> Dict[str, Any]:
    """Get current browser status and information."""
    group_id = generate_group_id("browser_status")
    emit_info(
        "BROWSER STATUS 📊",
        message_group=group_id,
    )
    try:
        browser_manager = get_camoufox_manager()

        if not browser_manager._initialized:
            return {
                "success": True,
                "status": "not_initialized",
                "browser_type": browser_manager.browser_type,
                "headless": browser_manager.headless,
            }

        page = await browser_manager.get_current_page()
        if page:
            url = page.url
            title = await page.title()

            # Get all pages
            all_pages = await browser_manager.get_all_pages()
            page_count = len(all_pages)
        else:
            url = None
            title = None
            page_count = 0

        return {
            "success": True,
            "status": "initialized",
            "browser_type": browser_manager.browser_type,
            "headless": browser_manager.headless,
            "current_url": url,
            "current_title": title,
            "page_count": page_count,
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


async def create_new_page(url: Optional[str] = None) -> Dict[str, Any]:
    """Create a new browser page/tab."""
    group_id = generate_group_id("browser_new_page", url or "blank")
    emit_info(
        f"BROWSER NEW PAGE 📄 {url or 'blank page'}",
        message_group=group_id,
    )
    try:
        browser_manager = get_camoufox_manager()

        if not browser_manager._initialized:
            return {
                "success": False,
                "error": "Browser not initialized. Use browser_initialize first.",
            }

        page = await browser_manager.new_page(url)

        final_url = page.url
        title = await page.title()

        emit_success(f"Created new page: {final_url}", message_group=group_id)

        return {"success": True, "url": final_url, "title": title, "requested_url": url}

    except Exception as e:
        return {"success": False, "error": str(e), "url": url}


async def list_pages() -> Dict[str, Any]:
    """List all open browser pages/tabs."""
    group_id = generate_group_id("browser_list_pages")
    emit_info(
        "BROWSER LIST PAGES 📋",
        message_group=group_id,
    )
    try:
        browser_manager = get_camoufox_manager()

        if not browser_manager._initialized:
            return {"success": False, "error": "Browser not initialized"}

        all_pages = await browser_manager.get_all_pages()

        pages_info = []
        for i, page in enumerate(all_pages):
            try:
                url = page.url
                title = await page.title()
                is_closed = page.is_closed()

                pages_info.append(
                    {"index": i, "url": url, "title": title, "closed": is_closed}
                )
            except Exception as e:
                pages_info.append(
                    {
                        "index": i,
                        "url": "Error",
                        "title": "Error",
                        "error": str(e),
                        "closed": True,
                    }
                )

        return {"success": True, "page_count": len(all_pages), "pages": pages_info}

    except Exception as e:
        return {"success": False, "error": str(e)}


# Tool registration functions
def register_initialize_browser(agent):
    """Register the browser initialization tool."""

    @agent.tool
    async def browser_initialize(
        context: RunContext,
        headless: bool = False,
        browser_type: str = "chromium",
        homepage: str = "https://www.google.com",
    ) -> Dict[str, Any]:
        """
        Initialize the browser with specified settings. Must be called before using other browser tools.

        Args:
            headless: Run browser in headless mode (no GUI)
            browser_type: Browser engine (chromium, firefox, webkit)
            homepage: Initial page to load

        Returns:
            Dict with initialization results
        """
        return await initialize_browser(headless, browser_type, homepage)


def register_close_browser(agent):
    """Register the browser close tool."""

    @agent.tool
    async def browser_close(context: RunContext) -> Dict[str, Any]:
        """
        Close the browser and clean up all resources.

        Returns:
            Dict with close results
        """
        return await close_browser()


def register_get_browser_status(agent):
    """Register the browser status tool."""

    @agent.tool
    async def browser_status(context: RunContext) -> Dict[str, Any]:
        """
        Get current browser status and information.

        Returns:
            Dict with browser status and metadata
        """
        return await get_browser_status()


def register_create_new_page(agent):
    """Register the new page creation tool."""

    @agent.tool
    async def browser_new_page(
        context: RunContext,
        url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new browser page/tab.

        Args:
            url: Optional URL to navigate to in the new page

        Returns:
            Dict with new page results
        """
        return await create_new_page(url)


def register_list_pages(agent):
    """Register the list pages tool."""

    @agent.tool
    async def browser_list_pages(context: RunContext) -> Dict[str, Any]:
        """
        List all open browser pages/tabs.

        Returns:
            Dict with information about all open pages
        """
        return await list_pages()
