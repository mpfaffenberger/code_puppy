"""Utility helpers for the ChatGPT OAuth plugin."""

from __future__ import annotations

import base64
import datetime
import hashlib
import json
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs as urllib_parse_qs
from urllib.parse import urlencode, urlparse

import requests

from .config import (
    CHATGPT_OAUTH_CONFIG,
    get_chatgpt_models_path,
    get_token_storage_path,
)

logger = logging.getLogger(__name__)


@dataclass
class OAuthContext:
    """Runtime state for an in-progress OAuth flow."""

    state: str
    code_verifier: str
    code_challenge: str
    created_at: float
    redirect_uri: Optional[str] = None
    expires_at: Optional[float] = None  # Add expiration time

    def is_expired(self) -> bool:
        """Check if this OAuth context has expired."""
        if self.expires_at is None:
            # Default 5 minute expiration if not set
            return time.time() - self.created_at > 300
        return time.time() > self.expires_at


def _urlsafe_b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _generate_code_verifier() -> str:
    return secrets.token_hex(64)


def _compute_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    return _urlsafe_b64encode(digest)


def prepare_oauth_context() -> OAuthContext:
    """Create a fresh OAuth PKCE context."""
    state = secrets.token_hex(32)
    code_verifier = _generate_code_verifier()
    code_challenge = _compute_code_challenge(code_verifier)

    # Set expiration 4 minutes from now (OpenAI sessions are short)
    expires_at = time.time() + 240

    return OAuthContext(
        state=state,
        code_verifier=code_verifier,
        code_challenge=code_challenge,
        created_at=time.time(),
        expires_at=expires_at,
    )


def assign_redirect_uri(context: OAuthContext, port: int) -> str:
    """Assign redirect URI for the given OAuth context."""
    host = CHATGPT_OAUTH_CONFIG["redirect_host"].rstrip("/")
    path = CHATGPT_OAUTH_CONFIG["redirect_path"].lstrip("/")
    required_port = CHATGPT_OAUTH_CONFIG.get("required_port")
    if required_port and port != required_port:
        raise RuntimeError(
            f"OAuth flow must use port {required_port}; attempted to assign port {port}"
        )
    redirect_uri = f"{host}:{port}/{path}"
    context.redirect_uri = redirect_uri
    return redirect_uri


def build_authorization_url(context: OAuthContext) -> str:
    """Return the OpenAI authorization URL with PKCE parameters."""
    if not context.redirect_uri:
        raise RuntimeError("Redirect URI has not been assigned for this OAuth context")

    params = {
        "response_type": "code",
        "client_id": CHATGPT_OAUTH_CONFIG["client_id"],
        "redirect_uri": context.redirect_uri,
        "scope": CHATGPT_OAUTH_CONFIG["scope"],
        "code_challenge": context.code_challenge,
        "code_challenge_method": "S256",
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
        "state": context.state,
    }
    return f"{CHATGPT_OAUTH_CONFIG['auth_url']}?{urlencode(params)}"


def parse_authorization_error(url: str) -> Optional[str]:
    """Parse error from OAuth callback URL."""
    try:
        parsed = urlparse(url)
        params = urllib_parse_qs(parsed.query)
        error = params.get("error", [None])[0]
        error_description = params.get("error_description", [None])[0]
        if error:
            return f"{error}: {error_description or 'Unknown error'}"
    except Exception as exc:
        logger.error("Failed to parse OAuth error: %s", exc)
    return None


def parse_jwt_claims(token: str) -> Optional[Dict[str, Any]]:
    """Parse JWT token to extract claims."""
    if not token or token.count(".") != 2:
        return None
    try:
        _, payload, _ = token.split(".")
        padded = payload + "=" * (-len(payload) % 4)
        data = base64.urlsafe_b64decode(padded.encode())
        return json.loads(data.decode())
    except Exception as exc:
        logger.error("Failed to parse JWT: %s", exc)
    return None


def load_stored_tokens() -> Optional[Dict[str, Any]]:
    try:
        token_path = get_token_storage_path()
        if token_path.exists():
            with open(token_path, "r", encoding="utf-8") as handle:
                return json.load(handle)
    except Exception as exc:
        logger.error("Failed to load tokens: %s", exc)
    return None


