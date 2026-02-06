"""Playwright browser manager for browser automation.

Supports multiple simultaneous instances with unique profile directories.
"""

import asyncio
import atexit
import contextvars
import os
from pathlib import Path
from typing import Callable, Dict, Optional

from playwright.async_api import Browser, BrowserContext, Page


from code_puppy import config
from code_puppy.messaging import emit_info, emit_success, emit_warning

# Registry for custom browser types from plugins (e.g., Camoufox for stealth browsing)
_CUSTOM_BROWSER_TYPES: Dict[str, Callable] = {}
_BROWSER_TYPES_LOADED: bool = False


def _load_plugin_browser_types() -> None:
    """Load custom browser types from plugins.

    This is called lazily on first browser initialization to allow plugins
    to register custom browser providers (like Camoufox for stealth browsing).
    """
    global _CUSTOM_BROWSER_TYPES, _BROWSER_TYPES_LOADED

    if _BROWSER_TYPES_LOADED:
        return

    _BROWSER_TYPES_LOADED = True

    try:
        from code_puppy.callbacks import on_register_browser_types

        results = on_register_browser_types()
        for result in results:
            if isinstance(result, dict):
                _CUSTOM_BROWSER_TYPES.update(result)
    except Exception:
        pass  # Don't break if plugins fail to load


# Store active manager instances by session ID
_active_managers: dict[str, "BrowserManager"] = {}

# Context variable for browser session - properly inherits through async tasks
# This allows parallel agent invocations to each have their own browser instance
_browser_session_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "browser_session", default=None
)


def set_browser_session(session_id: Optional[str]) -> contextvars.Token:
    """Set the browser session ID for the current context.

    This must be called BEFORE any tool calls that use the browser.
    The context will properly propagate to all subsequent async calls.

    Args:
        session_id: The session ID to use for browser operations.

    Returns:
        A token that can be used to reset the context.
    """
    return _browser_session_var.set(session_id)


def get_browser_session() -> Optional[str]:
    """Get the browser session ID for the current context.

    Returns:
        The current session ID, or None if not set.
    """
    return _browser_session_var.get()


def get_session_browser_manager() -> "BrowserManager":
    """Get the BrowserManager for the current context's session.

    This is the preferred way to get a browser manager in tool functions,
    as it automatically uses the correct session ID for the current
    agent context.

    Returns:
        A BrowserManager instance for the current session.
    """
    session_id = get_browser_session()
    return get_browser_manager(session_id)


# Flag to track if cleanup has already run
_cleanup_done: bool = False


