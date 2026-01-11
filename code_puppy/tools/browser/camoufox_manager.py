"""Camoufox browser manager - privacy-focused Firefox automation.

Supports multiple simultaneous instances with unique profile directories.
"""

import asyncio
import atexit
import contextvars
import os
from pathlib import Path
from typing import Optional

from playwright.async_api import Browser, BrowserContext, Page

from code_puppy import config
from code_puppy.messaging import emit_info, emit_success, emit_warning

# Store active manager instances by session ID
_active_managers: dict[str, "CamoufoxManager"] = {}

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


def get_session_browser_manager() -> "CamoufoxManager":
    """Get the CamoufoxManager for the current context's session.

    This is the preferred way to get a browser manager in tool functions,
    as it automatically uses the correct session ID for the current
    agent context.

    Returns:
        A CamoufoxManager instance for the current session.
    """
    session_id = get_browser_session()
    return get_camoufox_manager(session_id)


# Flag to track if cleanup has already run
_cleanup_done: bool = False


class CamoufoxManager:
    """Browser manager for Camoufox (privacy-focused Firefox) automation.

    Supports multiple simultaneous instances, each with its own profile directory.
    """

    _browser: Optional[Browser] = None
    _context: Optional[BrowserContext] = None
    _initialized: bool = False

    def __init__(self, session_id: Optional[str] = None):
        """Initialize manager settings.

        Args:
            session_id: Optional session ID for this instance.
                If None, uses 'default' as the session ID.
        """
        self.session_id = session_id or "default"

        # Default to headless=True (no browser spam during tests)
        # Override with BROWSER_HEADLESS=false to see the browser
        self.headless = os.getenv("BROWSER_HEADLESS", "true").lower() != "false"
        self.homepage = "https://www.google.com"
        # Browser type: "chromium" skips Camoufox entirely, "firefox"/"camoufox" uses Camoufox
        self.browser_type = "chromium"  # Default to Chromium for reliability
        # Camoufox-specific settings
        self.geoip = True  # Enable GeoIP spoofing
        self.block_webrtc = True  # Block WebRTC for privacy
        self.humanize = True  # Add human-like behavior

        # Unique profile directory per session for browser state
        self.profile_dir = self._get_profile_directory()

    def _get_profile_directory(self) -> Path:
        """Get or create the profile directory for this session.

        Each session gets its own profile directory under:
        XDG_CACHE_HOME/code_puppy/camoufox_profiles/<session_id>/

        This allows multiple instances to run simultaneously.
        """
        cache_dir = Path(config.CACHE_DIR)
        profiles_base = cache_dir / "camoufox_profiles"
        profile_path = profiles_base / self.session_id
        profile_path.mkdir(parents=True, exist_ok=True, mode=0o700)
        return profile_path

    async def async_initialize(self) -> None:
        """Initialize browser (Chromium or Camoufox based on browser_type)."""
        if self._initialized:
            return

        try:
            browser_name = "Chromium" if self.browser_type == "chromium" else "Camoufox"
            emit_info(f"Initializing {browser_name} (session: {self.session_id})...")

            # Only prefetch Camoufox if we're going to use it
            if self.browser_type != "chromium":
                await self._prefetch_camoufox()

            await self._initialize_camoufox()
            # emit_info(
            #     "[green]✅ Browser initialized successfully[/green]"
            # )  # Removed to reduce console spam
            self._initialized = True

        except Exception:
            await self._cleanup()
            raise

    async def _initialize_camoufox(self) -> None:
        """Try to start browser with the configured settings.

        If browser_type is 'chromium', skips Camoufox and uses Playwright Chromium directly.
        Otherwise, tries Camoufox first and falls back to Chromium on failure.
        """
        emit_info(f"Using persistent profile: {self.profile_dir}")

        # If chromium is explicitly requested, skip Camoufox entirely
        if self.browser_type == "chromium":
            await self._initialize_chromium()
            return

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
            emit_warning(
                "Camoufox not available. Falling back to Playwright (Chromium)."
            )
            await self._initialize_chromium()

    async def _initialize_chromium(self) -> None:
        """Initialize Playwright Chromium browser."""
        from playwright.async_api import async_playwright

        emit_info("Initializing Chromium browser...")
        pw = await async_playwright().start()
        # Use persistent context directory for Chromium to preserve browser state
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
        emit_info(f"Camoufox browser closed (session: {self.session_id})")


def get_camoufox_manager(session_id: Optional[str] = None) -> CamoufoxManager:
    """Get or create a CamoufoxManager instance.

    Args:
        session_id: Optional session ID. If provided and a manager with this
            session exists, returns that manager. Otherwise creates a new one.
            If None, uses 'default' as the session ID.

    Returns:
        A CamoufoxManager instance.

    Example:
        # Default session (for single-agent use)
        manager = get_camoufox_manager()

        # Named session (for multi-agent use)
        manager = get_camoufox_manager("qa-agent-1")
    """
    session_id = session_id or "default"

    if session_id not in _active_managers:
        _active_managers[session_id] = CamoufoxManager(session_id)

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
