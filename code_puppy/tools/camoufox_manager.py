"""Camoufox browser manager - privacy-focused Firefox automation."""

from typing import Optional

import camoufox
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

        self.headless = False
        self.homepage = "https://www.google.com"
        # Camoufox-specific settings
        self.geoip = True  # Enable GeoIP spoofing
        self.block_webrtc = True  # Block WebRTC for privacy
        self.humanize = True  # Add human-like behavior

    @classmethod
    def get_instance(cls) -> "CamoufoxManager":
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def async_initialize(self) -> None:
        """Initialize Camoufox browser."""
        if self._initialized:
            return

        try:
            emit_info("[yellow]Initializing Camoufox (privacy Firefox)...[/yellow]")

            # Launch Camoufox with privacy settings
            self._browser = await camoufox.async_firefox(
                headless=self.headless,
                geoip=self.geoip,
                block_webrtc=self.block_webrtc,
                humanize=self.humanize,
                # Additional privacy settings
                os="windows",  # OS spoofing
                safe_browsing=False,  # Disable safe browsing
                screen="1920x1080",  # Screen resolution spoofing
            )

            # Create context (Camoufox handles most privacy settings automatically)
            self._context = await self._browser.new_context(
                viewport={"width": 1920, "height": 1080},
                ignore_https_errors=True,
            )

            # Create initial page and navigate to homepage
            page = await self._context.new_page()
            await page.goto(self.homepage)

            self._initialized = True
            emit_info(
                "[green]✅ Camoufox initialized successfully (privacy-focused Firefox)[/green]"
            )

        except Exception as e:
            emit_info(f"[red]❌ Failed to initialize Camoufox: {e}[/red]")
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
            self._initialized = False
        except Exception as e:
            emit_info(f"[yellow]Warning during cleanup: {e}[/yellow]")

    async def close(self) -> None:
        """Close the browser and clean up resources."""
        await self._cleanup()
        emit_info("[yellow]Camoufox browser closed[/yellow]")

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
def get_camoufox_manager() -> CamoufoxManager:
    """Get the singleton CamoufoxManager instance."""
    return CamoufoxManager.get_instance()
