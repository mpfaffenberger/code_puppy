"""Camoufox browser plugin for stealth browsing.

This module provides Camoufox browser support via the plugin system.
Camoufox is a stealthy Firefox-based browser that helps avoid bot detection.

Registered as a custom browser type via the register_browser_types hook.
"""

from pathlib import Path
from typing import TYPE_CHECKING

from code_puppy import config
from code_puppy.messaging import emit_info, emit_success

if TYPE_CHECKING:
    from code_puppy.tools.browser.browser_manager import BrowserManager


def _get_camoufox_profile_directory(session_id: str) -> Path:
    """Get or create the Camoufox profile directory.

    Camoufox always uses a fixed profile for consistent fingerprinting,
    regardless of the session ID.

    Args:
        session_id: The session ID (unused for Camoufox, kept for API consistency).

    Returns:
        Path to the Camoufox profile directory.
    """
    cache_dir = Path(config.CACHE_DIR)
    profile_path = cache_dir / "browser_profiles" / "camoufox"
    profile_path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return profile_path


async def _prefetch_camoufox() -> None:
    """Prefetch Camoufox binary and dependencies.

    Ensures the Camoufox browser binary is installed and up-to-date.
    Also downloads the GeoIP database if enabled.
    """
    # Lazy imports to ensure monkey patches are applied BEFORE downloading
    from camoufox.exceptions import CamoufoxNotInstalled, UnsupportedVersion
    from camoufox.locale import ALLOW_GEOIP, download_mmdb
    from camoufox.pkgman import CamoufoxFetcher, camoufox_path

    emit_info(
        "[cyan]🔍 Ensuring Camoufox binary and dependencies are up-to-date...[/cyan]"
    )

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


async def initialize_camoufox(manager: "BrowserManager") -> None:
    """Initialize Camoufox browser on the given BrowserManager instance.

    This function is registered as a custom browser type and called by
    BrowserManager._initialize_browser() when browser_type is "camoufox".

    Camoufox is a stealthy Firefox-based browser that helps avoid
    bot detection. It uses playwright under the hood but with
    special fingerprinting evasion.

    Always uses a fixed profile directory for consistent fingerprinting.

    Args:
        manager: The BrowserManager instance to initialize.
    """
    # Ensure Camoufox binary is installed
    await _prefetch_camoufox()

    # Lazy imports to ensure monkey patches are applied first
    from playwright.async_api import async_playwright
    from camoufox.async_api import AsyncNewBrowser
    from camoufox.addons import DefaultAddons

    emit_info(f"Initializing Camoufox browser (session: {manager.session_id})...")

    # Start playwright instance (required by camoufox 0.4.11+)
    manager._playwright = await async_playwright().start()

    # Get the Camoufox-specific profile (always the same path)
    camoufox_profile = _get_camoufox_profile_directory(manager.session_id)
    emit_info(f"Using Camoufox profile: {camoufox_profile}")

    # Camoufox 0.4.11+ uses a direct async function (not context manager)
    # It returns a BrowserContext when persistent_context=True
    # Note: playwright instance is required as first arg since camoufox 0.4.11
    manager._context = await AsyncNewBrowser(
        manager._playwright,
        headless=manager.headless,
        # Use persistent data directory for state - always the same for Camoufox
        persistent_context=True,
        user_data_dir=str(camoufox_profile),
        # Exclude default addons that might cause issues
        exclude_addons=list(DefaultAddons),
    )
    manager._browser = manager._context.browser
    manager._initialized = True

    emit_success("Camoufox browser initialized successfully")


def get_camoufox_browser_types() -> dict:
    """Return the Camoufox browser type registration.

    This function is registered with the register_browser_types hook
    to make Camoufox available as a custom browser type.

    Returns:
        Dict mapping 'camoufox' to its initialization function.
    """
    return {"camoufox": initialize_camoufox}
