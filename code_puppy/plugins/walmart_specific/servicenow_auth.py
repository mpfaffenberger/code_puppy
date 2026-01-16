"""ServiceNow authentication module for Walmart.

This module handles interactive browser-based authentication for ServiceNow
using Playwright. It launches a Chrome browser, waits for the user to
authenticate, then scrapes session cookies and saves them for API access.
"""

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None

from code_puppy.config import CONFIG_DIR
from code_puppy.messaging import emit_error, emit_info, emit_success


# Constants
SERVICENOW_URL = "https://walmartglobal.service-now.com/"
SERVICENOW_COOKIES_FILE = Path(CONFIG_DIR) / "servicenow.json"
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


async def _scrape_servicenow_session_playwright() -> Dict[str, Any]:
    """Scrape ServiceNow session cookies using Playwright.

    This function:
    1. Launches a Chrome browser with a persistent profile
    2. Navigates to ServiceNow
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

    emit_info("🌐 Launching Chrome browser for ServiceNow authentication...")

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
                "--disable-blink-features=AutomationControlled",
            ],
        )

        # Get existing page or create new one
        page = context.pages[0] if context.pages else await context.new_page()

        try:
            # Wait for browser to fully initialize before navigating
            emit_info("⏳ Waiting for browser to initialize...")
            await asyncio.sleep(4)

            emit_info(f"📍 Navigating to {SERVICENOW_URL}...")
            await page.goto(SERVICENOW_URL, timeout=30000)

            emit_info(
                "⏳ Please authenticate in the browser window.\n"
                "   The browser will wait for you to complete login...\n"
                f"   Timeout: {AUTH_WAIT_TIMEOUT} seconds"
            )

            start_time = time.time()
            authenticated = False

            emit_info("🔍 Waiting for authentication cookies...")

            # Wait for successful authentication by checking for ServiceNow cookies
            # IMPORTANT: We must wait until we're back on service-now.com, not on the SSO page
            while time.time() - start_time < AUTH_WAIT_TIMEOUT:
                current_url = page.url
                
                # Only check cookies if we're actually on the ServiceNow domain
                # (not on PingFederate SSO or other auth pages)
                if (
                    "service-now.com" in current_url
                    and "login" not in current_url.lower()
                    and "saml" not in current_url.lower()
                    and "pfedprod" not in current_url.lower()
                    and "idp" not in current_url.lower()
                ):
                    # We're on ServiceNow - now check for cookies
                    cookies = await context.cookies()
                    cookie_names = [cookie["name"] for cookie in cookies]
                    
                    has_glide_session = any(
                        "glide_session" in name.lower() for name in cookie_names
                    )
                    has_jsessionid = any("JSESSIONID" in name for name in cookie_names)
                    has_glide_user = any(
                        "glide_user" in name.lower() for name in cookie_names
                    )

                    if has_glide_session or has_jsessionid or has_glide_user:
                        # Wait a bit more for all cookies to be fully set
                        await asyncio.sleep(3)
                        emit_success("✅ Authentication cookies detected!")
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
            await asyncio.sleep(15)
            emit_info("🍪 Extracting session cookies...")

            # Get all cookies
            cookies = await context.cookies()

            # Filter for important ServiceNow cookies
            important_cookies = [
                "glide_session_store",
                "glide_user",
                "glide_user_route",
                "JSESSIONID",
                "BIGipServer",
                "glide_node",
            ]

            cookie_dict = {}
            for cookie in cookies:
                if any(key in cookie["name"] for key in important_cookies):
                    cookie_dict[cookie["name"]] = cookie["value"]

            # Also store all cookies for completeness
            all_cookies = {cookie["name"]: cookie["value"] for cookie in cookies}
            
            # Try to extract the g_ck token (CSRF token needed for API calls)
            # This is typically available as a JavaScript variable on the page
            g_ck_token = None
            try:
                g_ck_token = await page.evaluate("() => window.g_ck || window.NOW?.g_ck || ''")
                if g_ck_token:
                    emit_info(f"🔑 Captured g_ck token for API authentication")
                    all_cookies["g_ck"] = g_ck_token
            except Exception:
                emit_info("⚠️  Could not extract g_ck token (may not be needed)")

            if not cookie_dict:
                emit_info(
                    "⚠️  No specific ServiceNow cookies found, storing all cookies..."
                )
                cookie_dict = all_cookies

            # Build result with metadata
            result = {
                "cookies": cookie_dict,
                "all_cookies": all_cookies,
                "url": current_url,
                "timestamp": datetime.now().isoformat(),
                "expires": None,
            }

            emit_success(
                f"✨ Extracted {len(cookie_dict)} important cookies "
                f"({len(all_cookies)} total)"
            )

            return result

        finally:
            emit_info("🔒 Closing browser...")
            await context.close()


def handle_servicenow_auth_command(command: str, name: str) -> Optional[str]:
    """Handle the /servicenow_auth command.

    This command initiates browser-based authentication for ServiceNow,
    extracts session cookies, and saves them to ~/.code_puppy/servicenow.json
    for use in API calls.

    Args:
        command: The full command string (e.g., "/servicenow_auth")
        name: The command name without the slash (e.g., "servicenow_auth")

    Returns:
        Optional[str]: Success/error message, or None if not handled
    """
    if name != "servicenow_auth":
        return None

    emit_info("🔐 Starting ServiceNow authentication flow...")

    # Check if Playwright is installed
    if async_playwright is None:
        emit_error(
            "❌ Playwright is not installed.\n"
            "   Install it with:\n"
            "   uv pip install playwright --index-url https://pypi.ci.artifacts.walmart.com/artifactory/api/pypi/external-pypi/simple --allow-insecure-host pypi.ci.artifacts.walmart.com\n"
            "   playwright install chromium"
        )
        return "Playwright is required for ServiceNow authentication."

    # Run async scraper in a new thread with its own event loop
    import concurrent.futures

    try:

        def run_in_new_loop():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                return new_loop.run_until_complete(
                    _scrape_servicenow_session_playwright()
                )
            finally:
                new_loop.close()

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_in_new_loop)
            result = future.result()

        # Save the result to file
        emit_info(f"💾 Saving cookies to {SERVICENOW_COOKIES_FILE}...")

        with open(SERVICENOW_COOKIES_FILE, "w") as f:
            json.dump(result, f, indent=2)

        emit_success(
            f"🎉 ServiceNow authentication complete!\n"
            f"   Cookies saved to: {SERVICENOW_COOKIES_FILE}\n"
            f"   Timestamp: {result['timestamp']}\n"
            f"   You can now use ServiceNow API tools."
        )

        return "ServiceNow authentication successful!"

    except KeyboardInterrupt:
        emit_info("\n🛑 Authentication cancelled by user.")
        return "Authentication cancelled."

    except Exception as e:
        emit_error(f"❌ Authentication failed: {str(e)}")
        return f"Authentication failed: {str(e)}"


def get_servicenow_auth_help() -> List[Tuple[str, str]]:
    """Get help information for ServiceNow authentication.

    Returns:
        List[Tuple[str, str]]: List of (command_name, description) tuples
    """
    return [
        ("servicenow_auth", "Authenticate with ServiceNow using browser"),
    ]
