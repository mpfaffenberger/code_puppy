"""Antigravity OAuth Plugin callbacks for Code Puppy CLI."""

from __future__ import annotations

import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from code_puppy.callbacks import register_callback
from code_puppy.config import set_model_name
from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

from ..oauth_puppy_html import oauth_failure_html, oauth_success_html
from .accounts import AccountManager
from .config import (
    ANTIGRAVITY_OAUTH_CONFIG,
    get_accounts_storage_path,
    get_token_storage_path,
)
from .constants import ANTIGRAVITY_MODELS
from .oauth import (
    TokenExchangeSuccess,
    assign_redirect_uri,
    build_authorization_url,
    exchange_code_for_tokens,
    fetch_antigravity_status,
    prepare_oauth_context,
)
from .storage import clear_accounts
from .utils import (
    add_models_to_config,
    load_antigravity_models,
    load_stored_tokens,
    reload_current_agent,
    remove_antigravity_models,
    save_tokens,
)

logger = logging.getLogger(__name__)


class _OAuthResult:
    def __init__(self) -> None:
        self.code: Optional[str] = None
        self.state: Optional[str] = None
        self.error: Optional[str] = None


class _CallbackHandler(BaseHTTPRequestHandler):
    result: _OAuthResult
    received_event: threading.Event
    redirect_uri: str

    def do_GET(self) -> None:  # noqa: N802
        logger.info("Callback received: path=%s", self.path)
        parsed = urlparse(self.path)
        params: Dict[str, List[str]] = parse_qs(parsed.query)

        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]

        if code and state:
            self.result.code = code
            self.result.state = state
            success_html = oauth_success_html(
                "Antigravity",
                "You're connected to Antigravity! 🚀 Gemini & Claude models are now available.",
            )
            self._write_response(200, success_html)
        else:
            self.result.error = "Missing code or state"
            failure_html = oauth_failure_html(
                "Antigravity",
                "Missing code or state parameter 🥺",
            )
            self._write_response(400, failure_html)

        self.received_event.set()

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    def _write_response(self, status: int, body: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))


def _start_callback_server(
    context: Any,
) -> Optional[Tuple[HTTPServer, _OAuthResult, threading.Event, str]]:
    """Start local HTTP server for OAuth callback."""
    port_range = ANTIGRAVITY_OAUTH_CONFIG["callback_port_range"]

    for port in range(port_range[0], port_range[1] + 1):
        try:
            server = HTTPServer(("localhost", port), _CallbackHandler)
            redirect_uri = assign_redirect_uri(context, port)
            result = _OAuthResult()
            event = threading.Event()
            _CallbackHandler.result = result
            _CallbackHandler.received_event = event
            _CallbackHandler.redirect_uri = redirect_uri

            def run_server() -> None:
                with server:
                    server.serve_forever()

            threading.Thread(target=run_server, daemon=True).start()
            return server, result, event, redirect_uri
        except OSError:
            continue

    emit_error("Could not start OAuth callback server; all candidate ports are in use")
    return None


def _await_callback(context: Any) -> Optional[Tuple[str, str, str]]:
    """Wait for OAuth callback and return (code, state, redirect_uri)."""
    timeout = ANTIGRAVITY_OAUTH_CONFIG["callback_timeout"]

    started = _start_callback_server(context)
    if not started:
        return None

    server, result, event, redirect_uri = started

    auth_url = build_authorization_url(context)

    try:
        import webbrowser

        from code_puppy.tools.common import should_suppress_browser

        if should_suppress_browser():
            emit_info(
                "[HEADLESS MODE] Would normally open browser for Antigravity OAuth…"
            )
            emit_info(f"In normal mode, would visit: {auth_url}")
        else:
            emit_info("🌐 Opening browser for Google OAuth…")
            webbrowser.open(auth_url)
            emit_info(f"If it doesn't open automatically, visit:\n{auth_url}")
    except Exception as exc:
        emit_warning(f"Failed to open browser: {exc}")
        emit_info(f"Please open manually: {auth_url}")

    emit_info(f"⏳ Waiting for callback on {redirect_uri}")

    if not event.wait(timeout=timeout):
        emit_error("OAuth callback timed out. Please try again.")
        server.shutdown()
        return None

    server.shutdown()

    if result.error:
        emit_error(f"OAuth callback error: {result.error}")
        return None

    return result.code, result.state, redirect_uri


def _perform_authentication(add_account: bool = False) -> bool:
    """Run the OAuth authentication flow."""
    context = prepare_oauth_context()
    callback_result = _await_callback(context)

    if not callback_result:
        return False

    code, state, redirect_uri = callback_result

    emit_info("🔄 Exchanging authorization code for tokens…")
    result = exchange_code_for_tokens(code, state, redirect_uri)

    if not isinstance(result, TokenExchangeSuccess):
        emit_error(f"Token exchange failed: {result.error}")
        return False

    # Save tokens
    tokens = {
        "access_token": result.access_token,
        "refresh_token": result.refresh_token,
        "expires_at": result.expires_at,
        "email": result.email,
        "project_id": result.project_id,
    }

    if not save_tokens(tokens):
        emit_error("Failed to save tokens locally. Check file permissions.")
        return False

    # Handle multi-account
    manager = AccountManager.load_from_disk(result.refresh_token)

    if add_account or manager.account_count == 0:
        manager.add_account(
            refresh_token=result.refresh_token,
            email=result.email,
            project_id=result.project_id,
        )
        manager.save_to_disk()

        if add_account:
            emit_success(f"✅ Added account: {result.email or 'Unknown'}")
            emit_info(f"📊 Total accounts: {manager.account_count}")

    if result.email:
        emit_success(f"🎉 Authenticated as {result.email}!")
    else:
        emit_success("🎉 Antigravity OAuth authentication successful!")

    # Add models
    emit_info("📦 Configuring available models…")
    if add_models_to_config(result.access_token, result.project_id):
        model_count = len(ANTIGRAVITY_MODELS)
        emit_success(f"✅ {model_count} Antigravity models configured!")
        emit_info(
            "   Use the `antigravity-` prefix (e.g., antigravity-gemini-3-pro-high)"
        )
    else:
        emit_warning("Failed to configure models. Try running /antigravity-auth again.")

    # Reload agent
    reload_current_agent()
    return True


