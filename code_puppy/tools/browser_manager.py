"""Clean, simplified browser manager for Camoufox (privacy-focused Firefox) automation in code_puppy."""

from typing import Optional

from playwright.async_api import Browser, BrowserContext, Page

from code_puppy.messaging import emit_info


class CamoufoxManager:
    """Singleton browser manager for Camoufox (privacy-focused Firefox) automation."""

    _instance: Optional["CamoufoxManager"] = None
    _browser: Optional[Browser] = None
    _context: Optional[BrowserContext] = None
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # Only initialize once
        if hasattr(self, "_init_done"):
            return
        self._init_done = True

        self.browser_type = "chromium"
        self.headless = False
        self.homepage = "https://www.google.com"

    @classmethod
    def get_instance(cls) -> "PlaywrightManager":
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def async_initialize(self) -> None:
        """Initialize Playwright and browser context."""
        if self._initialized:
            return

        try:
            emit_info("[yellow]Initializing Playwright browser...[/yellow]")

            # Start Playwright
            self._playwright = await async_playwright().start()

            # Launch browser with sensible defaults
            browser_kwargs = {
                "headless": self.headless,
                "args": [
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                ],
            }

            if self.browser_type == "chromium":
                self._browser = await self._playwright.chromium.launch(**browser_kwargs)
            elif self.browser_type == "firefox":
                self._browser = await self._playwright.firefox.launch(**browser_kwargs)
            elif self.browser_type == "webkit":
                self._browser = await self._playwright.webkit.launch(**browser_kwargs)
            else:
                raise ValueError(f"Unsupported browser type: {self.browser_type}")

            # Create context with reasonable defaults
            self._context = await self._browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                ignore_https_errors=True,
            )

            # Create initial page and navigate to homepage
            page = await self._context.new_page()
            await page.goto(self.homepage)

            self._initialized = True
            emit_info(
                f"[green]✅ Browser initialized successfully ({self.browser_type})[/green]"
            )

        except Exception as e:
            emit_info(f"[red]❌ Failed to initialize browser: {e}[/red]")
            await self._cleanup()
            raise

    async def get_current_page(self) -> Optional[Page]:
        """Get the currently active page."""
        if not self._initialized or not self._context:
            await self.async_initialize()

        if self._context:
            pages = self._context.pages
            return pages[0] if pages else None
        return None

    async def new_page(self, url: Optional[str] = None) -> Page:
        """Create a new page and optionally navigate to URL."""
        if not self._initialized:
            await self.async_initialize()

        page = await self._context.new_page()
        if url:
            await page.goto(url)
        return page

    async def close_page(self, page: Page) -> None:
        """Close a specific page."""
        await page.close()

    async def get_all_pages(self) -> list[Page]:
        """Get all open pages."""
        if not self._context:
            return []
        return self._context.pages

    async def _cleanup(self) -> None:
        """Clean up browser resources."""
        try:
            if self._context:
                await self._context.close()
                self._context = None
            if self._browser:
                await self._browser.close()
                self._browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
            self._initialized = False
        except Exception as e:
            emit_info(f"[yellow]Warning during cleanup: {e}[/yellow]")

    async def close(self) -> None:
        """Close the browser and clean up resources."""
        await self._cleanup()
        emit_info("[yellow]Browser closed[/yellow]")

    def __del__(self):
        """Ensure cleanup on object destruction."""
        # Note: Can't use async in __del__, so this is just a fallback
        if self._initialized:
            import asyncio

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self._cleanup())
                else:
                    loop.run_until_complete(self._cleanup())
            except:
                pass  # Best effort cleanup


# Convenience function for getting the singleton instance
def get_browser_manager() -> PlaywrightManager:
    """Get the singleton PlaywrightManager instance."""
    return PlaywrightManager.get_instance()
