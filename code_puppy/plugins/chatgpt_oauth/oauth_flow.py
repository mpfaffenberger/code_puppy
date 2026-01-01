"""ChatGPT OAuth flow closely matching the ChatMock implementation."""

from __future__ import annotations

import datetime
import threading
import time
import urllib.parse
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Optional, Tuple

import requests

from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

from ..oauth_puppy_html import oauth_failure_html, oauth_success_html
from .config import CHATGPT_OAUTH_CONFIG
from .utils import (
    add_models_to_extra_config,
    assign_redirect_uri,
    load_stored_tokens,
    parse_jwt_claims,
    prepare_oauth_context,
    save_tokens,
)

REQUIRED_PORT = CHATGPT_OAUTH_CONFIG["required_port"]
URL_BASE = f"http://localhost:{REQUIRED_PORT}"


@dataclass
class TokenData:
    id_token: str
    access_token: str
    refresh_token: str
    account_id: str


@dataclass
class AuthBundle:
    api_key: Optional[str]
    token_data: TokenData
    last_refresh: str


class _OAuthServer(HTTPServer):
    def __init__(
        self,
        *,
        client_id: str,
        verbose: bool = False,
    ) -> None:
        super().__init__(
            ("localhost", REQUIRED_PORT), _CallbackHandler, bind_and_activate=True
        )
        self.exit_code = 1
        self.verbose = verbose
        self.client_id = client_id
        self.issuer = CHATGPT_OAUTH_CONFIG["issuer"]
        self.token_endpoint = CHATGPT_OAUTH_CONFIG["token_url"]

        # Create fresh OAuth context for this server instance
        context = prepare_oauth_context()
        self.redirect_uri = assign_redirect_uri(context, REQUIRED_PORT)
        self.context = context

    def auth_url(self) -> str:
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": CHATGPT_OAUTH_CONFIG["scope"],
            "code_challenge": self.context.code_challenge,
            "code_challenge_method": "S256",
            "id_token_add_organizations": "true",
            "codex_cli_simplified_flow": "true",
            "state": self.context.state,
        }
        return f"{self.issuer}/oauth/authorize?" + urllib.parse.urlencode(params)

    def exchange_code(self, code: str) -> Tuple[AuthBundle, str]:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "code_verifier": self.context.code_verifier,
        }

        response = requests.post(
            self.token_endpoint,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()

        id_token = payload.get("id_token", "")
        access_token = payload.get("access_token", "")
        refresh_token = payload.get("refresh_token", "")

        id_token_claims = parse_jwt_claims(id_token) or {}
        access_token_claims = parse_jwt_claims(access_token) or {}

        auth_claims = id_token_claims.get("https://api.openai.com/auth") or {}
        chatgpt_account_id = auth_claims.get("chatgpt_account_id", "")
        # Extract org_id from nested auth structure like ChatMock
        organizations = auth_claims.get("organizations", [])
        org_id = None
        if organizations:
            default_org = next(
                (org for org in organizations if org.get("is_default")),
                organizations[0],
            )
            org_id = default_org.get("id")
        # Fallback to top-level org_id if still not found
        if not org_id:
            org_id = id_token_claims.get("organization_id")

        token_data = TokenData(
            id_token=id_token,
            access_token=access_token,
            refresh_token=refresh_token,
            account_id=chatgpt_account_id,
        )

        # Instead of exchanging for an API key, just use the access_token directly
        # This matches how ChatMock works - no token exchange, just OAuth tokens
        api_key = token_data.access_token

        last_refresh = (
            datetime.datetime.now(datetime.timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
        bundle = AuthBundle(
            api_key=api_key, token_data=token_data, last_refresh=last_refresh
        )

        # Build success URL with all the token info
        success_query = {
            "id_token": token_data.id_token,
            "access_token": token_data.access_token,
            "refresh_token": token_data.refresh_token,
            "org_id": org_id or "",
            "plan_type": access_token_claims.get("chatgpt_plan_type"),
            "platform_url": "https://platform.openai.com",
        }
        success_url = f"{URL_BASE}/success?{urllib.parse.urlencode(success_query)}"
        return bundle, success_url


class _CallbackHandler(BaseHTTPRequestHandler):
    server: "_OAuthServer"

    def do_GET(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if path == "/success":
            success_html = oauth_success_html(
                "ChatGPT",
                "You can now close this window and return to Code Puppy.",
            )
            self._send_html(success_html)
            self._shutdown_after_delay(2.0)
            return

        if path != "/auth/callback":
            self._send_failure(404, "Callback endpoint not found for the puppy parade.")
            self._shutdown()
            return

        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)

        code = params.get("code", [None])[0]
        if not code:
            self._send_failure(400, "Missing auth code — the token treat rolled away.")
            self._shutdown()
            return

        try:
            auth_bundle, success_url = self.server.exchange_code(code)
        except Exception as exc:  # noqa: BLE001
            self._send_failure(500, f"Token exchange failed: {exc}")
            self._shutdown()
            return

        tokens = {
            "id_token": auth_bundle.token_data.id_token,
            "access_token": auth_bundle.token_data.access_token,
            "refresh_token": auth_bundle.token_data.refresh_token,
            "account_id": auth_bundle.token_data.account_id,
            "last_refresh": auth_bundle.last_refresh,
        }
        if auth_bundle.api_key:
            tokens["api_key"] = auth_bundle.api_key

        if save_tokens(tokens):
            self.server.exit_code = 0
            # Redirect to the success URL returned by exchange_code
            self._send_redirect(success_url)
        else:
            self._send_failure(
                500, "Unable to persist auth file — a puppy probably chewed it."
            )
            self._shutdown()
        self._shutdown_after_delay(2.0)

    def do_POST(self) -> None:  # noqa: N802
        self._send_failure(
            404, "POST not supported — the pups only fetch GET requests."
        )
        self._shutdown()

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        if getattr(self.server, "verbose", False):
            super().log_message(fmt, *args)

    def _send_redirect(self, url: str) -> None:
        self.send_response(302)
        self.send_header("Location", url)
        self.end_headers()

    def _send_html(self, body: str, status: int = 200) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_failure(self, status: int, reason: str) -> None:
        failure_html = oauth_failure_html("ChatGPT", reason)
        self._send_html(failure_html, status)

    def _shutdown(self) -> None:
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def _shutdown_after_delay(self, seconds: float = 2.0) -> None:
        def _later() -> None:
            try:
                time.sleep(seconds)
            finally:
                self._shutdown()

        threading.Thread(target=_later, daemon=True).start()


def run_oauth_flow() -> None:
    existing_tokens = load_stored_tokens()
    if existing_tokens and existing_tokens.get("access_token"):
        emit_warning("Existing ChatGPT tokens will be overwritten.")

    try:
        server = _OAuthServer(client_id=CHATGPT_OAUTH_CONFIG["client_id"])
    except OSError as exc:
        emit_error(f"Could not start OAuth server on port {REQUIRED_PORT}: {exc}")
        emit_info(f"Use `lsof -ti:{REQUIRED_PORT} | xargs kill` to free the port.")
        return

    auth_url = server.auth_url()
    emit_info(f"Open this URL in your browser: {auth_url}")

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    webbrowser_opened = False
    try:
        import webbrowser

        from code_puppy.tools.common import should_suppress_browser

        if should_suppress_browser():
            emit_info(f"[HEADLESS MODE] Would normally open: {auth_url}")
        else:
            webbrowser_opened = webbrowser.open(auth_url)
    except Exception as exc:  # noqa: BLE001
        emit_warning(f"Could not open browser automatically: {exc}")

    if not webbrowser_opened and not should_suppress_browser():
        emit_warning("Please open the URL manually if the browser did not open.")

    emit_info("Waiting for authentication callback…")

    elapsed = 0.0
    timeout = CHATGPT_OAUTH_CONFIG["callback_timeout"]
    interval = 0.25
    while elapsed < timeout:
        time.sleep(interval)
        elapsed += interval
        if server.exit_code == 0:
            break

    server.shutdown()
    server_thread.join(timeout=5)

    if server.exit_code != 0:
        emit_error("Authentication failed or timed out.")
        return

    tokens = load_stored_tokens()
    if not tokens:
        emit_error("Tokens saved during OAuth flow could not be loaded.")
        return

    api_key = tokens.get("api_key")
    if api_key:
        emit_success("Successfully obtained OAuth access token for API access.")
        emit_info(
            f"Access token saved and available via {CHATGPT_OAUTH_CONFIG['api_key_env_var']}"
        )
    else:
        emit_warning(
            "No API key obtained. You may need to configure projects at platform.openai.com."
        )

    if api_key:
        emit_info("Registering ChatGPT Codex models…")
        from .utils import DEFAULT_CODEX_MODELS

        models = DEFAULT_CODEX_MODELS
        if models:
            if add_models_to_extra_config(models):
                emit_success(
                    "ChatGPT models registered. Use the `chatgpt-` prefix in /model."
                )