def _custom_help() -> List[Tuple[str, str]]:
    """Return help entries for Antigravity commands."""
    return [
        (
            "antigravity-auth",
            "Authenticate with Google/Antigravity for Gemini & Claude models",
        ),
        (
            "antigravity-add",
            "Add another Google account for load balancing",
        ),
        (
            "antigravity-status",
            "Check authentication status and account pool",
        ),
        (
            "antigravity-logout",
            "Remove all Antigravity OAuth tokens and models",
        ),
    ]


def _handle_status() -> None:
    """Handle /antigravity-status command."""
    tokens = load_stored_tokens()

    if not tokens or not tokens.get("access_token"):
        emit_warning("🔓 Antigravity: Not authenticated")
        emit_info("Run /antigravity-auth to sign in with Google")
        return

    emit_success("🔐 Antigravity: Authenticated")

    # Show email if available
    if tokens.get("email"):
        emit_info(f"   Primary account: {tokens['email']}")

    # Show token expiry
    expires_at = tokens.get("expires_at")
    if expires_at:
        remaining = max(0, int(expires_at - time.time()))
        hours, remainder = divmod(remaining, 3600)
        minutes = remainder // 60
        emit_info(f"   Token expires in: ~{hours}h {minutes}m")

    # Fetch tier/quota status from API
    emit_info("\n📊 Fetching tier status...")
    status = fetch_antigravity_status(tokens.get("access_token", ""))

    if status.error:
        emit_warning(f"   Could not fetch status: {status.error}")
    else:
        # Show tier info
        tier_display = {
            "free-tier": "Free Tier (limited)",
            "standard-tier": "Standard Tier (full access)",
        }
        current = tier_display.get(
            status.current_tier, status.current_tier or "Unknown"
        )
        emit_info(f"   Current tier: {current}")

        if status.project_id:
            emit_info(f"   Project ID: {status.project_id}")

        if status.allowed_tiers:
            available = ", ".join(status.allowed_tiers)
            emit_info(f"   Available tiers: {available}")

    # Show account pool
    manager = AccountManager.load_from_disk()
    if manager.account_count > 1:
        emit_info(f"\n📊 Account Pool: {manager.account_count} accounts")
        for acc in manager.get_accounts_snapshot():
            email_str = acc.email or "Unknown"
            limits = []
            if acc.rate_limit_reset_times:
                for key, reset_time in acc.rate_limit_reset_times.items():
                    if reset_time > time.time() * 1000:
                        wait_sec = int((reset_time - time.time() * 1000) / 1000)
                        limits.append(f"{key}: {wait_sec}s")

            status = f"  • {email_str}"
            if limits:
                status += f" (rate-limited: {', '.join(limits)})"
            emit_info(status)

    # Show configured models
    models = load_antigravity_models()
    antigravity_models = [
        name
        for name, cfg in models.items()
        if cfg.get("oauth_source") == "antigravity-plugin"
    ]

    if antigravity_models:
        emit_info(f"\n🎯 Configured models: {len(antigravity_models)}")
        # Group by family
        gemini = [m for m in antigravity_models if "gemini" in m]
        claude = [m for m in antigravity_models if "claude" in m]
        other = [m for m in antigravity_models if m not in gemini and m not in claude]

        if gemini:
            emit_info(f"   Gemini: {', '.join(sorted(gemini))}")
        if claude:
            emit_info(f"   Claude: {', '.join(sorted(claude))}")
        if other:
            emit_info(f"   Other: {', '.join(sorted(other))}")
    else:
        emit_warning("No Antigravity models configured")


def _handle_logout() -> None:
    """Handle /antigravity-logout command."""
    # Remove tokens
    token_path = get_token_storage_path()
    if token_path.exists():
        token_path.unlink()
        emit_info("✓ Removed OAuth tokens")

    # Remove accounts
    accounts_path = get_accounts_storage_path()
    if accounts_path.exists():
        clear_accounts()
        emit_info("✓ Removed account pool")

    # Remove models
    removed = remove_antigravity_models()
    if removed:
        emit_info(f"✓ Removed {removed} Antigravity models")

    emit_success("👋 Antigravity logout complete")


def _handle_custom_command(command: str, name: str) -> Optional[bool]:
    """Handle Antigravity custom commands."""
    if not name:
        return None

    if name == "antigravity-auth":
        emit_info("🚀 Starting Antigravity OAuth authentication…")
        tokens = load_stored_tokens()
        if tokens and tokens.get("access_token"):
            emit_warning(
                "Existing tokens found. This will refresh your authentication."
            )

        if _perform_authentication():
            # Set a default model
            set_model_name("antigravity-gemini-3-pro-high")
        return True

    if name == "antigravity-add":
        emit_info("➕ Adding another Google account…")
        manager = AccountManager.load_from_disk()
        emit_info(f"Current accounts: {manager.account_count}")
        _perform_authentication(add_account=True)
        return True

    if name == "antigravity-status":
        _handle_status()
        return True

    if name == "antigravity-logout":
        _handle_logout()
        return True

    return None


# Register callbacks
register_callback("custom_command_help", _custom_help)
register_callback("custom_command", _handle_custom_command)
