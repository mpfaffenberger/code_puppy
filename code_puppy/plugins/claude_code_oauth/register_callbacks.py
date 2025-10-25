"""
Claude Code OAuth Plugin for Code Puppy.
"""

from __future__ import annotations

import logging
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from code_puppy.callbacks import register_callback
from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

from .config import CLAUDE_CODE_OAUTH_CONFIG, get_token_storage_path
from .utils import (
    OAuthContext,
    add_models_to_extra_config,
    assign_redirect_uri,
    build_authorization_url,
    exchange_code_for_tokens,
    fetch_claude_code_models,
    load_claude_models,
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
            self._write_response(
                200,
                (
                    "<!DOCTYPE html>"
                    "<html><head><style>"
                    "body { margin: 0; padding: 0; overflow: hidden; "
                    "background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); "
                    "font-family: 'Arial', sans-serif; height: 100vh; "
                    "display: flex; flex-direction: column; align-items: center; "
                    "justify-content: center; color: white; } "
                    "h1 { font-size: 3em; margin: 0; animation: bounce 1s infinite; "
                    "text-shadow: 3px 3px 10px rgba(0,0,0,0.3); } "
                    "p { font-size: 1.3em; margin: 20px 0; animation: fadeIn 1.5s; } "
                    ".puppy { position: absolute; font-size: 4em; "
                    "animation: float 3s ease-in-out infinite; } "
                    ".puppy:nth-child(1) { top: 10%; left: 10%; animation-delay: 0s; } "
                    ".puppy:nth-child(2) { top: 20%; right: 15%; animation-delay: 0.5s; } "
                    ".puppy:nth-child(3) { bottom: 15%; left: 20%; animation-delay: 1s; } "
                    ".puppy:nth-child(4) { bottom: 20%; right: 10%; animation-delay: 1.5s; } "
                    ".puppy:nth-child(5) { top: 50%; left: 5%; animation-delay: 0.3s; } "
                    ".puppy:nth-child(6) { top: 50%; right: 5%; animation-delay: 0.8s; } "
                    ".puppy:nth-child(7) { top: 5%; left: 50%; animation-delay: 1.2s; } "
                    ".puppy:nth-child(8) { bottom: 5%; left: 50%; animation-delay: 0.6s; } "
                    ".center { position: relative; z-index: 10; text-align: center; "
                    "background: rgba(255,255,255,0.1); padding: 40px; "
                    "border-radius: 20px; backdrop-filter: blur(10px); "
                    "box-shadow: 0 8px 32px rgba(0,0,0,0.2); } "
                    ".sparkle { display: inline-block; animation: sparkle 1s infinite; } "
                    "@keyframes bounce { 0%, 100% { transform: translateY(0); } "
                    "50% { transform: translateY(-20px); } } "
                    "@keyframes float { 0%, 100% { transform: translateY(0) rotate(0deg); } "
                    "50% { transform: translateY(-30px) rotate(10deg); } } "
                    "@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } } "
                    "@keyframes sparkle { 0%, 100% { transform: scale(1); } "
                    "50% { transform: scale(1.3); } } "
                    "</style></head><body>"
                    "<div class='puppy'>🐶</div>"
                    "<div class='puppy'>🐕</div>"
                    "<div class='puppy'>🐩</div>"
                    "<div class='puppy'>🦮</div>"
                    "<div class='puppy'>🐕‍🦺</div>"
                    "<div class='puppy'>🐶</div>"
                    "<div class='puppy'>🐕</div>"
                    "<div class='puppy'>🐩</div>"
                    "<div class='center'>"
                    "<h1><span class='sparkle'>🎉</span> OAuth Success! <span class='sparkle'>🎉</span></h1>"
                    "<p><span class='sparkle'>✨</span> You're all set with Claude Code! <span class='sparkle'>✨</span></p>"
                    "<p>🐾 This window will close automatically 🐾</p>"
                    "</div>"
                    "<script>setTimeout(() => window.close(), 3000);</script>"
                    "</body></html>"
                ),
            )
        else:
            self.result.error = "Missing code or state"
            self._write_response(
                400,
                (
                    "<!DOCTYPE html>"
                    "<html><head><style>"
                    "body { margin: 0; padding: 0; overflow: hidden; "
                    "background: linear-gradient(135deg, #4b6cb7 0%, #182848 100%); "
                    "font-family: 'Arial', sans-serif; height: 100vh; "
                    "display: flex; flex-direction: column; align-items: center; "
                    "justify-content: center; color: white; } "
                    "h1 { font-size: 2.5em; margin: 0; animation: sadShake 2s infinite; "
                    "text-shadow: 2px 2px 8px rgba(0,0,0,0.5); } "
                    "p { font-size: 1.2em; margin: 20px 0; animation: fadeIn 1.5s; } "
                    ".sad-puppy { position: absolute; font-size: 3.5em; "
                    "animation: droop 4s ease-in-out infinite; filter: grayscale(30%); } "
                    ".sad-puppy:nth-child(1) { top: 15%; left: 15%; animation-delay: 0s; } "
                    ".sad-puppy:nth-child(2) { top: 25%; right: 20%; animation-delay: 0.5s; } "
                    ".sad-puppy:nth-child(3) { bottom: 20%; left: 25%; animation-delay: 1s; } "
                    ".sad-puppy:nth-child(4) { bottom: 25%; right: 15%; animation-delay: 1.5s; } "
                    ".sad-puppy:nth-child(5) { top: 45%; left: 8%; animation-delay: 0.7s; } "
                    ".sad-puppy:nth-child(6) { top: 45%; right: 8%; animation-delay: 1.2s; } "
                    ".center { position: relative; z-index: 10; text-align: center; "
                    "background: rgba(255,255,255,0.08); padding: 40px; "
                    "border-radius: 20px; backdrop-filter: blur(10px); "
                    "box-shadow: 0 8px 32px rgba(0,0,0,0.3); "
                    "border: 2px solid rgba(255,255,255,0.1); } "
                    ".tear { display: inline-block; animation: fall 2s infinite; } "
                    "@keyframes sadShake { 0%, 100% { transform: translateX(0); } "
                    "25% { transform: translateX(-5px); } "
                    "75% { transform: translateX(5px); } } "
                    "@keyframes droop { 0%, 100% { transform: translateY(0) rotate(-5deg); } "
                    "50% { transform: translateY(10px) rotate(5deg); } } "
                    "@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } } "
                    "@keyframes fall { 0% { transform: translateY(0); opacity: 1; } "
                    "100% { transform: translateY(20px); opacity: 0; } } "
                    ".retry-btn { margin-top: 20px; padding: 12px 30px; "
                    "background: rgba(255,255,255,0.2); border: 2px solid white; "
                    "border-radius: 25px; color: white; font-size: 1em; "
                    "cursor: pointer; transition: all 0.3s; } "
                    ".retry-btn:hover { background: rgba(255,255,255,0.3); "
                    "transform: scale(1.05); } "
                    "</style></head><body>"
                    "<div class='sad-puppy'>😭🐶</div>"
                    "<div class='sad-puppy'>😢🐕</div>"
                    "<div class='sad-puppy'>😥🐩</div>"
                    "<div class='sad-puppy'>😫🦮</div>"
                    "<div class='sad-puppy'>😭🐶</div>"
                    "<div class='sad-puppy'>😢🐕</div>"
                    "<div class='center'>"
                    "<h1>💔 OAuth Oopsie! 💔</h1>"
                    "<p><span class='tear'>💧</span> Something went wrong with the OAuth flow <span class='tear'>💧</span></p>"
                    "<p style='font-size: 0.9em; opacity: 0.9;'>🥺 Missing code or state parameter 🥺</p>"
                    "<p style='font-size: 1em; margin-top: 25px;'>🐾 Don't worry! Head back to Code Puppy and try again 🐾</p>"
                    "</div>"
                    "</body></html>"
                ),
            )

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
            assign_redirect_uri(port)
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

    emit_info("Opening browser for Claude Code OAuth…")
    emit_info(f"If it doesn't open automatically, visit: {auth_url}")
    try:
        webbrowser.open(auth_url)
    except Exception as exc:  # pragma: no cover
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
                for name, cfg in load_claude_models().items()
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


register_callback("custom_command_help", _custom_help)
register_callback("custom_command", _handle_custom_command)