class BrowserManager:
    """Browser manager for Playwright-based browser automation.

    Supports multiple simultaneous instances, each with its own profile directory.
    Uses Chromium by default for maximum compatibility.
    """

    _browser: Optional[Browser] = None
    _context: Optional[BrowserContext] = None
    _initialized: bool = False

    def __init__(
        self, session_id: Optional[str] = None, browser_type: Optional[str] = None
    ):
        """Initialize manager settings.

        Args:
            session_id: Optional session ID for this instance.
                If None, uses 'default' as the session ID.
            browser_type: Optional browser type to use. If None, uses Chromium.
                Custom types can be registered via the register_browser_types hook.
        """
        self.session_id = session_id or "default"
        self.browser_type = browser_type  # None means default Chromium

        # Default to headless=True (no browser spam during tests)
        # Override with BROWSER_HEADLESS=false to see the browser
        self.headless = os.getenv("BROWSER_HEADLESS", "true").lower() != "false"
        self.homepage = "https://www.google.com"

        # Browser type: 'chromium', 'firefox', 'webkit', or custom types via plugins
        # Default to chromium for maximum compatibility
        self.browser_type = os.getenv("BROWSER_TYPE", "chromium").lower()

        # Unique profile directory per session for browser state
        self.profile_dir = self._get_profile_directory()

        # Playwright instance (for standard browsers)
        self._playwright = None

    def _get_profile_directory(self) -> Path:
        """Get or create the profile directory.

        Each session gets its own profile directory under:
        XDG_CACHE_HOME/code_puppy/browser_profiles/<session_id>/

        Custom browser types (like Camoufox) may use their own profile
        management via the plugin system.
        """
        cache_dir = Path(config.CACHE_DIR)
        profiles_base = cache_dir / "browser_profiles"
        profile_path = profiles_base / self.session_id
        profile_path.mkdir(parents=True, exist_ok=True, mode=0o700)
        return profile_path

    async def async_initialize(self) -> None:
        """Initialize browser based on browser_type setting.

        Supported browser types:
        - 'chromium': Standard Playwright Chromium (default)
        - 'firefox': Standard Playwright Firefox
        - 'webkit': Standard Playwright WebKit
        - Custom types registered via the register_browser_types plugin hook
          (e.g., 'camoufox' for stealthy browsing)
        """
        if self._initialized:
            return

        try:
            emit_info(
                f"Initializing {self.browser_type} browser (session: {self.session_id})..."
            )
            await self._initialize_browser()

        except Exception:
            await self._cleanup()
            raise

    def _get_system_chrome_path(self) -> Optional[str]:
        """Find the system Chrome/Chromium executable path.

        Returns the path to the user's installed Chrome browser,
        or None if not found.
        """
        import platform
        import shutil

        system = platform.system()

        if system == "Darwin":  # macOS
            # Check common macOS Chrome locations
            chrome_paths = [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
                "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
                os.path.expanduser(
                    "~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
                ),
            ]
            for path in chrome_paths:
                if os.path.exists(path):
                    return path

        elif system == "Windows":
            # Check common Windows Chrome locations
            chrome_paths = [
                os.path.expandvars(
                    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"
                ),
                os.path.expandvars(
                    r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
                ),
                os.path.expandvars(
                    r"%LocalAppData%\Google\Chrome\Application\chrome.exe"
                ),
            ]
            for path in chrome_paths:
                if os.path.exists(path):
                    return path

        elif system == "Linux":
            # Check common Linux Chrome locations
            chrome_names = [
                "google-chrome",
                "google-chrome-stable",
                "chromium",
                "chromium-browser",
            ]
            for name in chrome_names:
                path = shutil.which(name)
                if path:
                    return path

        return None

    async def _initialize_browser(self) -> None:
        """Initialize browser with persistent context.

        Checks for custom browser types registered via plugins first,
        then falls back to default Playwright Chromium.
        """
        # Load plugin browser types on first initialization
        _load_plugin_browser_types()

        # Check if a custom browser type was requested and is available
        if self.browser_type and self.browser_type in _CUSTOM_BROWSER_TYPES:
            emit_info(
                f"Using custom browser type '{self.browser_type}' "
                f"(session: {self.session_id})"
            )
            init_func = _CUSTOM_BROWSER_TYPES[self.browser_type]
            # Custom init functions should set self._context and self._browser
            await init_func(self)
            self._initialized = True
            return

        # Default: use Playwright Chromium
        from playwright.async_api import async_playwright

        emit_info(f"Using persistent profile: {self.profile_dir}")

        self._playwright = await async_playwright().start()

        # Select the appropriate browser engine
        if self.browser_type == "firefox":
            browser_engine = self._playwright.firefox
        elif self.browser_type == "webkit":
            browser_engine = self._playwright.webkit
        else:
            # Default to chromium
            browser_engine = self._playwright.chromium

        # Build launch options
        launch_options = {
            "user_data_dir": str(self.profile_dir),
            "headless": self.headless,
        }

        # For chromium, try to use the system Chrome browser
        if self.browser_type in ("chromium", "chrome"):
            system_chrome = self._get_system_chrome_path()
            if system_chrome:
                emit_info(f"Using system Chrome: {system_chrome}")
                launch_options["executable_path"] = system_chrome
                # Use channel="chrome" style args for better compatibility
                launch_options["args"] = [
                    "--disable-blink-features=AutomationControlled",
                ]
            else:
                emit_warning("System Chrome not found, using bundled Chromium")

        # Use persistent context directory to preserve browser state
        context = await browser_engine.launch_persistent_context(**launch_options)
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

    async def close_page(self, page: Page) -> None:
        """Close a specific page."""
        await page.close()

    async def get_all_pages(self) -> list[Page]:
        """Get all open pages."""
        if not self._context:
            return []
        return self._context.pages

    async def _cleanup(self, silent: bool = False) -> None:
        """Clean up browser resources and save persistent state.

        Args:
            silent: If True, suppress all errors (used during shutdown).
        """
        try:
            # Save browser state before closing (cookies, localStorage, etc.)
            if self._context:
                try:
                    storage_state_path = self.profile_dir / "storage_state.json"
                    await self._context.storage_state(path=str(storage_state_path))
                    if not silent:
                        emit_success(f"Browser state saved to {storage_state_path}")
                except Exception as e:
                    if not silent:
                        emit_warning(f"Could not save storage state: {e}")

            # Close the browser context (works for both standard Playwright and Camoufox)
            if self._context:
                try:
                    await self._context.close()
                except Exception:
                    pass  # Ignore errors during context close
                self._context = None

            if self._browser:
                try:
                    await self._browser.close()
                except Exception:
                    pass  # Ignore errors during browser close
                self._browser = None

            # Clean up playwright instance if we created one
            if hasattr(self, "_playwright") and self._playwright:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass
                self._playwright = None

            self._initialized = False

            # Remove from active managers
            if self.session_id in _active_managers:
                del _active_managers[self.session_id]

        except Exception as e:
            if not silent:
                emit_warning(f"Warning during cleanup: {e}")

    async def close(self) -> None:
        """Close the browser and clean up resources."""
        await self._cleanup()
        emit_info(f"Browser closed (session: {self.session_id})")


