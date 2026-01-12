"""Chromium Terminal Manager - Simple Chromium browser for terminal use.

This module provides a browser manager for Chromium terminal automation.
Each instance gets its own ephemeral browser context, allowing multiple
terminal QA agents to run simultaneously without profile conflicts.
"""

import logging
import uuid
from typing import Optional

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from code_puppy.messaging import emit_info, emit_success

logger = logging.getLogger(__name__)

# Store active manager instances by session ID
_active_managers: dict[str, "ChromiumTerminalManager"] = {}


class ChromiumTerminalManager:
    """Browser manager for Chromium terminal automation.

    Each instance gets its own ephemeral browser context, allowing multiple
    terminal QA agents to run simultaneously without profile conflicts.

    Key features:
    - Ephemeral contexts (no profile locking issues)
    - Multiple instances can run simultaneously
    - Visible (headless=False) by default for terminal use
    - Simple API: initialize, get_current_page, new_page, close

    Usage:
        manager = get_chromium_terminal_manager()  # or with session_id
        await manager.async_initialize()
        page = await manager.get_current_page()
        await page.goto("https://example.com")
        await manager.close()
    """

    _browser: Optional[Browser] = None
    _context: Optional[BrowserContext] = None
    _playwright: Optional[object] = None
    _initialized: bool = False

    def __init__(self, session_id: Optional[str] = None) -> None:
        """Initialize manager settings.

        Args:
            session_id: Optional session ID for tracking this instance.
                If None, a UUID will be generated.
        """
        import os

        self.session_id = session_id or str(uuid.uuid4())[:8]

        # Default to headless=False - we want to see the terminal browser!
        # Can override with CHROMIUM_HEADLESS=true if needed
        self.headless = os.getenv("CHROMIUM_HEADLESS", "false").lower() == "true"

        logger.debug(
            f"ChromiumTerminalManager created: session={self.session_id}, "
            f"headless={self.headless}"
        )

    async def async_initialize(self) -> None:
        """Initialize the Chromium browser.

        Launches a Chromium browser with an ephemeral context. The browser
        runs in visible mode by default (headless=False) for terminal use.

        Raises:
            Exception: If browser initialization fails.
        """
        if self._initialized:
            logger.debug(
                f"ChromiumTerminalManager {self.session_id} already initialized"
            )
            return

        try:
            emit_info(
                f"Initializing Chromium terminal browser (session: {self.session_id})..."
            )

            # Start Playwright
            self._playwright = await async_playwright().start()

            # Launch browser (not persistent - allows multiple instances)
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
            )

            # Create ephemeral context
            self._context = await self._browser.new_context()
            self._initialized = True

            emit_success(
                f"Chromium terminal browser initialized (session: {self.session_id})"
            )
            logger.info(
                f"Chromium initialized: session={self.session_id}, headless={self.headless}"
            )

        except Exception as e:
            logger.error(f"Failed to initialize Chromium: {e}")
            await self._cleanup()
            raise

    async def get_current_page(self) -> Optional[Page]:
        """Get the currently active page, creating one if none exist.

        Lazily initializes the browser if not already initialized.

        Returns:
            The current page, or None if context is unavailable.
        """
        if not self._initialized or not self._context:
            await self.async_initialize()

        if not self._context:
            logger.warning("No browser context available")
            return None

        pages = self._context.pages
        if pages:
            return pages[0]

        # Create a new blank page if none exist
        logger.debug("No existing pages, creating new blank page")
        return await self._context.new_page()

    async def new_page(self, url: Optional[str] = None) -> Page:
        """Create a new page, optionally navigating to a URL.

        Lazily initializes the browser if not already initialized.

        Args:
            url: Optional URL to navigate to after creating the page.

        Returns:
            The newly created page.

        Raises:
            RuntimeError: If browser context is not available.
        """
        if not self._initialized:
            await self.async_initialize()

        if not self._context:
            raise RuntimeError("Browser context not available")

        page = await self._context.new_page()
        logger.debug(f"Created new page{f' navigating to {url}' if url else ''}")

        if url:
            await page.goto(url)

        return page

    async def close_page(self, page: Page) -> None:
        """Close a specific page.

        Args:
            page: The page to close.
        """
        await page.close()
        logger.debug("Page closed")

    async def get_all_pages(self) -> list[Page]:
        """Get all open pages.

        Returns:
            List of all open pages, or empty list if no context.
        """
        if not self._context:
            return []
        return self._context.pages

    async def _cleanup(self, silent: bool = False) -> None:
        """Clean up browser resources.

        Args:
            silent: If True, suppress all errors (used during shutdown).
        """
        try:
            if self._context:
                try:
                    await self._context.close()
                except Exception:
                    pass
                self._context = None

            if self._browser:
                try:
                    await self._browser.close()
                except Exception:
                    pass
                self._browser = None

            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass
                self._playwright = None

            self._initialized = False

            # Remove from active managers
            if self.session_id in _active_managers:
                del _active_managers[self.session_id]

            if not silent:
                logger.debug(
                    f"Browser resources cleaned up (session: {self.session_id})"
                )

        except Exception as e:
            if not silent:
                logger.warning(f"Warning during cleanup: {e}")

    async def close(self) -> None:
        """Close the browser and clean up all resources.

        This properly shuts down the browser and releases all resources.
        Should be called when done with the browser.
        """
        await self._cleanup()
        emit_info(f"Chromium terminal browser closed (session: {self.session_id})")


def get_chromium_terminal_manager(
    session_id: Optional[str] = None,
) -> ChromiumTerminalManager:
    """Get or create a ChromiumTerminalManager instance.

    Args:
        session_id: Optional session ID. If provided and a manager with this
            session exists, returns that manager. Otherwise creates a new one.
            If None, uses 'default' as the session ID.

    Returns:
        A ChromiumTerminalManager instance.

    Example:
        # Default session (for single-agent use)
        manager = get_chromium_terminal_manager()

        # Named session (for multi-agent use)
        manager = get_chromium_terminal_manager("agent-1")
    """
    session_id = session_id or "default"

    if session_id not in _active_managers:
        _active_managers[session_id] = ChromiumTerminalManager(session_id)

    return _active_managers[session_id]
