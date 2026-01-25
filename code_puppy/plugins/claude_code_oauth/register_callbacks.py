"""
Claude Code OAuth Plugin for Code Puppy.

Provides OAuth authentication for Claude Code models and registers
the 'claude_code' model type handler.
"""

from __future__ import annotations

import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from code_puppy.callbacks import register_callback
from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning
from code_puppy.model_switching import set_model_and_reload_agent

from ..oauth_puppy_html import oauth_failure_html, oauth_success_html
from .config import CLAUDE_CODE_OAUTH_CONFIG, get_token_storage_path
from .utils import (
    OAuthContext,
    add_models_to_extra_config,
    assign_redirect_uri,
    build_authorization_url,
    exchange_code_for_tokens,
    fetch_claude_code_models,
    get_valid_access_token,
    load_claude_models_filtered,
    load_stored_tokens,
    prepare_oauth_context,
    remove_claude_code_models,
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
                "Claude Code",
                "You're totally synced with Claude Code now!",
            )
            self._write_response(200, success_html)
        else:
            self.result.error = "Missing code or state"
            failure_html = oauth_failure_html(
                "Claude Code",
                "Missing code or state parameter 🥺",
            )
            self._write_response(400, failure_html)

        self.received_event.set()

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _write_response(self, status: int, body: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))


def _start_callback_server(
    context: OAuthContext,
) -> Optional[Tuple[HTTPServer, _OAuthResult, threading.Event]]:
    port_range = CLAUDE_CODE_OAUTH_CONFIG["callback_port_range"]

    for port in range(port_range[0], port_range[1] + 1):
        try:
            server = HTTPServer(("localhost", port), _CallbackHandler)
            assign_redirect_uri(context, port)
            result = _OAuthResult()
            event = threading.Event()
            _CallbackHandler.result = result
            _CallbackHandler.received_event = event

            def run_server() -> None:
                with server:
                    server.serve_forever()

            threading.Thread(target=run_server, daemon=True).start()
            return server, result, event
        except OSError:
            continue

    emit_error("Could not start OAuth callback server; all candidate ports are in use")
    return None


def _await_callback(context: OAuthContext) -> Optional[str]:
    timeout = CLAUDE_CODE_OAUTH_CONFIG["callback_timeout"]

    started = _start_callback_server(context)
    if not started:
        return None

    server, result, event = started
    redirect_uri = context.redirect_uri
    if not redirect_uri:
        emit_error("Failed to assign redirect URI for OAuth flow")
        server.shutdown()
        return None

    auth_url = build_authorization_url(context)

    try:
        import webbrowser

        from code_puppy.tools.common import should_suppress_browser

        if should_suppress_browser():
            emit_info(
                "[HEADLESS MODE] Would normally open browser for Claude Code OAuth…"
            )
            emit_info(f"In normal mode, would visit: {auth_url}")
        else:
            emit_info("Opening browser for Claude Code OAuth…")
            webbrowser.open(auth_url)
            emit_info(f"If it doesn't open automatically, visit: {auth_url}")
    except Exception as exc:  # pragma: no cover
        if not should_suppress_browser():
            emit_warning(f"Failed to open browser automatically: {exc}")
            emit_info(f"Please open the URL manually: {auth_url}")

    emit_info(f"Listening for callback on {redirect_uri}")
    emit_info(
        "If Claude redirects you to the console callback page, copy the full URL "
        "and paste it back into Code Puppy."
    )

    if not event.wait(timeout=timeout):
        emit_error("OAuth callback timed out. Please try again.")
        server.shutdown()
        return None

    server.shutdown()

    if result.error:
        emit_error(f"OAuth callback error: {result.error}")
        return None

    if result.state != context.state:
        emit_error("State mismatch detected; aborting authentication.")
        return None

    return result.code


def _custom_help() -> List[Tuple[str, str]]:
    return [
        (
            "claude-code-auth",
            "Authenticate with Claude Code via OAuth and import available models",
        ),
        (
            "claude-code-status",
            "Check Claude Code OAuth authentication status and configured models",
        ),
        ("claude-code-logout", "Remove Claude Code OAuth tokens and imported models"),
    ]


