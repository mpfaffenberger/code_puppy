"""Camoufox browser manager - privacy-focused Firefox automation."""

from typing import Optional

import camoufox
from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from code_puppy.messaging import emit_info
from camoufox.pkgman import CamoufoxFetcher
from camoufox.locale import ALLOW_GEOIP, download_mmdb
from camoufox.addons import maybe_download_addons, DefaultAddons


class CamoufoxManager:
    """Singleton browser manager for Camoufox (privacy-focused Firefox) automation."""

    _instance: Optional["CamoufoxManager"] = None
    _browser: Optional[Browser] = None
    _context: Optional[BrowserContext] = None
    _playwright: Optional[Playwright] = None
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
            
            # Ensure Camoufox binary and dependencies are fetched before launching
            await self._prefetch_camoufox()

            try:
                await self._initialize_camoufox()
                emit_info(
                    "[green]✅ Camoufox initialized successfully (privacy-focused Firefox)[/green]"
                )
            except Exception as camoufox_error:
                error_reason = str(camoufox_error).splitlines()[0]
                emit_info(
                    "[yellow]⚠️ Camoufox failed to initialize, falling back to Playwright Firefox[/yellow]"
                )
                await self._cleanup()
                await self._initialize_playwright_firefox(error_reason)

            self._initialized = True

        except Exception as e:
            emit_info(f"[red]❌ Failed to initialize browser: {e}[/red]")
            await self._cleanup()
            raise

    async def _initialize_camoufox(self) -> None:
        """Try to start Camoufox with the configured privacy settings."""
        camoufox_instance = camoufox.AsyncCamoufox(
            headless=self.headless,
            block_webrtc=self.block_webrtc,
            humanize=self.humanize,
        )
        self._browser = await camoufox_instance.start()
        self._context = await self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            ignore_https_errors=True,
        )
        page = await self._context.new_page()
        await page.goto(self.homepage)

    async def _initialize_playwright_firefox(self, error_reason: str) -> None:
        """Fallback to vanilla Playwright Firefox when Camoufox fails."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.firefox.launch(headless=self.headless)
        self._context = await self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            ignore_https_errors=True,
        )
        page = await self._context.new_page()
        await page.goto(self.homepage)
        emit_info(
            f"[green]✅ Playwright Firefox fallback ready (Camoufox error: {error_reason})[/green]"
        )

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

    async def _prefetch_camoufox(self) -> None:
        """Prefetch Camoufox binary and dependencies."""
        emit_info("[cyan]🔍 Ensuring Camoufox binary and dependencies are up-to-date...[/cyan]")
        
        # Fetch Camoufox binary if needed
        CamoufoxFetcher().install()
        
        # Fetch GeoIP database if enabled
        if ALLOW_GEOIP:
            download_mmdb()
        
        # Download default addons
        maybe_download_addons(list(DefaultAddons))
        
        emit_info("[cyan]📦 Camoufox dependencies ready[/cyan]")

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
