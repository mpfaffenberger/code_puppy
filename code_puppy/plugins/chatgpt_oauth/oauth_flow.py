"""ChatGPT OAuth flow closely matching the ChatMock implementation."""

from __future__ import annotations

import datetime
import json
import ssl
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional, Tuple

import certifi

from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

from .config import CHATGPT_OAUTH_CONFIG
from .utils import (
    add_models_to_extra_config,
    assign_redirect_uri,
    fetch_chatgpt_models,
    load_stored_tokens,
    parse_jwt_claims,
    prepare_oauth_context,
    save_tokens,
)

REQUIRED_PORT = CHATGPT_OAUTH_CONFIG["required_port"]
URL_BASE = f"http://localhost:{REQUIRED_PORT}"
_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


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


_LOGIN_SUCCESS_HTML = """<!DOCTYPE html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <title>Login successful</title>
  </head>
  <body>
    <div style=\"max-width: 640px; margin: 80px auto; font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;\">
      <h1>Login successful</h1>
      <p>You can now close this window and return to Code Puppy.</p>
    </div>
  </body>
  </html>
"""


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
        data = urllib.parse.urlencode(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri,
                "client_id": self.client_id,
                "code_verifier": self.context.code_verifier,
            }
        ).encode()

        with urllib.request.urlopen(
            urllib.request.Request(
                self.token_endpoint,
                data=data,
                method="POST",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ),
            context=_SSL_CONTEXT,
        ) as resp:
            payload = json.loads(resp.read().decode())

        id_token = payload.get("id_token", "")
        access_token = payload.get("access_token", "")
        refresh_token = payload.get("refresh_token", "")

        id_token_claims = parse_jwt_claims(id_token) or {}
        access_token_claims = parse_jwt_claims(access_token) or {}

        auth_claims = id_token_claims.get("https://api.openai.com/auth") or {}
        chatgpt_account_id = auth_claims.get("chatgpt_account_id", "")

        token_data = TokenData(
            id_token=id_token,
            access_token=access_token,
            refresh_token=refresh_token,
            account_id=chatgpt_account_id,
        )

        api_key, success_url = self._maybe_obtain_api_key(
            id_token_claims, access_token_claims, token_data
        )

        last_refresh = (
            datetime.datetime.now(datetime.timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
        bundle = AuthBundle(
            api_key=api_key, token_data=token_data, last_refresh=last_refresh
        )
        return bundle, success_url or f"{URL_BASE}/success"

    def _maybe_obtain_api_key(
        self,
        token_claims: Dict[str, Any],
        access_claims: Dict[str, Any],
        token_data: TokenData,
    ) -> Tuple[Optional[str], Optional[str]]:
        org_id = token_claims.get("organization_id")
        project_id = token_claims.get("project_id")
        if not org_id or not project_id:
            query = {
                "id_token": token_data.id_token,
                "needs_setup": "false",
                "org_id": org_id or "",
                "project_id": project_id or "",
                "plan_type": access_claims.get("chatgpt_plan_type"),
                "platform_url": "https://platform.openai.com",
            }
            return None, f"{URL_BASE}/success?{urllib.parse.urlencode(query)}"

        today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        exchange_data = urllib.parse.urlencode(
            {
                "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                "client_id": self.client_id,
                "requested_token": "openai-api-key",
                "subject_token": token_data.id_token,
                "subject_token_type": "urn:ietf:params:oauth:token-type:id_token",
                "name": f"Code Puppy ChatGPT [auto-generated] ({today})",
            }
        ).encode()

        with urllib.request.urlopen(
            urllib.request.Request(
                self.token_endpoint,
                data=exchange_data,
                method="POST",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ),
            context=_SSL_CONTEXT,
        ) as resp:
            exchange_payload = json.loads(resp.read().decode())
            exchanged_access_token = exchange_payload.get("access_token")

        chatgpt_plan_type = access_claims.get("chatgpt_plan_type")
        success_query = {
            "id_token": token_data.id_token,
            "access_token": token_data.access_token,
            "refresh_token": token_data.refresh_token,
            "exchanged_access_token": exchanged_access_token,
            "org_id": org_id,
            "project_id": project_id,
            "plan_type": chatgpt_plan_type,
            "platform_url": "https://platform.openai.com",
        }
        success_url = f"{URL_BASE}/success?{urllib.parse.urlencode(success_query)}"
        return exchanged_access_token, success_url


class _CallbackHandler(BaseHTTPRequestHandler):
    server: "_OAuthServer"

    def do_GET(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if path == "/success":
            self._send_html(_LOGIN_SUCCESS_HTML)
            self._shutdown_after_delay(2.0)
            return

        if path != "/auth/callback":
            self.send_error(404, "Not Found")
            self._shutdown()
            return

        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)

        code = params.get("code", [None])[0]
        if not code:
            self.send_error(400, "Missing auth code")
            self._shutdown()
            return

        try:
            auth_bundle, success_url = self.server.exchange_code(code)
        except Exception as exc:  # noqa: BLE001
            self.send_error(500, f"Token exchange failed: {exc}")
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
            self.send_error(500, "Unable to persist auth file")
            self._shutdown()
        self._shutdown_after_delay(2.0)

    def do_POST(self) -> None:  # noqa: N802
        self.send_error(404, "Not Found")
        self._shutdown()

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        if getattr(self.server, "verbose", False):
            super().log_message(fmt, *args)

    def _send_redirect(self, url: str) -> None:
        self.send_response(302)
        self.send_header("Location", url)
        self.end_headers()

    def _send_html(self, body: str) -> None:
        encoded = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

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

        webbrowser_opened = webbrowser.open(auth_url)
    except Exception as exc:  # noqa: BLE001
        emit_warning(f"Could not open browser automatically: {exc}")

    if not webbrowser_opened:
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
        emit_success("Successfully obtained API key from OAuth exchange.")
        emit_info(
            f"API key saved and available via {CHATGPT_OAUTH_CONFIG['api_key_env_var']}"
        )
    else:
        emit_warning(
            "No API key obtained. You may need to configure projects at platform.openai.com."
        )

    if api_key:
        emit_info("Fetching available ChatGPT models…")
        models = fetch_chatgpt_models(api_key)
        if models:
            if add_models_to_extra_config(models, api_key):
                emit_success(
                    "ChatGPT models registered. Use the `chatgpt-` prefix in /model."
                )
        else:
            emit_warning("API key obtained, but model list could not be fetched.")