def _perform_authentication() -> None:
    context = prepare_oauth_context()
    code = _await_callback(context)
    if not code:
        return

    emit_info("Exchanging authorization code for tokens…")
    tokens = exchange_code_for_tokens(code, context)
    if not tokens:
        emit_error("Token exchange failed. Please retry the authentication flow.")
        return

    if not save_tokens(tokens):
        emit_error(
            "Tokens retrieved but failed to save locally. Check file permissions."
        )
        return

    emit_success("Claude Code OAuth authentication successful!")

    access_token = tokens.get("access_token")
    if not access_token:
        emit_warning("No access token returned; skipping model discovery.")
        return

    emit_info("Fetching available Claude Code models…")
    models = fetch_claude_code_models(access_token)
    if not models:
        emit_warning(
            "Claude Code authentication succeeded but no models were returned."
        )
        return

    emit_info(f"Discovered {len(models)} models: {', '.join(models)}")
    if add_models_to_extra_config(models):
        emit_success(
            "Claude Code models added to your configuration. Use the `claude-code-` prefix!"
        )


def _handle_custom_command(command: str, name: str) -> Optional[bool]:
    if not name:
        return None

    if name == "claude-code-auth":
        emit_info("Starting Claude Code OAuth authentication…")
        tokens = load_stored_tokens()
        if tokens and tokens.get("access_token"):
            emit_warning(
                "Existing Claude Code tokens found. Continuing will overwrite them."
            )
        _perform_authentication()
        set_model_and_reload_agent("claude-code-claude-opus-4-5-20251101")
        return True

    if name == "claude-code-status":
        tokens = load_stored_tokens()
        if tokens and tokens.get("access_token"):
            emit_success("Claude Code OAuth: Authenticated")
            expires_at = tokens.get("expires_at")
            if expires_at:
                remaining = max(0, int(expires_at - time.time()))
                hours, minutes = divmod(remaining // 60, 60)
                emit_info(f"Token expires in ~{hours}h {minutes}m")

            claude_models = [
                name
                for name, cfg in load_claude_models_filtered().items()
                if cfg.get("oauth_source") == "claude-code-plugin"
            ]
            if claude_models:
                emit_info(f"Configured Claude Code models: {', '.join(claude_models)}")
            else:
                emit_warning("No Claude Code models configured yet.")
        else:
            emit_warning("Claude Code OAuth: Not authenticated")
            emit_info("Run /claude-code-auth to begin the browser sign-in flow.")
        return True

    if name == "claude-code-logout":
        token_path = get_token_storage_path()
        if token_path.exists():
            token_path.unlink()
            emit_info("Removed Claude Code OAuth tokens")

        removed = remove_claude_code_models()
        if removed:
            emit_info(f"Removed {removed} Claude Code models from configuration")

        emit_success("Claude Code logout complete")
        return True

    return None


def _create_claude_code_model(model_name: str, model_config: Dict, config: Dict) -> Any:
    """Create a Claude Code model instance.

    This handler is registered via the 'register_model_type' callback to handle
    models with type='claude_code'.
    """
    from anthropic import AsyncAnthropic
    from pydantic_ai.models.anthropic import AnthropicModel
    from pydantic_ai.providers.anthropic import AnthropicProvider

    from code_puppy.claude_cache_client import (
        ClaudeCacheAsyncClient,
        patch_anthropic_client_messages,
    )
    from code_puppy.config import get_effective_model_settings
    from code_puppy.http_utils import get_cert_bundle_path, get_http2
    from code_puppy.model_factory import get_custom_config

    url, headers, verify, api_key = get_custom_config(model_config)

    # Refresh token if this is from the plugin
    if model_config.get("oauth_source") == "claude-code-plugin":
        refreshed_token = get_valid_access_token()
        if refreshed_token:
            api_key = refreshed_token
            custom_endpoint = model_config.get("custom_endpoint")
            if isinstance(custom_endpoint, dict):
                custom_endpoint["api_key"] = refreshed_token

    if not api_key:
        emit_warning(
            f"API key is not set for Claude Code endpoint; skipping model '{model_config.get('name')}'."
        )
        return None

    # Check if interleaved thinking is enabled (defaults to True for OAuth models)
    effective_settings = get_effective_model_settings(model_name)
    interleaved_thinking = effective_settings.get("interleaved_thinking", True)

    # Handle anthropic-beta header based on interleaved_thinking setting
    if "anthropic-beta" in headers:
        beta_parts = [p.strip() for p in headers["anthropic-beta"].split(",")]
        if interleaved_thinking:
            if "interleaved-thinking-2025-05-14" not in beta_parts:
                beta_parts.append("interleaved-thinking-2025-05-14")
        else:
            beta_parts = [p for p in beta_parts if "interleaved-thinking" not in p]
        headers["anthropic-beta"] = ",".join(beta_parts) if beta_parts else None
        if headers.get("anthropic-beta") is None:
            del headers["anthropic-beta"]
    elif interleaved_thinking:
        headers["anthropic-beta"] = "interleaved-thinking-2025-05-14"

    # Use a dedicated client wrapper that injects cache_control on /v1/messages
    if verify is None:
        verify = get_cert_bundle_path()

    http2_enabled = get_http2()

    client = ClaudeCacheAsyncClient(
        headers=headers,
        verify=verify,
        timeout=180,
        http2=http2_enabled,
    )

    anthropic_client = AsyncAnthropic(
        base_url=url,
        http_client=client,
        auth_token=api_key,
    )
    patch_anthropic_client_messages(anthropic_client)
    anthropic_client.api_key = None
    anthropic_client.auth_token = api_key
    provider = AnthropicProvider(anthropic_client=anthropic_client)
    return AnthropicModel(model_name=model_config["name"], provider=provider)


def _register_model_types() -> List[Dict[str, Any]]:
    """Register the claude_code model type handler."""
    return [{"type": "claude_code", "handler": _create_claude_code_model}]


# Global storage for the token refresh heartbeat
# Using a dict to allow multiple concurrent agent runs (keyed by session_id)
_active_heartbeats: Dict[str, Any] = {}


async def _on_agent_run_start(
    agent_name: str,
    model_name: str,
    session_id: Optional[str] = None,
) -> None:
    """Start token refresh heartbeat for Claude Code OAuth models.

    This callback is triggered when an agent run starts. If the model is a
    Claude Code OAuth model, we start a background heartbeat to keep the
    token fresh during long-running operations.
    """
    # Only start heartbeat for Claude Code models
    if not model_name.startswith("claude-code"):
        return

    try:
        from .token_refresh_heartbeat import TokenRefreshHeartbeat

        heartbeat = TokenRefreshHeartbeat()
        await heartbeat.start()

        # Store heartbeat for cleanup, keyed by session_id
        key = session_id or "default"
        _active_heartbeats[key] = heartbeat
        logger.debug(
            "Started token refresh heartbeat for session %s (model: %s)",
            key,
            model_name,
        )
    except ImportError:
        logger.debug("Token refresh heartbeat module not available")
    except Exception as exc:
        logger.debug("Failed to start token refresh heartbeat: %s", exc)


async def _on_agent_run_end(
    agent_name: str,
    model_name: str,
    session_id: Optional[str] = None,
    success: bool = True,
    error: Optional[Exception] = None,
    response_text: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Stop token refresh heartbeat when agent run ends.

    This callback is triggered when an agent run completes (success or failure).
    We stop any heartbeat that was started for this session.
    """
    # We don't use response_text or metadata, just cleanup the heartbeat
    key = session_id or "default"
    heartbeat = _active_heartbeats.pop(key, None)

    if heartbeat is not None:
        try:
            await heartbeat.stop()
            logger.debug(
                "Stopped token refresh heartbeat for session %s (refreshed %d times)",
                key,
                heartbeat.refresh_count,
            )
        except Exception as exc:
            logger.debug("Error stopping token refresh heartbeat: %s", exc)


register_callback("custom_command_help", _custom_help)
register_callback("custom_command", _handle_custom_command)
register_callback("register_model_type", _register_model_types)
register_callback("agent_run_start", _on_agent_run_start)
register_callback("agent_run_end", _on_agent_run_end)