def save_tokens(tokens: Dict[str, Any]) -> bool:
    try:
        token_path = get_token_storage_path()
        with open(token_path, "w", encoding="utf-8") as handle:
            json.dump(tokens, handle, indent=2)
        token_path.chmod(0o600)
        return True
    except Exception as exc:
        logger.error("Failed to save tokens: %s", exc)
    return False


def load_chatgpt_models() -> Dict[str, Any]:
    try:
        models_path = get_chatgpt_models_path()
        if models_path.exists():
            with open(models_path, "r", encoding="utf-8") as handle:
                return json.load(handle)
    except Exception as exc:
        logger.error("Failed to load ChatGPT models: %s", exc)
    return {}


def save_chatgpt_models(models: Dict[str, Any]) -> bool:
    try:
        models_path = get_chatgpt_models_path()
        with open(models_path, "w", encoding="utf-8") as handle:
            json.dump(models, handle, indent=2)
        return True
    except Exception as exc:
        logger.error("Failed to save ChatGPT models: %s", exc)
    return False


def exchange_code_for_tokens(
    auth_code: str, context: OAuthContext
) -> Optional[Dict[str, Any]]:
    """Exchange authorization code for access tokens."""
    if not context.redirect_uri:
        raise RuntimeError("Redirect URI missing from OAuth context")

    if context.is_expired():
        logger.error("OAuth context expired, cannot exchange code")
        return None

    payload = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": context.redirect_uri,
        "client_id": CHATGPT_OAUTH_CONFIG["client_id"],
        "code_verifier": context.code_verifier,
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
    }

    logger.info("Exchanging code for tokens: %s", CHATGPT_OAUTH_CONFIG["token_url"])
    try:
        response = requests.post(
            CHATGPT_OAUTH_CONFIG["token_url"],
            data=payload,
            headers=headers,
            timeout=30,
        )
        logger.info("Token exchange response: %s", response.status_code)
        if response.status_code == 200:
            token_data = response.json()
            # Add timestamp
            token_data["last_refresh"] = (
                datetime.datetime.now(datetime.timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
            )
            return token_data
        else:
            logger.error(
                "Token exchange failed: %s - %s",
                response.status_code,
                response.text,
            )
            # Try to parse OAuth error
            if response.headers.get("content-type", "").startswith("application/json"):
                try:
                    error_data = response.json()
                    if "error" in error_data:
                        logger.error(
                            "OAuth error: %s",
                            error_data.get("error_description", error_data["error"]),
                        )
                except Exception:
                    pass
    except Exception as exc:
        logger.error("Token exchange error: %s", exc)
    return None


def fetch_chatgpt_models(api_key: str) -> Optional[List[str]]:
    """Fetch available models from OpenAI API."""
    models = ["gpt-5", "gpt-5-codex", "gpt-5-mini", "gpt-5-nano"]
    return models


def add_models_to_extra_config(models: List[str], api_key: str) -> bool:
    """Add ChatGPT models to chatgpt_models.json configuration."""
    try:
        chatgpt_models = load_chatgpt_models()
        added = 0
        for model_name in models:
            prefixed = f"{CHATGPT_OAUTH_CONFIG['prefix']}{model_name}"
            chatgpt_models[prefixed] = {
                "type": "openai",
                "name": model_name,
                "custom_endpoint": {
                    "url": CHATGPT_OAUTH_CONFIG["api_base_url"],
                    "api_key": f"${CHATGPT_OAUTH_CONFIG['api_key_env_var']}",
                },
                "context_length": CHATGPT_OAUTH_CONFIG["default_context_length"],
                "oauth_source": "chatgpt-oauth-plugin",
            }
            added += 1
        if save_chatgpt_models(chatgpt_models):
            logger.info("Added %s ChatGPT models", added)
            return True
    except Exception as exc:
        logger.error("Error adding models to config: %s", exc)
    return False


def remove_chatgpt_models() -> int:
    """Remove ChatGPT OAuth models from chatgpt_models.json."""
    try:
        chatgpt_models = load_chatgpt_models()
        to_remove = [
            name
            for name, config in chatgpt_models.items()
            if config.get("oauth_source") == "chatgpt-oauth-plugin"
        ]
        if not to_remove:
            return 0
        for model_name in to_remove:
            chatgpt_models.pop(model_name, None)
        if save_chatgpt_models(chatgpt_models):
            return len(to_remove)
    except Exception as exc:
        logger.error("Error removing ChatGPT models: %s", exc)
    return 0