def get_browser_manager(
    session_id: Optional[str] = None, browser_type: Optional[str] = None
) -> BrowserManager:
    """Get or create a BrowserManager instance.

    Args:
        session_id: Optional session ID. If provided and a manager with this
            session exists, returns that manager. Otherwise creates a new one.
            If None, uses 'default' as the session ID.
        browser_type: Optional browser type to use for new managers.
            Ignored if a manager for this session already exists.
            Custom types can be registered via the register_browser_types hook.

    Returns:
        A BrowserManager instance.

    Example:
        # Default session (for single-agent use)
        manager = get_browser_manager()

        # Named session (for multi-agent use)
        manager = get_browser_manager("qa-agent-1")

        # Custom browser type (e.g., stealth browser from plugin)
        manager = get_browser_manager("stealth-session", browser_type="camoufox")
    """
    session_id = session_id or "default"

    if session_id not in _active_managers:
        _active_managers[session_id] = BrowserManager(session_id, browser_type)

    return _active_managers[session_id]


async def cleanup_all_browsers() -> None:
    """Close all active browser manager instances.

    This should be called before application exit to ensure all browser
    connections are properly closed and no dangling futures remain.
    """
    global _cleanup_done

    if _cleanup_done:
        return

    _cleanup_done = True

    # Get a copy of the keys since we'll be modifying the dict during cleanup
    session_ids = list(_active_managers.keys())

    for session_id in session_ids:
        manager = _active_managers.get(session_id)
        if manager and manager._initialized:
            try:
                await manager._cleanup(silent=True)
            except Exception:
                pass  # Silently ignore all errors during exit cleanup


def _sync_cleanup_browsers() -> None:
    """Synchronous cleanup wrapper for use with atexit.

    Creates a new event loop to run the async cleanup since the main
    event loop may have already been closed when atexit handlers run.
    """
    global _cleanup_done

    if _cleanup_done or not _active_managers:
        return

    try:
        # Try to get the running loop first
        try:
            loop = asyncio.get_running_loop()
            # If we're in an async context, schedule the cleanup
            # but this is unlikely in atexit handlers
            loop.create_task(cleanup_all_browsers())
            return
        except RuntimeError:
            pass  # No running loop, which is expected in atexit

        # Create a new event loop for cleanup
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(cleanup_all_browsers())
        finally:
            loop.close()
    except Exception:
        # Silently swallow ALL errors during exit cleanup
        # We don't want to spam the user with errors on exit
        pass


# Register the cleanup handler with atexit
# This ensures browsers are closed even if close_browser() isn't explicitly called
atexit.register(_sync_cleanup_browsers)


# Backwards compatibility aliases
CamoufoxManager = BrowserManager
get_camoufox_manager = get_browser_manager
