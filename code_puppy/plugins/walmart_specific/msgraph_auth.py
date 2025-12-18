"""Microsoft Graph authentication module for Code Puppy.

Provides browser-based token capture authentication for Microsoft Graph API.
Uses Playwright to open Graph Explorer, waits for user to sign in and trigger
an API call, then captures the access token from the Authorization header of
requests to graph.microsoft.com. Tokens are persisted to ~/.code_puppy/msgraph.json.

Commands:
    /msgraph_auth - Opens browser for Graph Explorer authentication
    /msgraph_test - Validates saved tokens by calling /me endpoint
    /msgraph_test debug - Validates with verbose output

Note:
    Requires Playwright: ``uv pip install playwright && playwright install chromium``

See Also:
    https://developer.microsoft.com/en-us/graph/graph-explorer
    https://docs.microsoft.com/en-us/graph/overview
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
try:
    from playwright.async_api import async_playwright
except ImportError:  # pragma: no cover
    async_playwright = None  # pragma: no cover


# =============================================================================
# CONSTANTS
# =============================================================================

# Graph Explorer URL - user signs in here and we scrape the token
GRAPH_EXPLORER_URL: str = "https://developer.microsoft.com/en-us/graph/graph-explorer"

# Microsoft Graph API base URL
MSGRAPH_API_BASE: str = "https://graph.microsoft.com/v1.0"

# Token storage
MSGRAPH_TOKENS_FILE: Path = Path(CONFIG_DIR) / "msgraph.json"

# Timeouts
AUTH_WAIT_TIMEOUT: int = 300  # 5 minutes max wait for user authentication
POLL_INTERVAL: int = 2  # Seconds between token detection checks


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


# =============================================================================
# BROWSER-BASED TOKEN SCRAPING
# =============================================================================


async def _scrape_graph_explorer_token() -> dict[str, Any]:
    """Launch browser and capture MS Graph access token after user authenticates.

    Opens Chrome, navigates to Graph Explorer, waits for user to sign in
    and trigger an API call, then captures the access token from the
    Authorization header of requests to graph.microsoft.com.

    Returns:
        Dict with access_token and timestamp.

    Raises:
        RuntimeError: If Playwright is not installed or no token found.
        TimeoutError: If auth not completed within AUTH_WAIT_TIMEOUT seconds.
    """
    if async_playwright is None:
        raise RuntimeError(
            "Playwright is not installed. Install it with: "
            "uv pip install playwright && playwright install chromium"
        )

    emit_info("🌐 Launching Chrome browser for Graph Explorer authentication...")
    profile_path = _get_code_puppy_chrome_profile_path()

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_path),
            headless=False,
            channel="chrome",
            viewport={"width": 1280, "height": 720},
            args=["--disable-blink-features=AutomationControlled"],
        )

        page = context.pages[0] if context.pages else await context.new_page()

        # Variable to capture the token from request headers
        captured_token: str | None = None

        def handle_request(request: Any) -> None:
            nonlocal captured_token
            if captured_token:
                return  # Already got one
            auth_header = request.headers.get("authorization", "")
            if (
                auth_header.startswith("Bearer ")
                and "graph.microsoft.com" in request.url
            ):
                captured_token = auth_header[7:]  # Remove 'Bearer ' prefix

        page.on("request", handle_request)

        try:
            emit_info("⏳ Waiting for browser to initialize...")
            await asyncio.sleep(2)

            emit_info(f"📍 Navigating to {GRAPH_EXPLORER_URL}...")
            await page.goto(GRAPH_EXPLORER_URL, timeout=30000)

            # Wait for page to load
            await asyncio.sleep(3)

            # Try to auto-click the sign-in button to make it easier for users
            sign_in_clicked = False
            try:
                # Graph Explorer has a "Sign in" button - try multiple selectors
                sign_in_selectors = [
                    "button:has-text('Sign in')",
                    "[data-testid='sign-in-button']",
                    ".sign-in-button",
                    "button.ms-Button:has-text('Sign in')",
                    "#signin-button",
                ]
                for selector in sign_in_selectors:
                    try:
                        sign_in_btn = page.locator(selector).first
                        if await sign_in_btn.is_visible(timeout=2000):
                            emit_info("🔑 Found sign-in button, clicking...")
                            await sign_in_btn.click()
                            sign_in_clicked = True
                            await asyncio.sleep(2)
                            break
                    except Exception:
                        continue

                if not sign_in_clicked:
                    emit_info(
                        "ℹ️  Could not auto-click sign-in button.\n"
                        "   Please click 'Sign in' in the top-right corner."
                    )
            except Exception as e:
                emit_info(f"ℹ️  Auto sign-in click skipped: {e!s}")

            emit_info(
                "⏳ Please sign in with your Microsoft account in the browser.\n"
                "   After signing in, click 'Run query' to trigger an API call...\n"
                f"   Timeout: {AUTH_WAIT_TIMEOUT} seconds"
            )

            # Wait for token to be captured from a request
            start_time = time.time()
            while time.time() - start_time < AUTH_WAIT_TIMEOUT:
                if captured_token:
                    emit_success("✅ Access token captured from API request!")
                    break
                await asyncio.sleep(POLL_INTERVAL)

            if not captured_token:
                raise TimeoutError(
                    f"Authentication timed out after {AUTH_WAIT_TIMEOUT} seconds. "
                    "Please try again."
                )

            result: dict[str, Any] = {
                "access_token": captured_token,
                "timestamp": datetime.now().isoformat(),
            }

            emit_success("✨ Access token extracted successfully!")
            return result

        finally:
            emit_info("🔒 Closing browser...")
            await context.close()


# =============================================================================
# TOKEN STORAGE
# =============================================================================


def _save_tokens(tokens: dict[str, Any]) -> None:
    """Save tokens to the tokens file.

    Args:
        tokens: Token data dictionary to persist.
    """
    emit_info(f"💾 Saving tokens to {MSGRAPH_TOKENS_FILE}...")

    # Ensure config directory exists
    MSGRAPH_TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(MSGRAPH_TOKENS_FILE, "w") as f:
        json.dump(tokens, f, indent=2)


def _load_tokens() -> dict[str, Any]:
    """Load tokens from the tokens file.

    Returns:
        Token data dictionary.

    Raises:
        FileNotFoundError: If tokens file doesn't exist.
        json.JSONDecodeError: If tokens file is invalid JSON.
    """
    with open(MSGRAPH_TOKENS_FILE) as f:
        return json.load(f)


# =============================================================================
# COMMAND HANDLERS
# =============================================================================


def handle_msgraph_auth_command(command: str, name: str) -> str | None:
    """Handle the /msgraph_auth slash command.

    Args:
        command: Full command string (e.g., "/msgraph_auth").
        name: Command name without slash (e.g., "msgraph_auth").

    Returns:
        Success/error message if handled, None if not our command.
    """
    if name != "msgraph_auth":
        return None

    emit_info("🔐 Starting Microsoft Graph authentication flow...")
    emit_info(
        "ℹ️  This will open Graph Explorer. Sign in with your Microsoft account,\n"
        "   and Code Puppy will capture the access token automatically."
    )

    if async_playwright is None:
        emit_error(
            "❌ Playwright is not installed.\n"
            "   Install it with:\n"
            "   uv pip install playwright --index-url "
            "https://pypi.ci.artifacts.walmart.com/artifactory/api/pypi/external-pypi/simple "
            "--allow-insecure-host pypi.ci.artifacts.walmart.com\n"
            "   playwright install chromium"
        )
        return "Playwright is required for Microsoft Graph authentication."

    try:
        tokens = _run_async_scraper()
        _save_tokens(tokens)

        emit_success(
            f"🎉 Microsoft Graph authentication complete!\n"
            f"   Tokens saved to: {MSGRAPH_TOKENS_FILE}\n"
            f"   Timestamp: {tokens['timestamp']}\n"
            f"   You can now use Microsoft Graph API tools.\n\n"
            f"   ⚠️  Note: Graph Explorer tokens expire after ~1 hour.\n"
            f"   Run /msgraph_auth again when they expire."
        )
        return "Microsoft Graph authentication successful!"

    except Exception as e:
        emit_error(f"❌ Authentication failed: {e!s}")
        return f"Authentication failed: {e!s}"


def _run_async_scraper() -> dict[str, Any]:
    """Run async scraper, handling both sync and async calling contexts.

    Returns:
        Result dictionary from _scrape_graph_explorer_token.
    """
    loop = asyncio.get_event_loop()

    if loop.is_running():
        # pragma: no cover - This branch executes when called from within
        # an already-running async event loop
        return _run_scraper_in_thread_with_new_loop()  # pragma: no cover

    return loop.run_until_complete(_scrape_graph_explorer_token())


def _run_scraper_in_thread_with_new_loop() -> dict[str, Any]:  # pragma: no cover
    """Run async scraper in new thread (used when loop already running)."""

    def run_in_new_loop() -> dict[str, Any]:
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        try:
            return new_loop.run_until_complete(_scrape_graph_explorer_token())
        finally:
            new_loop.close()

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(run_in_new_loop)
        return future.result()


# =============================================================================
# VALIDATION
# =============================================================================


def validate_msgraph_auth(*, debug: bool = False) -> dict[str, Any]:
    """Validate Microsoft Graph authentication by calling /me endpoint.

    Args:
        debug: If True, emit verbose request/response information.

    Returns:
        Dict with success, user info (if success=True),
        or success=False with error message.
    """
    if not MSGRAPH_TOKENS_FILE.exists():
        return {
            "success": False,
            "error": "No Microsoft Graph tokens found. Run /msgraph_auth first.",
        }

    try:
        tokens = _load_tokens()
    except (json.JSONDecodeError, OSError) as e:
        return {
            "success": False,
            "error": f"Failed to load tokens file: {e}",
        }

    access_token = tokens.get("access_token")
    if not access_token:
        return {
            "success": False,
            "error": "No access token found. Run /msgraph_auth to authenticate.",
        }

    if debug:
        timestamp = tokens.get("timestamp", "Unknown")
        emit_info(f"🔍 Debug: Token timestamp: {timestamp}")
        emit_info(f"🔍 Debug: Token length: {len(access_token)} chars")

    return _make_validation_request(access_token, debug=debug)


def _make_validation_request(
    access_token: str,
    *,
    debug: bool = False,
) -> dict[str, Any]:
    """Make HTTP request to validate Microsoft Graph access."""
    try:
        with httpx.Client(
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {access_token}",
                "User-Agent": "Code-Puppy/1.0",
                "Accept": "application/json",
            },
        ) as client:
            url = f"{MSGRAPH_API_BASE}/me"

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
            "id": user_data.get("id", ""),
            "display_name": user_data.get("displayName", "Unknown User"),
            "email": user_data.get("mail") or user_data.get("userPrincipalName", ""),
            "job_title": user_data.get("jobTitle", ""),
        }

    if response.status_code == 401:
        if debug:
            emit_info(f"🔍 Debug: Response body: {response.text[:500]}")
        return {
            "success": False,
            "error": "Access token expired or invalid. Run /msgraph_auth to re-authenticate.",
        }

    if response.status_code == 403:
        if debug:
            emit_info(f"🔍 Debug: Response body: {response.text[:500]}")
        return {
            "success": False,
            "error": "Insufficient permissions. The Graph Explorer token may not have the required scopes.",
        }

    # Other HTTP errors
    if debug:
        emit_info(f"🔍 Debug: Response body: {response.text[:500]}")
    return {
        "success": False,
        "error": f"API error: HTTP {response.status_code}",
    }


def handle_msgraph_test_command(command: str, name: str) -> str | None:
    """Handle the /msgraph_test slash command. Add 'debug' for verbose output.

    Args:
        command: Full command string (e.g., "/msgraph_test debug").
        name: Command name without slash.

    Returns:
        Success/error message if handled, None if not our command.
    """
    if name != "msgraph_test":
        return None

    debug = "debug" in command.lower()
    emit_info("🔍 Testing Microsoft Graph authentication...")

    result = validate_msgraph_auth(debug=debug)

    if result["success"]:
        emit_success(
            f"✅ Microsoft Graph authentication valid!\n"
            f"   Name: {result['display_name']}\n"
            f"   Email: {result.get('email', 'N/A')}\n"
            f"   Job Title: {result.get('job_title', 'N/A')}"
        )
        return (
            f"Authenticated as {result['display_name']} ({result.get('email', 'N/A')})"
        )

    emit_error(f"❌ {result['error']}")
    return result["error"]


# =============================================================================
# HELP / AUTOCOMPLETE
# =============================================================================


def get_msgraph_auth_help() -> list[tuple[str, str]]:
    """Return (command_name, description) tuples for autocomplete/help."""
    return [
        ("msgraph_auth", "Authenticate with Microsoft Graph via Graph Explorer"),
        (
            "msgraph_test",
            "Test Microsoft Graph authentication (add 'debug' for verbose output)",
        ),
    ]


# =============================================================================
# UTILITY FUNCTIONS FOR API CLIENTS
# =============================================================================


def get_valid_access_token() -> str | None:
    """Get a valid access token from stored tokens.

    This is a convenience function for other modules that need to make
    Microsoft Graph API calls. Note that Graph Explorer tokens expire
    after ~1 hour - if the token is expired, returns None and user
    must run /msgraph_auth again.

    Returns:
        Access token string, or None if not authenticated or token missing.
    """
    if not MSGRAPH_TOKENS_FILE.exists():
        return None

    try:
        tokens = _load_tokens()
    except (json.JSONDecodeError, OSError):
        return None

    return tokens.get("access_token")


def run_auth_flow_if_needed(*, force: bool = False) -> bool:
    """Run the auth flow automatically if tokens are missing or invalid.

    This function can be called by the msgraph client when it detects
    authentication is needed, providing a smoother UX than requiring
    users to manually run /msgraph_auth.

    Args:
        force: If True, run auth even if tokens exist.

    Returns:
        True if authentication succeeded, False otherwise.
    """
    # Check if we already have valid tokens
    if not force:
        token = get_valid_access_token()
        if token:
            # Validate the token is still working
            result = validate_msgraph_auth()
            if result.get("success"):
                return True

    emit_info("\n🔐 Microsoft Graph authentication required...")
    emit_info("🚀 Launching browser for Graph Explorer authentication...")

    if async_playwright is None:
        emit_error(
            "❌ Playwright is not installed.\n"
            "   Install it with:\n"
            "   uv pip install playwright --index-url "
            "https://pypi.ci.artifacts.walmart.com/artifactory/api/pypi/external-pypi/simple "
            "--allow-insecure-host pypi.ci.artifacts.walmart.com\n"
            "   playwright install chromium"
        )
        return False

    try:
        tokens = _run_async_scraper()
        _save_tokens(tokens)

        emit_success(
            f"🎉 Microsoft Graph authentication complete!\n"
            f"   Tokens saved to: {MSGRAPH_TOKENS_FILE}\n"
            f"   Timestamp: {tokens['timestamp']}"
        )
        return True

    except Exception as e:
        emit_error(f"❌ Auto-authentication failed: {e!s}")
        return False
