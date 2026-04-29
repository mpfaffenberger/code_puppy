"""Marketplace authentication commands and browser automation.

This module handles authentication for the Puppy Agent Marketplace and keeps
backward-compatible aliases for older command names.
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Optional

from rich.text import Text

from code_puppy.config import CONFIG_DIR
from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning


def _get_code_puppy_chrome_profile_path() -> str:
    """Get the code-puppy dedicated Chrome profile path.

    This creates a dedicated Chrome profile just for code-puppy automation,
    separate from the user's main Chrome profile to avoid conflicts.
    Uses the same path as other auth modules for session consistency.

    Returns:
        Path to ~/.code_puppy/chrome_profile
    """
    profile_path = Path(CONFIG_DIR) / "chrome_profile"
    profile_path.mkdir(parents=True, exist_ok=True)
    return str(profile_path)


def handle_pingfed_auth_command(command: str, name: str) -> Optional[bool]:
    """Backward-compatible alias for /marketplace_auth.

    /pingfed_auth is no longer advertised as its own command. Keep it working as
    an alias so existing muscle memory and old docs do not explode.
    """
    if name != "pingfed_auth":
        return None

    emit_info("🔁 /pingfed_auth is deprecated. Redirecting to /marketplace_auth...")
    return handle_puppy_auth_command("/marketplace_auth", "marketplace_auth")


def get_pingfed_auth_help() -> list:
    """Return help information for the deprecated pingfed_auth command."""
    return []


# =============================================================================
# Puppy Site Authentication (for Marketplace)
# =============================================================================


def _get_puppy_base_url() -> str:
    """Get the puppy site base URL based on the CODEPUPPY_LOCAL_AGENT_MARKETPLACE env var.

    - "1" -> dev   (https://puppy.dev.walmart.com)
    - "2" -> stage (https://puppy.stg.walmart.com)
    - anything else (or unset) -> prod (https://puppy.walmart.com)
    """
    env = os.environ.get("CODEPUPPY_LOCAL_AGENT_MARKETPLACE")
    return {
        "1": "https://puppy.dev.walmart.com",
        "2": "https://puppy.stg.walmart.com",
    }.get(env, "https://puppy.walmart.com")


async def _fetch_puppy_token_playwright() -> Optional[dict]:
    """Use Playwright to authenticate via the puppy site and fetch token.

    Flow:
    1. Open browser to puppy site
    2. User authenticates via PingFed SSO (or uses existing session)
    3. Hit /api/auth/fetch-my-token endpoint to get the token
    4. Return token data

    Returns:
        dict with accessToken, user info, etc. or None if failed
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        emit_error(
            "Playwright not installed. Install with: uv pip install playwright && playwright install chromium"
        )
        return None

    base_url = _get_puppy_base_url()
    profile_path = _get_code_puppy_chrome_profile_path()

    emit_info(
        Text.from_markup(
            f"🐶 Launching browser for Puppy authentication...\n"
            f"   [dim]URL: {base_url}[/dim]\n"
            f"   [dim]Profile: {profile_path}[/dim]"
        )
    )

    try:
        async with async_playwright() as p:
            # Launch with persistent context using our dedicated profile
            # Use system Chrome for better compatibility and no need to install browsers
            context = await p.chromium.launch_persistent_context(
                user_data_dir=profile_path,
                headless=False,
                channel="chrome",  # Use system Chrome
                ignore_https_errors=True,  # For local dev with self-signed certs
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",  # Help with cookie sharing
                    "--disable-site-isolation-trials",
                ],
                bypass_csp=True,  # Accept all cookies including third-party
            )
            page = context.pages[0] if context.pages else await context.new_page()
            emit_success("✅ Browser launched! Please sign in if prompted.")

            # Navigate to the token endpoint - OAuth will redirect to signin if needed
            token_url = f"{base_url}/api/auth/fetch-my-token"
            emit_info(f"🔑 Navigating to {token_url}")
            emit_info("   (OAuth will redirect to signin if needed)")

            await page.goto(token_url, wait_until="networkidle", timeout=30000)

            # Check if we were redirected to auth pages - wait for user to complete
            max_wait = 120  # 2 minutes for user to authenticate
            start_time = time.time()
            retry_count = 0
            max_retries = 3

            while time.time() - start_time < max_wait:
                current_url = page.url

                # If we're on signin or pingfed pages, user needs to authenticate
                if (
                    "signin" in current_url
                    or "pingfed" in current_url.lower()
                    or "pfed" in current_url.lower()
                ):
                    emit_info("⏳ Waiting for authentication to complete...")
                    await page.wait_for_timeout(2000)  # Check every 2 seconds
                    retry_count = 0  # Reset retry count when at auth page
                    continue

                # If we got redirected to a weird URL (favicon, root, etc), go back to token endpoint
                if (
                    base_url in current_url
                    and "fetch-my-token" not in current_url
                    and "signin" not in current_url
                    and "pingfed" not in current_url.lower()
                ):
                    # Check if it's a bad redirect (favicon, root page, etc)
                    if (
                        "favicon" in current_url
                        or current_url.rstrip("/") == base_url.rstrip("/")
                        or ".ico" in current_url
                        or ".png" in current_url
                    ):
                        emit_info("🔄 Redirecting back to token endpoint...")
                        await page.goto(
                            token_url, wait_until="networkidle", timeout=15000
                        )
                        await page.wait_for_timeout(1000)
                        continue

                # If we're back at the token endpoint or redirected elsewhere on puppy site
                if base_url in current_url:
                    # Wait for page to settle before getting content
                    try:
                        await page.wait_for_load_state("networkidle", timeout=5000)
                    except Exception:
                        pass  # Page might still be navigating

                    # Try to get the page content safely
                    try:
                        content = await page.content()
                    except Exception as e:
                        emit_info(f"⏳ Page still loading... ({e.__class__.__name__})")
                        await page.wait_for_timeout(2000)
                        continue

                    # Check if we got the token response
                    if '"success":true' in content and '"accessToken"' in content:
                        emit_success("✅ Authentication successful!")
                        break
                    elif '"success":false' in content:
                        retry_count += 1
                        if retry_count >= max_retries:
                            emit_error(
                                "❌ Token fetch failed after retries. You may need to sign in again."
                            )
                            # Try redirecting to signin page with callback to token endpoint
                            from urllib.parse import quote

                            callback = quote(token_url, safe="")
                            signin_url = (
                                f"{base_url}/api/auth/signin?callbackUrl={callback}"
                            )
                            emit_info("🔑 Redirecting to sign-in...")
                            await page.goto(
                                signin_url, wait_until="networkidle", timeout=15000
                            )
                            retry_count = 0
                            continue
                        emit_info(
                            f"🔄 Re-fetching token (attempt {retry_count}/{max_retries})..."
                        )
                        await page.goto(
                            token_url, wait_until="networkidle", timeout=15000
                        )
                        await page.wait_for_timeout(2000)
                        continue

                await page.wait_for_timeout(1000)

            # Check if we timed out
            if time.time() - start_time >= max_wait:
                emit_error("❌ Authentication timed out. Please try again.")
                await context.close()
                return None

            # Make sure we're at the token endpoint and get the response
            current_url = page.url
            if token_url not in current_url:
                emit_info("🔑 Navigating to token endpoint...")
                await page.goto(token_url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(1000)  # Let page settle

            # Parse the JSON response
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
                content = await page.content()
                # Extract JSON from the page (it might be wrapped in HTML)
                json_match = re.search(r"\{.*\}", content, re.DOTALL)
                if json_match:
                    token_data = json.loads(json_match.group())
                else:
                    emit_error("❌ Could not find JSON in response")
                    await context.close()
                    return None
            except json.JSONDecodeError as e:
                emit_error(f"❌ Failed to parse token response: {e}")
                await context.close()
                return None

            if not token_data.get("success"):
                error_msg = token_data.get("error", "Unknown error")
                emit_error(f"❌ Token fetch failed: {error_msg}")
                await context.close()
                return None

            emit_success("✅ Token fetched successfully! Closing browser...")
            # Small delay to ensure cookies are flushed to disk
            await page.wait_for_timeout(500)
            await context.close()
            return token_data.get("data")

    except Exception as e:
        emit_error(f"🐞 Browser automation failed: {e}")
        import traceback

        emit_error(Text.from_markup(f"[dim]{traceback.format_exc()}[/dim]"))
        return None


def handle_puppy_auth_command(command: str, name: str) -> Optional[bool]:
    """Handle marketplace authentication commands.

    Opens a browser, authenticates via the puppy site,
    and saves the token for marketplace API calls.

    Supported commands:
    - /marketplace_auth (preferred)
    - /puppy_auth (backward-compatible alias)

    Args:
        command: The full command string
        name: The command name (without slash)

    Returns:
        True if handled, None if not this command
    """
    if name not in {"marketplace_auth", "puppy_auth"}:
        return None

    if name == "puppy_auth":
        emit_info("🔁 /puppy_auth is deprecated. Redirecting to /marketplace_auth...")

    emit_info("🐶 Starting Agent Marketplace authentication flow...")
    emit_info("   This will authenticate you for the Agent Marketplace.")

    import asyncio
    import concurrent.futures

    def run_in_new_loop():
        """Run the async function in a fresh event loop in this thread."""
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        try:
            return new_loop.run_until_complete(_fetch_puppy_token_playwright())
        finally:
            new_loop.close()

    try:
        # Always run in a thread pool to avoid event loop conflicts
        # This handles both "no event loop" and "event loop already running" cases
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_in_new_loop)
            result = future.result(timeout=180)  # 3 minute timeout for auth
    except concurrent.futures.TimeoutError:
        emit_error("Authentication timed out after 3 minutes.")
        return True
    except Exception as e:
        emit_error(f"Failed to run browser automation: {e}")
        import traceback

        emit_error(Text.from_markup(f"[dim]{traceback.format_exc()}[/dim]"))
        return True

    if not result:
        emit_error(
            "Failed to fetch Puppy token. Please check the browser window and try again."
        )
        return True

    # Save token to config (use different key than puppy_token which is for backend)
    from code_puppy.config import set_config_value

    # Handle both formats: result might be {accessToken, user} or {data: {accessToken, user}}
    if "data" in result:
        data = result.get("data", {})
    else:
        data = result

    access_token = data.get("accessToken")
    user_info = data.get("user") or {}

    # Helper to get a field value, filtering out "NOT_FOUND" placeholder
    def get_valid(field: str) -> str:
        val = user_info.get(field)
        return val if val and val != "NOT_FOUND" else ""

    # PingFed puts email in various fields - try them all
    user_email = (
        get_valid("email")
        or get_valid("mail")
        or get_valid("preferredUsername")
        or get_valid("preferred_username")
        or get_valid("id")
        or get_valid("sub")
        or "Unknown"
    )

    if access_token:
        set_config_value("marketplace_token", access_token)
        emit_success(
            f"✅ Marketplace token saved to config!\n"
            f"🔑 Token: {access_token[:30]}...\n"
            f"👤 User: {user_email}"
        )
    else:
        emit_warning("⚠️ No access token in response - you may need to re-authenticate")

    # Also save the full token data for reference
    config_dir = Path(CONFIG_DIR)
    config_dir.mkdir(parents=True, exist_ok=True)

    marketplace_token_file = config_dir / "marketplace_token.json"
    try:
        # Save the data portion (with accessToken and user info)
        with open(marketplace_token_file, "w") as f:
            json.dump(data, f, indent=2)
        emit_info(f"📄 Full token data saved to {marketplace_token_file}")
    except Exception as e:
        emit_warning(f"Could not save token file: {e}")

    emit_success("\n🎉 You're now authenticated for the Agent Marketplace!")
    emit_info("   Try: /search-agents or /upload-agent")

    return True


def get_marketplace_auth_help() -> list:
    """Return help information for the marketplace_auth command."""
    return [
        (
            "marketplace_auth",
            "Authenticate with the Puppy site for Agent Marketplace access",
        )
    ]


def get_puppy_auth_help() -> list:
    """Backward-compatible alias for marketplace auth help.

    Intentionally returns no extra help entry so /help only shows the canonical
    /marketplace_auth command.
    """
    return []
