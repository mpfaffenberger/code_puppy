"""Confluence authentication module for Walmart.

This module handles interactive browser-based authentication for Confluence
using Playwright. It launches a Chrome browser, waits for the user to
authenticate, then scrapes session cookies and saves them for API access.
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None

from code_puppy.config import CONFIG_DIR
from code_puppy.messaging import emit_error, emit_info, emit_success


# Constants
CONFLUENCE_URL = "https://confluence.walmart.com/"
CONFLUENCE_COOKIES_FILE = Path(CONFIG_DIR) / "confluence.json"
AUTH_WAIT_TIMEOUT = 300  # 5 minutes
POLL_INTERVAL = 2  # seconds


def _get_code_puppy_chrome_profile_path() -> Path:
    """Get the path to the code-puppy Chrome profile directory.

    Creates a persistent Chrome profile directory inside ~/.code_puppy/
    for storing browser data and cookies across sessions.

    Returns:
        Path: The path to the Chrome profile directory
    """
    profile_path = Path(CONFIG_DIR) / "chrome_profile"
    profile_path.mkdir(parents=True, exist_ok=True)
    return profile_path


async def _scrape_confluence_session_playwright() -> Dict[str, Any]:
    """Scrape Confluence session cookies using Playwright.

    This function:
    1. Launches a Chrome browser with a persistent profile
    2. Navigates to Confluence
    3. Waits for the user to authenticate
    4. Extracts session cookies
    5. Returns the cookies as a dictionary

    Returns:
        Dict[str, Any]: Dictionary containing cookies and metadata

    Raises:
        RuntimeError: If Playwright is not installed
        Exception: If authentication fails or times out
    """
    if async_playwright is None:
        raise RuntimeError(
            "Playwright is not installed. Install it with: "
            "uv pip install playwright && playwright install chromium"
        )

    emit_info("🌐 Launching Chrome browser for Confluence authentication...")

    profile_path = _get_code_puppy_chrome_profile_path()

    async with async_playwright() as p:
        # Launch browser with persistent context and Walmart proxy
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile_path),
            headless=False,
            channel="chrome",  # Use system Chrome if available
            viewport={"width": 1280, "height": 720},
            proxy={"server": "http://sysproxy.wal-mart.com:8080"},
            args=[
                "--disable-blink-features=AutomationControlled",  # Make it less detectable
            ],
        )

        # Get existing page or create new one
        page = context.pages[0] if context.pages else await context.new_page()

        try:
            # Wait for browser to fully initialize before navigating
            emit_info("⏳ Waiting for browser to initialize...")
            await asyncio.sleep(4)

            emit_info(f"📍 Navigating to {CONFLUENCE_URL}...")
            await page.goto(CONFLUENCE_URL, timeout=30000)

            emit_info(
                "⏳ Please authenticate in the browser window.\n"
                "   The browser will wait for you to complete login...\n"
                f"   Timeout: {AUTH_WAIT_TIMEOUT} seconds"
            )

            start_time = time.time()
            authenticated = False

            emit_info("🔍 Waiting for authentication cookies...")

            # Wait for successful authentication by checking for Confluence cookies
            while time.time() - start_time < AUTH_WAIT_TIMEOUT:
                # Get current cookies
                cookies = await context.cookies()

                # Check if we have important Confluence session cookies
                cookie_names = [cookie["name"] for cookie in cookies]
                has_jsessionid = any("JSESSIONID" in name for name in cookie_names)
                has_seraph = any("seraph" in name.lower() for name in cookie_names)

                if has_jsessionid or has_seraph:
                    emit_success("✅ Authentication cookies detected!")
                    authenticated = True
                    break

                # Also check URL as fallback
                current_url = page.url
                if (
                    "confluence.walmart.com" in current_url
                    and "login" not in current_url.lower()
                ):
                    # Wait a bit for cookies to be set
                    await asyncio.sleep(3)
                    cookies = await context.cookies()
                    cookie_names = [cookie["name"] for cookie in cookies]
                    if any(
                        "JSESSIONID" in name or "seraph" in name.lower()
                        for name in cookie_names
                    ):
                        emit_success("✅ Authentication successful!")
                        authenticated = True
                        break

                await asyncio.sleep(POLL_INTERVAL)

            if not authenticated:
                raise TimeoutError(
                    f"Authentication timed out after {AUTH_WAIT_TIMEOUT} seconds. "
                    "Please try again."
                )

            # Get the final URL after authentication
            current_url = page.url

            emit_success("✅ Authentication successful!")
            emit_info("⏳ Waiting 15 seconds for all cookies to be set...")
            await asyncio.sleep(15)  # Wait for page to fully load and set all cookies
            emit_info("🍪 Extracting session cookies...")

            # Get all cookies
            cookies = await context.cookies()

            # Filter for important Confluence cookies
            important_cookies = [
                "JSESSIONID",
                "seraph.confluence",
                "atlassian.xsrf.token",
                "crowd.token_key",
            ]

            cookie_dict = {}
            for cookie in cookies:
                if any(key in cookie["name"] for key in important_cookies):
                    cookie_dict[cookie["name"]] = cookie["value"]

            # Also store all cookies for completeness
            all_cookies = {cookie["name"]: cookie["value"] for cookie in cookies}

            if not cookie_dict:
                emit_info(
                    "⚠️  No specific Confluence cookies found, storing all cookies..."
                )
                cookie_dict = all_cookies

            # Build result with metadata
            result = {
                "cookies": cookie_dict,
                "all_cookies": all_cookies,
                "url": current_url,
                "timestamp": datetime.now().isoformat(),
                "expires": None,  # Could parse from cookie expiry if needed
            }

            emit_success(
                f"✨ Extracted {len(cookie_dict)} important cookies "
                f"({len(all_cookies)} total)"
            )

            return result

        finally:
            emit_info("🔒 Closing browser...")
            await context.close()


def handle_confluence_auth_command(command: str, name: str) -> Optional[str]:
    """Handle the /confluence_auth command.

    This command initiates browser-based authentication for Confluence,
    extracts session cookies, and saves them to ~/.code_puppy/confluence.json
    for use in API calls.

    Args:
        command: The full command string (e.g., "/confluence_auth")
        name: The command name without the slash (e.g., "confluence_auth")

    Returns:
        Optional[str]: Success/error message, or None if not handled
    """
    if name != "confluence_auth":
        return None

    emit_info("🔐 Starting Confluence authentication flow...")

    # Check if Playwright is installed
    if async_playwright is None:
        emit_error(
            "❌ Playwright is not installed.\n"
            "   Install it with:\n"
            "   uv pip install playwright --index-url https://pypi.ci.artifacts.walmart.com/artifactory/api/pypi/external-pypi/simple --allow-insecure-host pypi.ci.artifacts.walmart.com\n"
            "   playwright install chromium"
        )
        return "Playwright is required for Confluence authentication."

    # Run async scraper in a new thread with its own event loop
    # This avoids issues with AnyIO worker threads and nested loops
    import concurrent.futures

    try:

        def run_in_new_loop():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                return new_loop.run_until_complete(
                    _scrape_confluence_session_playwright()
                )
            finally:
                new_loop.close()

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_in_new_loop)
            result = future.result()

        # Save the result to file
        emit_info(f"💾 Saving cookies to {CONFLUENCE_COOKIES_FILE}...")

        with open(CONFLUENCE_COOKIES_FILE, "w") as f:
            json.dump(result, f, indent=2)

        emit_success(
            f"🎉 Confluence authentication complete!\n"
            f"   Cookies saved to: {CONFLUENCE_COOKIES_FILE}\n"
            f"   Timestamp: {result['timestamp']}\n"
            f"   You can now use Confluence API tools."
        )

        return "Confluence authentication successful!"

    except KeyboardInterrupt:
        emit_info("\n🛑 Authentication cancelled by user.")
        return "Authentication cancelled."

    except Exception as e:
        emit_error(f"❌ Authentication failed: {str(e)}")
        return f"Authentication failed: {str(e)}"


def get_confluence_auth_help() -> List[Tuple[str, str]]:
    """Get help information for Confluence authentication.

    Returns:
        List[Tuple[str, str]]: List of (command_name, description) tuples for autocomplete
    """
    return [
        ("confluence_auth", "Authenticate with Confluence using browser"),
    ]
