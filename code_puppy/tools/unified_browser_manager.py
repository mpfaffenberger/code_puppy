"""Unified browser manager that can switch between Playwright and Camoufox."""

from typing import Literal, Optional, Union

from playwright.async_api import Page

from .browser_manager import PlaywrightManager
from .camoufox_manager import CamoufoxManager

BrowserBackend = Literal["playwright", "camoufox"]


class UnifiedBrowserManager:
    """Manager that can switch between Playwright and Camoufox backends."""

    _instance: Optional["UnifiedBrowserManager"] = None
    _current_backend: BrowserBackend = "camoufox"
    _playwright_manager: Optional[PlaywrightManager] = None
    _camoufox_manager: Optional[CamoufoxManager] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_init_done"):
            return
        self._init_done = True

    @classmethod
    def get_instance(cls) -> "UnifiedBrowserManager":
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_backend(self, backend: BrowserBackend) -> None:
        """Switch between browser backends."""
        self._current_backend = backend

    def get_current_backend(self) -> BrowserBackend:
        """Get the currently active backend."""
        return self._current_backend

    def _get_active_manager(self) -> Union[PlaywrightManager, CamoufoxManager]:
        """Get the currently active browser manager."""
        if self._current_backend == "camoufox":
            if self._camoufox_manager is None:
                from .camoufox_manager import get_camoufox_manager
                self._camoufox_manager = get_camoufox_manager()
            return self._camoufox_manager
        else:
            if self._playwright_manager is None:
                from .browser_manager import get_browser_manager
                self._playwright_manager = get_browser_manager()
            return self._playwright_manager

    async def async_initialize(self, **kwargs) -> None:
        """Initialize the active browser backend."""
        manager = self._get_active_manager()

        # Set common properties
        for key, value in kwargs.items():
            if hasattr(manager, key):
                setattr(manager, key, value)

        await manager.async_initialize()

    async def get_current_page(self) -> Optional[Page]:
        """Get the currently active page."""
        manager = self._get_active_manager()
        return await manager.get_current_page()

    async def new_page(self, url: Optional[str] = None) -> Page:
        """Create a new page."""
        manager = self._get_active_manager()
        return await manager.new_page(url)

    async def close_page(self, page: Page) -> None:
        """Close a specific page."""
        manager = self._get_active_manager()
        await manager.close_page(page)

    async def get_all_pages(self) -> list[Page]:
        """Get all open pages."""
        manager = self._get_active_manager()
        return await manager.get_all_pages()

    async def close(self) -> None:
        """Close the active browser."""
        manager = self._get_active_manager()
        await manager.close()

    async def close_all(self) -> None:
        """Close all browser instances (both backends)."""
        if self._playwright_manager and self._playwright_manager._initialized:
            await self._playwright_manager.close()
        if self._camoufox_manager and self._camoufox_manager._initialized:
            await self._camoufox_manager.close()

    @property
    def browser_type(self) -> str:
        """Get browser type based on backend."""
        if self._current_backend == "camoufox":
            return "camoufox"
        else:
            manager = self._get_active_manager()
            return getattr(manager, 'browser_type', 'chromium')

    @browser_type.setter
    def browser_type(self, value: str) -> None:
        """Set browser type (only applies to Playwright backend)."""
        if self._current_backend == "playwright":
            manager = self._get_active_manager()
            manager.browser_type = value

    @property
    def headless(self) -> bool:
        """Get headless mode."""
        manager = self._get_active_manager()
        return getattr(manager, 'headless', False)

    @headless.setter
    def headless(self, value: bool) -> None:
        """Set headless mode."""
        manager = self._get_active_manager()
        manager.headless = value

    @property
    def homepage(self) -> str:
        """Get homepage."""
        manager = self._get_active_manager()
        return getattr(manager, 'homepage', 'https://www.google.com')

    @homepage.setter
    def homepage(self, value: str) -> None:
        """Set homepage."""
        manager = self._get_active_manager()
        manager.homepage = value

    @property
    def _initialized(self) -> bool:
        """Check if the active browser is initialized."""
        manager = self._get_active_manager()
        return getattr(manager, '_initialized', False)


# Convenience function
def get_unified_browser_manager() -> UnifiedBrowserManager:
    """Get the singleton UnifiedBrowserManager instance."""
    return UnifiedBrowserManager.get_instance()
