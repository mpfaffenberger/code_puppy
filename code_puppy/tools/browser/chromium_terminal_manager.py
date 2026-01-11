"""Chromium Terminal Manager - Simple Chromium browser for terminal use.

This module provides a singleton manager for a Chromium browser instance
optimized for terminal/CLI use cases. Unlike CamoufoxManager, this is
a simple, non-privacy-focused browser that runs in visible mode by default.
"""

import logging
from pathlib import Path
from typing import Optional

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from code_puppy import config
from code_puppy.messaging import emit_info, emit_success

logger = logging.getLogger(__name__)


class ChromiumTerminalManager:
    """Singleton browser manager for Chromium terminal automation.

    This manager provides a simple Chromium browser instance for terminal use.
    Unlike CamoufoxManager, it doesn't include privacy features - just a
    straightforward Chromium browser that's visible by default.

    Key features:
    - Singleton pattern ensures only one browser instance
    - Persistent profile directory for consistent state across runs
    - Visible (headless=False) by default for terminal use
    - Simple API: initialize, get_current_page, new_page, close

    Usage:
        manager = get_chromium_terminal_manager()
        await manager.async_initialize()
        page = await manager.get_current_page()
        await page.goto("https://example.com")
        await manager.close()
    """

    _instance: Optional["ChromiumTerminalManager"] = None
    _browser: Optional[Browser] = None
    _context: Optional[BrowserContext] = None
    _playwright: Optional[object] = None  # Store playwright instance for cleanup
    _initialized: bool = False

    def __new__(cls) -> "ChromiumTerminalManager":
        """Create or return the singleton instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize manager settings (only runs once due to singleton)."""
        # Only initialize once
        if hasattr(self, "_init_done"):
            return
        self._init_done = True

        # Default to headless=False - we want to see the terminal browser!
        # Can override with CHROMIUM_HEADLESS=true if needed
        import os

        self.headless = os.getenv("CHROMIUM_HEADLESS", "false").lower() == "true"

        # Persistent profile directory for consistent browser state across runs
        self.profile_dir = self._get_profile_directory()

        logger.debug(
            f"ChromiumTerminalManager initialized: headless={self.headless}, "
            f"profile={self.profile_dir}"
        )

    @classmethod
    def get_instance(cls) -> "ChromiumTerminalManager":
        """Get the singleton instance.

        Returns:
            The singleton ChromiumTerminalManager instance.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_profile_directory(self) -> Path:
        """Get or create the persistent profile directory.

        Uses XDG_CACHE_HOME/code_puppy/chromium_terminal_profile for storing
        browser data (cookies, history, bookmarks, etc.).

        Returns:
            Path to the profile directory.
        """
        cache_dir = Path(config.CACHE_DIR)
        profile_path = cache_dir / "chromium_terminal_profile"
        profile_path.mkdir(parents=True, exist_ok=True, mode=0o700)
        return profile_path

    async def async_initialize(self) -> None:
        """Initialize the Chromium browser.

        Launches a Chromium browser with a persistent context. The browser
        runs in visible mode by default (headless=False) for terminal use.

        Raises:
            Exception: If browser initialization fails.
        """
        if self._initialized:
            logger.debug("ChromiumTerminalManager already initialized")
            return

        try:
            emit_info("Initializing Chromium terminal browser...")
            emit_info(f"Using persistent profile: {self.profile_dir}")

            # Start Playwright
            self._playwright = await async_playwright().start()

            # Launch persistent context (keeps profile data between sessions)
            self._context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                headless=self.headless,
            )

            # Get browser reference from context
            self._browser = self._context.browser
            self._initialized = True

            emit_success("Chromium terminal browser initialized")
            logger.info(
                f"Chromium initialized: headless={self.headless}, "
                f"profile={self.profile_dir}"
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

    async def _cleanup(self) -> None:
        """Clean up browser resources and save persistent state."""
        try:
            # Save browser state before closing
            if self._context:
                try:
                    storage_state_path = self.profile_dir / "storage_state.json"
                    await self._context.storage_state(path=str(storage_state_path))
                    logger.debug(f"Browser state saved to {storage_state_path}")
                except Exception as e:
                    logger.warning(f"Could not save storage state: {e}")

                await self._context.close()
                self._context = None

            if self._browser:
                await self._browser.close()
                self._browser = None

            if self._playwright:
                await self._playwright.stop()
                self._playwright = None

            self._initialized = False
            logger.debug("Browser resources cleaned up")

        except Exception as e:
            logger.warning(f"Warning during cleanup: {e}")

    async def close(self) -> None:
        """Close the browser and clean up all resources.

        This properly shuts down the browser, saves state, and releases
        all resources. Should be called when done with the browser.
        """
        await self._cleanup()
        emit_info("Chromium terminal browser closed")

    def __del__(self) -> None:
        """Ensure cleanup on object destruction.

        Note: Can't reliably use async in __del__, so this is best-effort.
        Always prefer calling close() explicitly.
        """
        if self._initialized:
            import asyncio

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self._cleanup())
                else:
                    loop.run_until_complete(self._cleanup())
            except Exception:
                pass  # Best effort cleanup


def get_chromium_terminal_manager() -> ChromiumTerminalManager:
    """Get the singleton ChromiumTerminalManager instance.

    This is the recommended way to access the ChromiumTerminalManager.

    Returns:
        The singleton ChromiumTerminalManager instance.

    Example:
        manager = get_chromium_terminal_manager()
        await manager.async_initialize()
        page = await manager.get_current_page()
    """
    return ChromiumTerminalManager.get_instance()
