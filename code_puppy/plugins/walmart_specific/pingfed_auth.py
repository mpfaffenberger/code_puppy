"""PingFed authentication token scraper.

This module provides browser automation to fetch PingFed tokens from the
ping-token-util service and save them to the local config.
It also updates any MCP servers that use PINGFED_TOKEN env vars.
"""

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import List, Optional, Tuple

from rich.text import Text

from code_puppy.config import CONFIG_DIR, MCP_SERVERS_FILE
from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

# Configure logging
logger = logging.getLogger(__name__)


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


async def _scrape_pingfed_tokens_playwright() -> Optional[Tuple[str, str]]:
    """Use Playwright to scrape tokens from the ping-token-util page.

    Returns:
        Tuple of (pingfed_token, refresh_token) or None if failed
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        emit_error(
            "Playwright not installed. Install with: uv pip install playwright && playwright install chromium"
        )
        return None

    # Use a dedicated Chrome profile for code-puppy (avoids conflicts with main Chrome)
    profile_path = _get_code_puppy_chrome_profile_path()
    emit_info(
        Text.from_markup(
            f"🌐 Launching browser with code-puppy profile...\n"
            f"   [dim]Profile: {profile_path}[/dim]"
        )
    )

    try:
        async with async_playwright() as p:
            # Launch with persistent context using our dedicated profile
            context = await p.chromium.launch_persistent_context(
                user_data_dir=profile_path,
                headless=False,
                channel="chrome",  # Use installed Chrome
                args=[
                    "--disable-blink-features=AutomationControlled",  # Make it less detectable
                ],
            )
            page = context.pages[0] if context.pages else await context.new_page()
            emit_success(
                "✅ Browser launched! (First time? You may need to log in. After that, you'll stay logged in.)"
            )

            # Navigate to the token util page
            url = "http://ping-token-util.squiggly.walmart.com/account"
            emit_info(f"🔗 Navigating to {url}")
            await page.goto(url, wait_until="networkidle", timeout=30000)

            # Give the page a moment to fully render
            emit_info("⏳ Waiting for page to load...")
            time.sleep(2)

            # Scrape tokens from textarea elements
            # The ping-token-util page has two textareas:
            # - First textarea = PingFed token
            # - Second textarea = Refresh token
            pingfed_token = None
            refresh_token = None

            try:
                emit_info("🔍 Searching for tokens on page...")

                # Get all textarea elements
                textareas = await page.query_selector_all("textarea")

                if len(textareas) < 2:
                    emit_error(
                        f"❌ Expected 2 textareas but found {len(textareas)}. "
                        "Page structure may have changed."
                    )
                else:
                    # First textarea = PingFed token
                    # Use input_value() for textarea elements (not inner_text)
                    pingfed_token = (await textareas[0].input_value()).strip()
                    emit_success(f"✅ Found PingFed token: {pingfed_token[:30]}...")

                    # Second textarea = Refresh token
                    refresh_token = (await textareas[1].input_value()).strip()
                    emit_success(f"✅ Found refresh token: {refresh_token[:20]}...")

            except Exception as e:
                emit_error(f"Error extracting tokens: {e}")
                import traceback

                emit_error(Text.from_markup(f"[dim]{traceback.format_exc()}[/dim]"))

            # If we couldn't find the tokens, provide helpful debugging info
            if not pingfed_token or not refresh_token:
                screenshot_path = Path(CONFIG_DIR) / "pingfed_page.png"
                await page.screenshot(path=str(screenshot_path))

                missing = []
                if not pingfed_token:
                    missing.append("PingFed token (first textarea)")
                if not refresh_token:
                    missing.append("Refresh token (second textarea)")

                emit_error(
                    f"❌ Could not locate: {', '.join(missing)}\n\n"
                    f"📸 Screenshot saved to: {screenshot_path}\n"
                    f"👀 Please check if you're logged in or if the page structure changed.\n\n"
                    f"Keeping browser open for 30 seconds for inspection..."
                )
                time.sleep(30)

                await context.close()
                return None

            # Success! Close the browser and return tokens
            emit_success("✅ Tokens extracted successfully! Closing browser...")
            await context.close()
            return (pingfed_token, refresh_token)

    except Exception as e:
        emit_error(f"🐞 Browser automation failed: {e}")
        import traceback

        emit_error(Text.from_markup(f"[dim]{traceback.format_exc()}[/dim]"))
        return None


def handle_pingfed_auth_command(command: str, name: str) -> Optional[bool]:
    """Handle the /pingfed_auth command.

    Opens a browser, navigates to ping-token-util, scrapes tokens,
    and saves them to ~/.code_puppy/pingfed.json

    Args:
        command: The full command string
        name: The command name (without slash)

    Returns:
        True if handled, None if not this command
    """
    if name != "pingfed_auth":
        return None

    emit_info("🔐 Starting PingFed authentication flow...")

    # Scrape tokens from the web page (run async function in event loop)
    import asyncio

    try:
        # Check if we're already in an event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're in an async context, create a task
            import concurrent.futures

            # Run in a new thread with its own event loop
            def run_in_new_loop():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(
                        _scrape_pingfed_tokens_playwright()
                    )
                finally:
                    new_loop.close()

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_in_new_loop)
                result = future.result()
        else:
            # No running loop, safe to use run_until_complete
            result = loop.run_until_complete(_scrape_pingfed_tokens_playwright())
    except Exception as e:
        emit_error(f"Failed to run async browser automation: {e}")
        import traceback

        emit_error(Text.from_markup(f"[dim]{traceback.format_exc()}[/dim]"))
        return True

    if not result:
        emit_error(
            "Failed to scrape PingFed tokens. Please check the browser window and try again."
        )
        return True

    pingfed_token, refresh_token = result

    # Save tokens to ~/.code_puppy/pingfed.json
    config_dir = Path(CONFIG_DIR)
    config_dir.mkdir(parents=True, exist_ok=True)

    pingfed_file = config_dir / "pingfed.json"
    token_data = {"pingfed_token": pingfed_token, "refresh_token": refresh_token}

    try:
        with open(pingfed_file, "w") as f:
            json.dump(token_data, f, indent=2)
        emit_success(
            f"✅ PingFed tokens saved to {pingfed_file}\n"
            f"🔑 pingfed_token: {pingfed_token[:20]}...\n"
            f"🔄 refresh_token: {refresh_token[:20]}..."
        )
    except Exception as e:
        emit_error(f"Failed to save tokens: {e}")
        return True

    # Update MCP servers that have PINGFED_TOKEN env vars
    emit_info("\n🔍 Scanning MCP servers for PINGFED_TOKEN env vars...")
    updated_servers = _update_mcp_servers_with_token(pingfed_token)

    if updated_servers:
        emit_success(
            f"📝 Updated PINGFED_TOKEN in {len(updated_servers)} MCP server(s): "
            f"{', '.join(updated_servers)}"
        )

        # Restart the affected servers
        emit_info("\n🔄 Restarting affected MCP servers...")
        _restart_mcp_servers(updated_servers)
    else:
        emit_info(
            Text.from_markup(
                "[dim]No MCP servers found with PINGFED_TOKEN env var[/dim]"
            )
        )

    return True


def _update_mcp_servers_with_token(token: str) -> List[str]:
    """Update any MCP servers that have PINGFED_TOKEN env vars.

    Scans the mcp_servers.json file for servers with PINGFED_TOKEN in their
    env configuration and updates them with the new token value.

    Args:
        token: The new PingFed token value

    Returns:
        List of server names that were updated
    """
    updated_servers: List[str] = []

    try:
        if not os.path.exists(MCP_SERVERS_FILE):
            logger.debug("No MCP servers file found, skipping token update")
            return updated_servers

        with open(MCP_SERVERS_FILE, "r") as f:
            content = f.read().strip()
            if not content:
                return updated_servers
            config = json.loads(content)

        # Handle both formats: {"mcp_servers": {...}} and legacy {...}
        if "mcp_servers" in config:
            servers = config["mcp_servers"]
        else:
            servers = config

        if not isinstance(servers, dict):
            return updated_servers

        # Scan for servers with PINGFED_TOKEN env var
        modified = False
        for server_name, server_config in servers.items():
            if not isinstance(server_config, dict):
                continue

            env = server_config.get("env", {})
            if not isinstance(env, dict):
                continue

            # Check for PINGFED_TOKEN (case-sensitive)
            if "PINGFED_TOKEN" in env:
                old_value = env["PINGFED_TOKEN"]
                env["PINGFED_TOKEN"] = token
                server_config["env"] = env
                updated_servers.append(server_name)
                modified = True
                logger.info(
                    f"Updated PINGFED_TOKEN for server '{server_name}' "
                    f"(was: {old_value[:20] if old_value else 'empty'}...)"
                )

        # Save if modified
        if modified:
            # Preserve format
            if "mcp_servers" in config:
                config["mcp_servers"] = servers
            else:
                config = servers

            with open(MCP_SERVERS_FILE, "w") as f:
                json.dump(
                    config if "mcp_servers" not in config else {"mcp_servers": servers},
                    f,
                    indent=2,
                )
            logger.info(
                f"Saved updated MCP server configs for {len(updated_servers)} servers"
            )

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse MCP servers JSON: {e}")
    except Exception as e:
        logger.error(f"Failed to update MCP servers with token: {e}")

    return updated_servers


def _restart_mcp_servers(server_names: List[str]) -> None:
    """Restart the specified MCP servers.

    This reloads the configuration and restarts the servers so they
    pick up the new PINGFED_TOKEN value.

    Args:
        server_names: List of server names to restart
    """
    if not server_names:
        return

    try:
        from code_puppy.mcp_.manager import get_mcp_manager

        manager = get_mcp_manager()

        for server_name in server_names:
            try:
                # Find server by name
                server_config = manager.get_server_by_name(server_name)
                if not server_config:
                    emit_warning(
                        f"Could not find MCP server '{server_name}' to restart"
                    )
                    continue

                server_id = server_config.id

                # Stop the server
                emit_info(f"🔄 Stopping MCP server: {server_name}")
                manager.stop_server_sync(server_id)

                # Reload from config to pick up new env vars
                emit_info(f"📥 Reloading configuration for: {server_name}")
                manager.sync_from_config()
                manager.reload_server(server_id)

                # Start the server again
                emit_info(f"🚀 Starting MCP server: {server_name}")
                manager.start_server_sync(server_id)

                emit_success(f"✅ Restarted MCP server: {server_name}")

            except Exception as e:
                emit_error(f"Failed to restart server '{server_name}': {e}")
                logger.error(f"Error restarting server '{server_name}': {e}")

        # Reload the agent to pick up the server changes
        try:
            from code_puppy.agents import get_current_agent

            agent = get_current_agent()
            agent.reload_code_generation_agent()
            agent.update_mcp_tool_cache_sync()
            emit_info(
                Text.from_markup("[dim]Agent reloaded with updated MCP servers[/dim]")
            )
        except Exception as e:
            logger.warning(f"Could not reload agent: {e}")

    except Exception as e:
        emit_error(f"Failed to restart MCP servers: {e}")
        logger.error(f"Failed to restart MCP servers: {e}")


def get_pingfed_auth_help() -> list:
    """Return help information for the pingfed_auth command."""
    return [
        (
            "pingfed_auth",
            "Fetch PingFed tokens and update MCP servers with PINGFED_TOKEN env vars",
        )
    ]


# =============================================================================
# Puppy Site Authentication (for Marketplace)
# =============================================================================


def _get_puppy_base_url() -> str:
    """Get the puppy site base URL based on environment."""
    if os.environ.get("CODEPUPPY_LOCAL_AGENT_MARKETPLACE") == "1":
        return "https://puppy-dev.walmart.com"
    return "https://puppy.walmart.com"


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
    """Handle the /puppy_auth command.

    Opens a browser, authenticates via the puppy site,
    and saves the token for marketplace API calls.

    Args:
        command: The full command string
        name: The command name (without slash)

    Returns:
        True if handled, None if not this command
    """
    if name != "puppy_auth":
        return None

    emit_info("🐶 Starting Puppy site authentication flow...")
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


def get_puppy_auth_help() -> list:
    """Return help information for the puppy_auth command."""
    return [
        (
            "puppy_auth",
            "Authenticate with the Puppy site for Agent Marketplace access",
        )
    ]
