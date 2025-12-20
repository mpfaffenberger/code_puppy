"""Jira authentication module for Walmart's internal Jira instance.

Provides browser-based SSO authentication using Playwright. Captures session
cookies and persists them to ~/.code_puppy/jira.json for API access.

Commands:
    /jira_auth - Opens browser for SSO authentication
    /jira_test - Validates saved credentials
    /jira_test debug - Validates with verbose output

Note:
    Requires Playwright: ``uv pip install playwright && playwright install chromium``

See Also:
    jira_client.py (planned) - API client for Jira operations using these cookies.
    confluence_client.py - Reference implementation for the client pattern.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from code_puppy.config import CONFIG_DIR
from code_puppy.messaging import emit_error, emit_info, emit_success

# Playwright is an optional dependency - gracefully handle import failure
# pragma: no cover - Import fallback only executes when playwright is not installed,
# which cannot be tested in our test environment where playwright IS installed.
# This is a standard pattern for optional dependencies.
try:
    from playwright.async_api import async_playwright
except ImportError:  # pragma: no cover
    async_playwright = None  # pragma: no cover

# =============================================================================
# CONSTANTS
# =============================================================================

JIRA_URL: str = "https://jira.walmart.com/"
JIRA_COOKIES_FILE: Path = Path(CONFIG_DIR) / "jira.json"
AUTH_WAIT_TIMEOUT: int = 300  # 5 minutes max wait for user authentication
POLL_INTERVAL: int = 2  # Seconds between cookie detection checks

_IMPORTANT_COOKIE_NAMES: list[str] = [
    "JSESSIONID",
    "seraph.jira",
    "atlassian.xsrf.token",
    "crowd.token_key",
]


# =============================================================================
# PRIVATE HELPER FUNCTIONS
# =============================================================================


def _get_code_puppy_chrome_profile_path() -> Path:
    """Get or create the Chrome profile directory for persistent browser state.

    Returns:
        Path to ~/.code_puppy/chrome_profile (created if needed).
    """
    profile_path = Path(CONFIG_DIR) / "chrome_profile"
    profile_path.mkdir(parents=True, exist_ok=True)
    return profile_path


def _has_auth_cookies(cookie_names: list[str]) -> bool:
    """Check if any authentication-related cookies are present.

    Args:
        cookie_names: List of cookie names to check.

    Returns:
        True if any Jira authentication cookies are detected.
    """
    return any(
        "JSESSIONID" in name or "seraph" in name.lower() or "atlassian" in name.lower()
        for name in cookie_names
    )


def _extract_cookies(
    cookies: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, str]]:
    """Extract important and all cookies from Playwright cookie list.

    Args:
        cookies: List of cookie dictionaries from Playwright.

    Returns:
        Tuple of (important_cookies, all_cookies) where:
            - important_cookies: Only cookies matching known Jira auth patterns
            - all_cookies: All cookies (used as fallback)
    """
    important: dict[str, str] = {}
    all_cookies: dict[str, str] = {}

    for cookie in cookies:
        name = cookie["name"]
        value = cookie["value"]
        all_cookies[name] = value

        if any(key in name for key in _IMPORTANT_COOKIE_NAMES):
            important[name] = value

    return important, all_cookies


# =============================================================================
# BROWSER-BASED AUTHENTICATION
# =============================================================================


async def _scrape_jira_session_playwright() -> dict[str, Any]:
    """Launch browser and capture Jira session cookies after user authenticates.

    Opens Chrome, navigates to Jira, waits for user to complete SSO login,
    then extracts session cookies.

    Returns:
        Dict with cookies, all_cookies, url, base_url, timestamp, expires.

    Raises:
        RuntimeError: If Playwright is not installed.
        TimeoutError: If auth not completed within AUTH_WAIT_TIMEOUT seconds.
    """
    if async_playwright is None:
        raise RuntimeError(
            "Playwright is not installed. Install it with: "
            "uv pip install playwright && playwright install chromium"
        )

    emit_info("🌐 Launching Chrome browser for Jira authentication...")
    profile_path = _get_code_puppy_chrome_profile_path()

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_path),
            headless=False,
            channel="chrome",
            viewport={"width": 1280, "height": 720},
            proxy={"server": "http://sysproxy.wal-mart.com:8080"},
            args=["--disable-blink-features=AutomationControlled"],
        )

        page = context.pages[0] if context.pages else await context.new_page()

        try:
            emit_info("⏳ Waiting for browser to initialize...")
            await asyncio.sleep(4)

            emit_info(f"📍 Navigating to {JIRA_URL}...")
            await page.goto(JIRA_URL, timeout=30000)

            emit_info(
                "⏳ Please authenticate in the browser window.\n"
                "   The browser will wait for you to complete login...\n"
                f"   Timeout: {AUTH_WAIT_TIMEOUT} seconds"
            )

            authenticated = await _wait_for_authentication(context, page)

            if not authenticated:
                # pragma: no cover - TimeoutError is raised after AUTH_WAIT_TIMEOUT
                # seconds of real wall-clock time. Testing this would require either
                # waiting 5+ minutes or complex time mocking that breaks async.
                raise TimeoutError(
                    f"Authentication timed out after {AUTH_WAIT_TIMEOUT} seconds. "
                    "Please try again."
                )

            return await _finalize_authentication(context, page)

        finally:
            emit_info("🔒 Closing browser...")
            await context.close()


async def _wait_for_authentication(context: Any, page: Any) -> bool:
    """Poll for authentication cookies until detected or timeout.

    Args:
        context: Playwright browser context.
        page: Playwright page object.

    Returns:
        True if authentication cookies were detected, False if timed out.
    """
    start_time = time.time()
    emit_info("🔍 Waiting for authentication cookies...")

    while time.time() - start_time < AUTH_WAIT_TIMEOUT:
        cookies = await context.cookies()
        cookie_names = [cookie["name"] for cookie in cookies]

        if _has_auth_cookies(cookie_names):
            emit_success("✅ Authentication cookies detected!")
            return True

        # URL-based fallback: check if we're on Jira (not login page)
        current_url = page.url
        if "jira.walmart.com" in current_url and "login" not in current_url.lower():
            await asyncio.sleep(3)  # Wait for cookies to be set
            cookies = await context.cookies()
            cookie_names = [cookie["name"] for cookie in cookies]

            if _has_auth_cookies(cookie_names):
                emit_success("✅ Authentication successful!")
                return True

        await asyncio.sleep(POLL_INTERVAL)

    return False


async def _finalize_authentication(context: Any, page: Any) -> dict[str, Any]:
    """Extract cookies and build result after successful authentication.

    Args:
        context: Playwright browser context.
        page: Playwright page object.

    Returns:
        Dictionary containing cookies and metadata.
    """
    current_url = page.url

    emit_success("✅ Authentication successful!")
    emit_info("⏳ Waiting 15 seconds for all cookies to be set...")
    await asyncio.sleep(15)
    emit_info("🍪 Extracting session cookies...")

    cookies = await context.cookies()
    important_cookies, all_cookies = _extract_cookies(cookies)

    # Fallback to all cookies if no important ones found
    if not important_cookies:
        emit_info("⚠️  No specific Jira cookies found, storing all cookies...")
        important_cookies = all_cookies

    result: dict[str, Any] = {
        "cookies": important_cookies,
        "all_cookies": all_cookies,
        "url": current_url,
        "base_url": JIRA_URL.rstrip("/"),
        "timestamp": datetime.now().isoformat(),
        "expires": None,
    }

    emit_success(
        f"✨ Extracted {len(important_cookies)} important cookies "
        f"({len(all_cookies)} total)"
    )

    return result


# =============================================================================
# COMMAND HANDLERS
# =============================================================================


def handle_jira_auth_command(command: str, name: str) -> str | None:
    """Handle the /jira_auth slash command.

    Args:
        command: Full command string (e.g., "/jira_auth").
        name: Command name without slash (e.g., "jira_auth").

    Returns:
        Success/error message if handled, None if not our command.
    """
    if name != "jira_auth":
        return None

    emit_info("🔐 Starting Jira authentication flow...")

    if async_playwright is None:
        emit_error(
            "❌ Playwright is not installed.\n"
            "   Install it with:\n"
            "   uv pip install playwright --index-url "
            "https://pypi.ci.artifacts.walmart.com/artifactory/api/pypi/external-pypi/simple "
            "--allow-insecure-host pypi.ci.artifacts.walmart.com\n"
            "   playwright install chromium"
        )
        return "Playwright is required for Jira authentication."

    try:
        result = _run_async_scraper()
        _save_session(result)

        emit_success(
            f"🎉 Jira authentication complete!\n"
            f"   Cookies saved to: {JIRA_COOKIES_FILE}\n"
            f"   Timestamp: {result['timestamp']}\n"
            f"   You can now use Jira API tools."
        )
        return "Jira authentication successful!"

    except Exception as e:
        emit_error(f"❌ Authentication failed: {e!s}")
        return f"Authentication failed: {e!s}"


def _run_async_scraper() -> dict[str, Any]:
    """Run async scraper, handling both sync and async calling contexts.

    Returns:
        Result dictionary from _scrape_jira_session_playwright.
    """
    # Always run in a new thread with a fresh event loop to avoid
    # issues with AnyIO worker threads and nested event loops
    return _run_in_thread_with_new_loop()


def _run_in_thread_with_new_loop() -> dict[str, Any]:  # pragma: no cover
    """Run async scraper in new thread (used when loop already running)."""

    def run_in_new_loop() -> dict[str, Any]:
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        try:
            return new_loop.run_until_complete(_scrape_jira_session_playwright())
        finally:
            new_loop.close()

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(run_in_new_loop)
        return future.result()


def _save_session(result: dict[str, Any]) -> None:
    """Save session data to the cookies file.

    Args:
        result: Session data dictionary to persist.
    """
    emit_info(f"💾 Saving cookies to {JIRA_COOKIES_FILE}...")
    with open(JIRA_COOKIES_FILE, "w") as f:
        json.dump(result, f, indent=2)


# =============================================================================
# VALIDATION
# =============================================================================


def validate_jira_auth(*, debug: bool = False) -> dict[str, Any]:
    """Validate Jira authentication by calling /rest/api/2/myself.

    Args:
        debug: If True, emit verbose request/response information.

    Returns:
        Dict with success, user, display_name, email (if success=True),
        or success=False with error message.
    """
    if not JIRA_COOKIES_FILE.exists():
        return {
            "success": False,
            "error": "No Jira session found. Run /jira_auth first.",
        }

    try:
        session_data = _load_session()
    except (json.JSONDecodeError, OSError) as e:
        return {
            "success": False,
            "error": f"Failed to load session file: {e}",
        }

    cookies = session_data.get("all_cookies", session_data.get("cookies", {}))
    base_url = session_data.get("base_url", "https://jira.walmart.com")

    if debug:
        emit_info(f"🔍 Debug: Using {len(cookies)} cookies")
        emit_info(f"🔍 Debug: Cookie names: {list(cookies.keys())}")
        emit_info(f"🔍 Debug: Base URL: {base_url}")

    return _make_validation_request(base_url, cookies, debug=debug)


def _load_session() -> dict[str, Any]:
    """Load session data from cookies file. Raises on invalid JSON or IO error."""
    with open(JIRA_COOKIES_FILE) as f:
        return json.load(f)


def _make_validation_request(
    base_url: str,
    cookies: dict[str, str],
    *,
    debug: bool = False,
) -> dict[str, Any]:
    """Make HTTP request to validate Jira session."""
    try:
        with httpx.Client(
            cookies=cookies,
            timeout=30.0,
            verify=False,  # Walmart internal certs
            headers={
                "User-Agent": "Code-Puppy/1.0",
                "Accept": "application/json",
            },
        ) as client:
            url = f"{base_url}/rest/api/2/myself"

            if debug:
                emit_info(f"🔍 Debug: Requesting {url}")

            response = client.get(url)

            if debug:
                emit_info(f"🔍 Debug: Response status: {response.status_code}")
                emit_info(f"🔍 Debug: Response headers: {dict(response.headers)}")

            return _parse_validation_response(response, debug=debug)

    except Exception as e:
        return {
            "success": False,
            "error": f"Connection error: {e}",
        }


def _parse_validation_response(
    response: httpx.Response,
    *,
    debug: bool = False,
) -> dict[str, Any]:
    """Parse validation API response into result dict."""
    if response.status_code == 200:
        user_data = response.json()
        return {
            "success": True,
            "user": user_data.get("name", "unknown"),
            "display_name": user_data.get("displayName", "Unknown User"),
            "email": user_data.get("emailAddress", ""),
        }

    if response.status_code in (401, 403):
        if debug:
            emit_info(f"🔍 Debug: Response body: {response.text[:500]}")
        return {
            "success": False,
            "error": (
                f"Session expired or forbidden (HTTP {response.status_code}). "
                "Run /jira_auth to re-authenticate."
            ),
        }

    # Other HTTP errors (500, 502, etc.)
    if debug:
        emit_info(f"🔍 Debug: Response body: {response.text[:500]}")
    return {
        "success": False,
        "error": f"API error: HTTP {response.status_code}",
    }


def handle_jira_test_command(command: str, name: str) -> str | None:
    """Handle the /jira_test slash command. Add 'debug' for verbose output.

    Args:
        command: Full command string (e.g., "/jira_test debug").
        name: Command name without slash.

    Returns:
        Success/error message if handled, None if not our command.
    """
    if name != "jira_test":
        return None

    debug = "debug" in command.lower()
    emit_info("🔍 Testing Jira authentication...")

    result = validate_jira_auth(debug=debug)

    if result["success"]:
        emit_success(
            f"✅ Jira authentication valid!\n"
            f"   User: {result['user']}\n"
            f"   Name: {result['display_name']}\n"
            f"   Email: {result.get('email', 'N/A')}"
        )
        return f"Authenticated as {result['display_name']} ({result['user']})"

    emit_error(f"❌ {result['error']}")
    return result["error"]


# =============================================================================
# HELP / AUTOCOMPLETE
# =============================================================================


def get_jira_auth_help() -> list[tuple[str, str]]:
    """Return (command_name, description) tuples for autocomplete/help."""
    return [
        ("jira_auth", "Authenticate with Jira using browser"),
        ("jira_test", "Test Jira authentication (add 'debug' for verbose output)"),
    ]
