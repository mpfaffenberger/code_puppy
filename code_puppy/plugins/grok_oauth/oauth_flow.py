"""Grok (x.ai) OAuth flow matching the official Grok CLI / pi-xai-oauth."""

from __future__ import annotations

import secrets
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

from ..oauth_puppy_html import oauth_failure_html, oauth_success_html
from .config import GROK_OAUTH_CONFIG
from .utils import (
    exchange_token,
    fetch_discovery,
    generate_pkce_pair,
    load_stored_tokens,
    save_tokens,
    tokens_from_payload,
)

_ALLOWED_CORS_ORIGINS = ("https://accounts.x.ai", "https://auth.x.ai")


class _OAuthServer(HTTPServer):
    """Localhost callback server holding the state for one OAuth attempt."""

    def __init__(self) -> None:
        host = GROK_OAUTH_CONFIG["redirect_host"]
        preferred_port = GROK_OAUTH_CONFIG["redirect_port"]
        try:
            super().__init__((host, preferred_port), _CallbackHandler)
        except OSError:
            # Preferred port busy — xAI accepts ephemeral localhost ports.
            super().__init__((host, 0), _CallbackHandler)

        self.exit_code = 1
        discovery = fetch_discovery()
        self.authorization_endpoint = discovery["authorization_endpoint"]
        self.token_endpoint = discovery["token_endpoint"]
        self.state = secrets.token_hex(16)
        self.nonce = secrets.token_hex(16)
        self.code_verifier, self.code_challenge = generate_pkce_pair()
        port = self.server_address[1]
        self.redirect_uri = f"http://{host}:{port}{GROK_OAUTH_CONFIG['redirect_path']}"

    def auth_url(self) -> str:
        params = {
            "response_type": "code",
            "client_id": GROK_OAUTH_CONFIG["client_id"],
            "redirect_uri": self.redirect_uri,
            "scope": GROK_OAUTH_CONFIG["scope"],
            "code_challenge": self.code_challenge,
            "code_challenge_method": "S256",
            "state": self.state,
            "nonce": self.nonce,
        }
        return f"{self.authorization_endpoint}?{urllib.parse.urlencode(params)}"

    def exchange_code(self, code: str) -> bool:
        payload = exchange_token(
            self.token_endpoint,
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri,
                "client_id": GROK_OAUTH_CONFIG["client_id"],
                "code_verifier": self.code_verifier,
            },
        )
        return save_tokens(tokens_from_payload(payload, self.token_endpoint))


class _CallbackHandler(BaseHTTPRequestHandler):
    server: "_OAuthServer"

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != GROK_OAUTH_CONFIG["redirect_path"]:
            self._send_failure(404, "Callback endpoint not found for the puppy parade.")
            return

        params = urllib.parse.parse_qs(parsed.query)
        error = params.get("error", [None])[0]
        if error:
            description = params.get("error_description", [error])[0]
            self._send_failure(400, f"xAI authorization failed: {description}")
            self._shutdown_after_delay()
            return

        if params.get("state", [None])[0] != self.server.state:
            self._send_failure(
                400, "OAuth state mismatch — a squirrel may have tampered with it."
            )
            return

        code = params.get("code", [None])[0]
        if not code:
            self._send_failure(400, "Missing auth code — the token treat rolled away.")
            self._shutdown_after_delay()
            return

        try:
            saved = self.server.exchange_code(code)
        except Exception as exc:  # noqa: BLE001
            self._send_failure(500, f"Token exchange failed: {exc}")
            self._shutdown_after_delay()
            return

        if saved:
            self.server.exit_code = 0
            self._send_html(
                oauth_success_html(
                    "Grok",
                    "You can now close this window and return to Code Puppy.",
                )
            )
        else:
            self._send_failure(
                500, "Unable to persist auth file — a puppy probably chewed it."
            )
        self._shutdown_after_delay()

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        pass

    def _send_cors_headers(self) -> None:
        origin = self.headers.get("Origin")
        if origin not in _ALLOWED_CORS_ORIGINS:
            return
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Vary", "Origin")

    def _send_html(self, body: str, status: int = 200) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self._send_cors_headers()
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_failure(self, status: int, reason: str) -> None:
        self._send_html(oauth_failure_html("Grok", reason), status)

    def _shutdown_after_delay(self, seconds: float = 2.0) -> None:
        def _later() -> None:
            time.sleep(seconds)
            self.server.shutdown()

        threading.Thread(target=_later, daemon=True).start()


def run_oauth_flow() -> bool:
    """Run the browser OAuth flow. Returns True when tokens were saved."""
    existing_tokens = load_stored_tokens()
    if existing_tokens and existing_tokens.get("access_token"):
        emit_warning("Existing Grok tokens will be overwritten.")

    try:
        server = _OAuthServer()
    except Exception as exc:  # noqa: BLE001
        emit_error(f"Could not start Grok OAuth flow: {exc}")
        return False

    auth_url = server.auth_url()
    emit_info(f"Open this URL in your browser: {auth_url}")

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    from code_puppy.tools.common import should_suppress_browser

    if should_suppress_browser():
        emit_info(f"[HEADLESS MODE] Would normally open: {auth_url}")
    else:
        try:
            import webbrowser

            if not webbrowser.open(auth_url):
                emit_warning("Please open the URL manually — the browser stayed home.")
        except Exception as exc:  # noqa: BLE001
            emit_warning(f"Could not open browser automatically: {exc}")

    emit_info("Waiting for xAI authentication callback…")

    elapsed = 0.0
    timeout = GROK_OAUTH_CONFIG["callback_timeout"]
    interval = 0.25
    while elapsed < timeout and server.exit_code != 0:
        time.sleep(interval)
        elapsed += interval

    server.shutdown()
    server_thread.join(timeout=5)

    if server.exit_code != 0:
        emit_error("Grok authentication failed or timed out.")
        return False

    emit_success("Grok OAuth complete — access token saved.")
    return True
