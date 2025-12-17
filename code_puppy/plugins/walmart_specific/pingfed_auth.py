"""PingFed authentication token scraper.

This module provides browser automation to fetch PingFed tokens from the
ping-token-util service and save them to the local config.
"""

import json
import time
from pathlib import Path
from typing import Optional, Tuple

from rich.text import Text

from code_puppy.config import CONFIG_DIR
from code_puppy.messaging import emit_error, emit_info, emit_success


def _get_code_puppy_chrome_profile_path() -> str:
    """Get the code-puppy dedicated Chrome profile path.

    This creates a dedicated Chrome profile just for code-puppy automation,
    separate from the user's main Chrome profile to avoid conflicts.

    Returns:
        Path to ~/.code_puppy/profiles/chrome
    """
    profile_path = Path(CONFIG_DIR) / "profiles" / "chrome"
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

    return True


def get_pingfed_auth_help() -> list:
    """Return help information for the pingfed_auth command."""
    return [("pingfed_auth", "Fetch and save PingFed tokens from ping-token-util")]
