"""Camoufox browser manager - privacy-focused Firefox automation."""

import os
from pathlib import Path
from typing import Optional

from playwright.async_api import Browser, BrowserContext, Page

from code_puppy import config
from code_puppy.messaging import emit_info, emit_success, emit_warning


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

        # Default to headless=True (no browser spam during tests)
        # Override with BROWSER_HEADLESS=false to see the browser
        self.headless = os.getenv("BROWSER_HEADLESS", "true").lower() != "false"
        self.homepage = "https://www.google.com"
        # Camoufox-specific settings
        self.geoip = True  # Enable GeoIP spoofing
        self.block_webrtc = True  # Block WebRTC for privacy
        self.humanize = True  # Add human-like behavior

        # Persistent profile directory for consistent browser state across runs
        self.profile_dir = self._get_profile_directory()

    @classmethod
    def get_instance(cls) -> "CamoufoxManager":
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_profile_directory(self) -> Path:
        """Get or create the persistent profile directory (uses XDG_CACHE_HOME).

        Returns a Path object pointing to XDG_CACHE_HOME/code_puppy/camoufox_profile
        where browser data (cookies, history, bookmarks, etc.) will be stored.
        """
        cache_dir = Path(config.CACHE_DIR)
        profile_path = cache_dir / "camoufox_profile"
        profile_path.mkdir(parents=True, exist_ok=True, mode=0o700)
        return profile_path

    async def async_initialize(self) -> None:
        """Initialize Camoufox browser."""
        if self._initialized:
            return

        try:
            emit_info("Initializing Camoufox (privacy Firefox)...")

            # Ensure Camoufox binary and dependencies are fetched before launching
            await self._prefetch_camoufox()

            await self._initialize_camoufox()
            # emit_info(
            #     "[green]✅ Camoufox initialized successfully (privacy-focused Firefox)[/green]"
            # )  # Removed to reduce console spam
            self._initialized = True

        except Exception:
            await self._cleanup()
            raise

    async def _initialize_camoufox(self) -> None:
        """Try to start Camoufox with the configured privacy settings."""
        emit_info(f"Using persistent profile: {self.profile_dir}")
        # Lazy import camoufox to avoid triggering heavy optional deps at import time
        try:
            import camoufox
            from camoufox.addons import DefaultAddons

            camoufox_instance = camoufox.AsyncCamoufox(
                headless=self.headless,
                block_webrtc=self.block_webrtc,
                humanize=self.humanize,
                exclude_addons=list(DefaultAddons),
                persistent_context=True,
                user_data_dir=str(self.profile_dir),
                addons=[],
            )

            self._browser = camoufox_instance.browser
            if not self._initialized:
                self._context = await camoufox_instance.start()
                self._initialized = True
        except Exception:
            from playwright.async_api import async_playwright

            emit_warning(
                "Camoufox no disponible. Usando Playwright (Chromium) como alternativa."
            )
            pw = await async_playwright().start()
            # Use persistent context directory for Chromium to emulate previous behavior
            context = await pw.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir), headless=self.headless
            )
            self._context = context
            self._browser = context.browser
            self._initialized = True

    async def get_current_page(self) -> Optional[Page]:
        """Get the currently active page. Lazily creates one if none exist."""
        if not self._initialized or not self._context:
            await self.async_initialize()

        if not self._context:
            return None

        pages = self._context.pages
        if pages:
            return pages[0]

        # Lazily create a new blank page without navigation
        return await self._context.new_page()

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
        emit_info("Ensuring Camoufox binary and dependencies are up-to-date...")

        # Lazy import camoufox utilities to avoid side effects during module import
        try:
            from camoufox.exceptions import CamoufoxNotInstalled, UnsupportedVersion
            from camoufox.locale import ALLOW_GEOIP, download_mmdb
            from camoufox.pkgman import CamoufoxFetcher, camoufox_path
        except Exception:
            emit_warning(
                "Camoufox no disponible. Omitiendo prefetch y preparándose para usar Playwright."
            )
            return

        needs_install = False
        try:
            camoufox_path(download_if_missing=False)
            emit_info("Using cached Camoufox installation")
        except (CamoufoxNotInstalled, FileNotFoundError):
            emit_info("Camoufox not found, installing fresh copy")
            needs_install = True
        except UnsupportedVersion:
            emit_info("Camoufox update required, reinstalling")
            needs_install = True

        if needs_install:
            CamoufoxFetcher().install()

        # Fetch GeoIP database if enabled
        if ALLOW_GEOIP:
            download_mmdb()

        emit_info("Camoufox dependencies ready")

    async def close_page(self, page: Page) -> None:
        """Close a specific page."""
        await page.close()

    async def get_all_pages(self) -> list[Page]:
        """Get all open pages."""
        if not self._context:
            return []
        return self._context.pages

    async def _cleanup(self) -> None:
        """Clean up browser resources and save persistent state."""
        try:
            # Save browser state before closing (cookies, localStorage, etc.)
            if self._context:
                try:
                    storage_state_path = self.profile_dir / "storage_state.json"
                    await self._context.storage_state(path=str(storage_state_path))
                    emit_success(f"Browser state saved to {storage_state_path}")
                except Exception as e:
                    emit_warning(f"Could not save storage state: {e}")

                await self._context.close()
                self._context = None
            if self._browser:
                await self._browser.close()
                self._browser = None
            self._initialized = False
        except Exception as e:
            emit_warning(f"Warning during cleanup: {e}")

    async def close(self) -> None:
        """Close the browser and clean up resources."""
        await self._cleanup()
        emit_info("Camoufox browser closed")

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
            except Exception:
                pass  # Best effort cleanup


# Convenience function for getting the singleton instance
def get_camoufox_manager() -> CamoufoxManager:
    """Get the singleton CamoufoxManager instance."""
    return CamoufoxManager.get_instance()
