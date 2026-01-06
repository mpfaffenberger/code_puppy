"""Microsoft Graph authentication module for Code Puppy.

Hijacks Graph Explorer's OAuth flow to authenticate with Microsoft Graph API.
Uses Graph Explorer's client ID and redirect URI, intercepts the OAuth callback,
and exchanges the auth code for an access token.

Commands:
    /msgraph_auth - Opens browser for Microsoft authentication
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
import base64
import concurrent.futures
import hashlib
import json
import secrets
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from code_puppy.config import CONFIG_DIR
from code_puppy.messaging import emit_error, emit_info, emit_success

# Playwright is an optional dependency - gracefully handle import failure
try:
    from playwright.async_api import async_playwright
except ImportError:  # pragma: no cover
    async_playwright = None  # pragma: no cover


# =============================================================================
# CONSTANTS - Graph Explorer's OAuth Configuration (we're hijacking it!)
# =============================================================================

# Graph Explorer's client ID - this is public, registered by Microsoft
GRAPH_EXPLORER_CLIENT_ID: str = "de8bc8b5-d9f9-48b1-a8ad-b748da725064"

# Graph Explorer's redirect URI
GRAPH_EXPLORER_REDIRECT_URI: str = (
    "https://developer.microsoft.com/en-us/graph/graph-explorer"
)

# Azure AD endpoints (using /common for multi-tenant)
AZURE_AD_AUTHORIZE_URL: str = (
    "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
)
AZURE_AD_TOKEN_URL: str = "https://login.microsoftonline.com/common/oauth2/v2.0/token"

# Scopes that Graph Explorer requests
GRAPH_EXPLORER_SCOPES: str = "openid profile User.Read offline_access"

# Microsoft Graph API base URL
MSGRAPH_API_BASE: str = "https://graph.microsoft.com/v1.0"

# Token storage
MSGRAPH_TOKENS_FILE: Path = Path(CONFIG_DIR) / "msgraph.json"

# Timeouts
AUTH_WAIT_TIMEOUT: int = 300  # 5 minutes max wait for user authentication


# =============================================================================
# PKCE HELPERS
# =============================================================================


def _generate_pkce_pair() -> tuple[str, str]:
    """Generate PKCE code verifier and challenge.

    Returns:
        Tuple of (code_verifier, code_challenge).
    """
    # Generate a random code verifier (43-128 characters)
    code_verifier = secrets.token_urlsafe(32)

    # Create SHA256 hash and base64url encode it
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")

    return code_verifier, code_challenge


def _generate_state() -> str:
    """Generate a random state parameter for OAuth."""
    return secrets.token_urlsafe(16)


# =============================================================================
# BROWSER PATH HELPERS
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
# OAUTH FLOW - HIJACKING GRAPH EXPLORER'S CREDENTIALS
# =============================================================================


async def _perform_oauth_flow() -> dict[str, Any]:
    """Perform OAuth flow using Graph Explorer's client ID.

    This hijacks Graph Explorer's OAuth configuration:
    1. Build authorize URL with Graph Explorer's client ID and redirect URI
    2. Open browser to Azure AD login
    3. Intercept the redirect back to Graph Explorer (contains auth code)
    4. Exchange auth code for access token using Graph Explorer's client ID

    Returns:
        Dict with access_token, refresh_token (if available), and timestamp.

    Raises:
        RuntimeError: If Playwright is not installed.
        TimeoutError: If auth not completed within timeout.
    """
    if async_playwright is None:
        raise RuntimeError(
            "Playwright is not installed. Install it with: "
            "uv pip install playwright && playwright install chromium"
        )

    # Generate PKCE pair and state
    code_verifier, code_challenge = _generate_pkce_pair()
    state = _generate_state()

    # Build the authorization URL (mimicking Graph Explorer exactly)
    # Note: We don't set prompt=select_account so it auto-completes if already logged in
    auth_params = {
        "client_id": GRAPH_EXPLORER_CLIENT_ID,
        "scope": GRAPH_EXPLORER_SCOPES,
        "redirect_uri": GRAPH_EXPLORER_REDIRECT_URI,
        "response_mode": "fragment",  # Graph Explorer uses fragment
        "response_type": "code",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    auth_url = f"{AZURE_AD_AUTHORIZE_URL}?{urlencode(auth_params)}"

    emit_info("🌐 Launching browser for Microsoft authentication...")
    profile_path = _get_code_puppy_chrome_profile_path()

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_path),
            headless=False,
            channel="chrome",
            viewport={"width": 1024, "height": 768},
            args=["--disable-blink-features=AutomationControlled"],
        )

        page = context.pages[0] if context.pages else await context.new_page()

        # Variable to capture the auth code from the redirect
        captured_code: str | None = None

        def handle_response(response: Any) -> None:
            """Watch for redirect to Graph Explorer with auth code."""
            nonlocal captured_code
            if captured_code:
                return

            url = response.url
            # Check if this is the redirect back to Graph Explorer
            if url.startswith(GRAPH_EXPLORER_REDIRECT_URI):
                # The auth code is in the URL fragment (after #)
                # But we can't see fragments in response URL...
                # We need to check the page URL instead
                pass

        async def check_for_auth_code() -> str | None:
            """Check if the current page URL contains the auth code."""
            try:
                current_url = page.url
                if GRAPH_EXPLORER_REDIRECT_URI in current_url:
                    # Parse the fragment (everything after #)
                    parsed = urlparse(current_url)
                    # Fragment contains the params
                    if parsed.fragment:
                        fragment_params = parse_qs(parsed.fragment)
                        if "code" in fragment_params:
                            return fragment_params["code"][0]
            except Exception:
                pass
            return None

        try:
            emit_info("📍 Navigating to Microsoft login...")
            await page.goto(auth_url, timeout=30000)

            emit_info(
                "⏳ Waiting for authentication...\n"
                "   (If you're already logged in, this should auto-complete)"
            )

            # Poll for the auth code in the URL - should be fast if already logged in
            start_time = time.time()
            while time.time() - start_time < AUTH_WAIT_TIMEOUT:
                code = await check_for_auth_code()
                if code:
                    captured_code = code
                    elapsed = time.time() - start_time
                    if elapsed < 5:
                        emit_success("✅ Authorization code captured automatically!")
                    else:
                        emit_success("✅ Authorization code captured!")
                    break
                await asyncio.sleep(0.5)

            if not captured_code:
                raise TimeoutError(
                    f"Authentication timed out after {AUTH_WAIT_TIMEOUT} seconds."
                )

            # Exchange the auth code for tokens (must happen in browser context)
            emit_info("🔄 Exchanging authorization code for access token...")
            tokens = await _exchange_code_for_tokens_in_browser(
                page, captured_code, code_verifier
            )

            return tokens

        finally:
            emit_info("🔒 Closing browser...")
            await context.close()


async def _exchange_code_for_tokens_in_browser(
    page: Any,
    auth_code: str,
    code_verifier: str,
) -> dict[str, Any]:
    """Exchange authorization code for access tokens using browser fetch.

    Graph Explorer is a SPA, so Azure AD requires the token exchange to happen
    via a cross-origin request FROM the browser, not from a backend.
    We inject JavaScript to do the fetch from the Graph Explorer origin.

    Args:
        page: Playwright page object (on Graph Explorer domain).
        auth_code: The authorization code from OAuth redirect.
        code_verifier: The PKCE code verifier.

    Returns:
        Dict with access_token, refresh_token (if available), and timestamp.
    """
    # Execute the token exchange from the browser context
    token_response = await page.evaluate(
        """
        async ({tokenUrl, clientId, code, redirectUri, codeVerifier}) => {
            const params = new URLSearchParams();
            params.append('client_id', clientId);
            params.append('code', code);
            params.append('redirect_uri', redirectUri);
            params.append('grant_type', 'authorization_code');
            params.append('code_verifier', codeVerifier);

            try {
                const response = await fetch(tokenUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded',
                    },
                    body: params.toString(),
                });

                const data = await response.json();
                
                if (!response.ok) {
                    return {error: data.error_description || JSON.stringify(data)};
                }
                
                return {
                    access_token: data.access_token,
                    refresh_token: data.refresh_token || null,
                    expires_in: data.expires_in || 3600,
                };
            } catch (e) {
                return {error: e.message};
            }
        }
        """,
        {
            "tokenUrl": AZURE_AD_TOKEN_URL,
            "clientId": GRAPH_EXPLORER_CLIENT_ID,
            "code": auth_code,
            "redirectUri": GRAPH_EXPLORER_REDIRECT_URI,
            "codeVerifier": code_verifier,
        },
    )

    if "error" in token_response:
        raise RuntimeError(f"Token exchange failed: {token_response['error']}")

    return {
        "access_token": token_response["access_token"],
        "refresh_token": token_response.get("refresh_token"),
        "expires_in": token_response.get("expires_in", 3600),
        "timestamp": datetime.now().isoformat(),
    }


# =============================================================================
# TOKEN STORAGE
# =============================================================================


def _save_tokens(tokens: dict[str, Any]) -> None:
    """Save tokens to the tokens file."""
    emit_info(f"💾 Saving tokens to {MSGRAPH_TOKENS_FILE}...")
    MSGRAPH_TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(MSGRAPH_TOKENS_FILE, "w") as f:
        json.dump(tokens, f, indent=2)


def _load_tokens() -> dict[str, Any]:
    """Load tokens from the tokens file."""
    with open(MSGRAPH_TOKENS_FILE) as f:
        return json.load(f)


# =============================================================================
# TOKEN REFRESH
# =============================================================================


def _refresh_access_token(refresh_token: str) -> dict[str, Any] | None:
    """Attempt to refresh the access token using refresh token.

    Args:
        refresh_token: The refresh token.

    Returns:
        New token dict if successful, None if refresh failed.
    """
    try:
        token_data = {
            "client_id": GRAPH_EXPLORER_CLIENT_ID,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                AZURE_AD_TOKEN_URL,
                data=token_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code == 200:
                token_response = response.json()
                return {
                    "access_token": token_response["access_token"],
                    "refresh_token": token_response.get("refresh_token", refresh_token),
                    "expires_in": token_response.get("expires_in", 3600),
                    "timestamp": datetime.now().isoformat(),
                }
    except Exception:
        pass

    return None


# =============================================================================
# COMMAND HANDLERS
# =============================================================================


def handle_msgraph_auth_command(command: str, name: str) -> str | None:
    """Handle the /msgraph_auth slash command."""
    if name != "msgraph_auth":
        return None

    emit_info("🔐 Starting Microsoft Graph authentication flow...")
    emit_info(
        "ℹ️  This uses Graph Explorer's OAuth credentials.\n"
        "   Sign in with your Microsoft account when prompted."
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
        tokens = _run_async_oauth()
        _save_tokens(tokens)

        has_refresh = bool(tokens.get("refresh_token"))
        refresh_msg = (
            "   ✅ Refresh token obtained - token will auto-refresh!\n"
            if has_refresh
            else "   ⚠️  No refresh token - you may need to re-auth when it expires.\n"
        )

        emit_success(
            f"🎉 Microsoft Graph authentication complete!\n"
            f"   Tokens saved to: {MSGRAPH_TOKENS_FILE}\n"
            f"   Timestamp: {tokens['timestamp']}\n"
            f"{refresh_msg}"
            f"   You can now use Microsoft Graph API tools."
        )
        return "Microsoft Graph authentication successful!"

    except KeyboardInterrupt:
        emit_info("\n🛑 Authentication cancelled by user.")
        return "Authentication cancelled."

    except Exception as e:
        emit_error(f"❌ Authentication failed: {e!s}")
        return f"Authentication failed: {e!s}"


def _run_async_oauth() -> dict[str, Any]:
    """Run async OAuth flow in a new thread with its own event loop.

    Always runs in a new thread to avoid issues with AnyIO worker threads
    and nested event loops.
    """
    return _run_oauth_in_thread_with_new_loop()


def _run_oauth_in_thread_with_new_loop() -> dict[str, Any]:
    """Run async OAuth in new thread (used when loop already running)."""

    def run_in_new_loop() -> dict[str, Any]:
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        try:
            return new_loop.run_until_complete(_perform_oauth_flow())
        finally:
            new_loop.close()

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(run_in_new_loop)
        return future.result()


# =============================================================================
# VALIDATION
# =============================================================================


def validate_msgraph_auth(*, debug: bool = False) -> dict[str, Any]:
    """Validate Microsoft Graph authentication by calling /me endpoint."""
    if not MSGRAPH_TOKENS_FILE.exists():
        return {
            "success": False,
            "error": "No Microsoft Graph tokens found. Microsoft Graph authentication required.",
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
            "error": "No access token found. Microsoft Graph authentication required.",
        }

    if debug:
        timestamp = tokens.get("timestamp", "Unknown")
        emit_info(f"🔍 Debug: Token timestamp: {timestamp}")
        emit_info(f"🔍 Debug: Token length: {len(access_token)} chars")
        emit_info(f"🔍 Debug: Has refresh token: {bool(tokens.get('refresh_token'))}")

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
            "error": "Access token expired or invalid. Microsoft Graph re-authentication required.",
        }

    if response.status_code == 403:
        if debug:
            emit_info(f"🔍 Debug: Response body: {response.text[:500]}")
        return {
            "success": False,
            "error": "Insufficient permissions.",
        }

    if debug:
        emit_info(f"🔍 Debug: Response body: {response.text[:500]}")
    return {
        "success": False,
        "error": f"API error: HTTP {response.status_code}",
    }


def handle_msgraph_test_command(command: str, name: str) -> str | None:
    """Handle the /msgraph_test slash command."""
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
        ("msgraph_auth", "Authenticate with Microsoft Graph"),
        ("msgraph_test", "Test Microsoft Graph authentication"),
    ]


# =============================================================================
# UTILITY FUNCTIONS FOR API CLIENTS
# =============================================================================


def get_valid_access_token() -> str | None:
    """Get a valid access token, attempting refresh if needed.

    Returns:
        Access token string, or None if not authenticated.
    """
    if not MSGRAPH_TOKENS_FILE.exists():
        return None

    try:
        tokens = _load_tokens()
    except (json.JSONDecodeError, OSError):
        return None

    access_token = tokens.get("access_token")
    if not access_token:
        return None

    # Try a quick validation
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                f"{MSGRAPH_API_BASE}/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if response.status_code == 200:
                return access_token

            # Token expired, try refresh
            if response.status_code == 401:
                refresh_token = tokens.get("refresh_token")
                if refresh_token:
                    new_tokens = _refresh_access_token(refresh_token)
                    if new_tokens:
                        _save_tokens(new_tokens)
                        return new_tokens["access_token"]
    except Exception:
        pass

    return access_token  # Return it anyway, let caller handle errors
