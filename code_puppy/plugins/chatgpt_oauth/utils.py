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


_oauth_context: Optional[OAuthContext] = None


def _urlsafe_b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _generate_code_verifier() -> str:
    return secrets.token_hex(64)


def _compute_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    return _urlsafe_b64encode(digest)


def prepare_oauth_context() -> OAuthContext:
    """Create and cache a new OAuth PKCE context."""
    global _oauth_context
    state = secrets.token_hex(32)
    code_verifier = _generate_code_verifier()
    code_challenge = _compute_code_challenge(code_verifier)

    # Set expiration 4 minutes from now (OpenAI sessions are short)
    expires_at = time.time() + 240

    _oauth_context = OAuthContext(
        state=state,
        code_verifier=code_verifier,
        code_challenge=code_challenge,
        created_at=time.time(),
        expires_at=expires_at,
    )
    return _oauth_context


def get_oauth_context() -> Optional[OAuthContext]:
    """Get current OAuth context, checking if it's expired."""
    global _oauth_context
    if _oauth_context and _oauth_context.is_expired():
        logger.warning("OAuth context expired, clearing")
        _oauth_context = None
    return _oauth_context


def clear_oauth_context() -> None:
    global _oauth_context
    _oauth_context = None


def assign_redirect_uri(port: int) -> str:
    """Assign redirect URI for the active OAuth context."""
    context = _oauth_context
    if context is None:
        raise RuntimeError("OAuth context has not been prepared")

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


def exchange_for_api_key(tokens: Dict[str, Any]) -> Optional[str]:
    """Exchange id_token for OpenAI API key using token exchange flow."""
    id_token = tokens.get("id_token")
    if not id_token:
        logger.error("No id_token available for API key exchange")
        return None

    # Parse JWT to extract organization and project info
    id_token_claims = parse_jwt_claims(id_token)
    if not id_token_claims:
        logger.error("Failed to parse id_token claims")
        return None

    org_id = id_token_claims.get("organization_id")
    project_id = id_token_claims.get("project_id")

    if not org_id or not project_id:
        logger.warning(
            "No organization or project ID in token; skipping API key exchange"
        )
        return None

    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    payload = {
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "client_id": CHATGPT_OAUTH_CONFIG["client_id"],
        "requested_token": "openai-api-key",
        "subject_token": id_token,
        "subject_token_type": "urn:ietf:params:oauth:token-type:id_token",
        "name": f"Code Puppy ChatGPT [auto-generated] ({today})",
    }

    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    try:
        response = requests.post(
            CHATGPT_OAUTH_CONFIG["token_url"],
            data=payload,
            headers=headers,
            timeout=30,
        )
        if response.status_code == 200:
            exchange_data = response.json()
            api_key = exchange_data.get("access_token")
            if api_key:
                logger.info("Successfully exchanged token for API key")
                return api_key
        logger.error(
            "API key exchange failed: %s - %s", response.status_code, response.text
        )
    except Exception as exc:
        logger.error("API key exchange error: %s", exc)
    return None


def fetch_chatgpt_models(api_key: str) -> Optional[List[str]]:
    """Fetch available models from OpenAI API."""
    try:
        api_url = f"{CHATGPT_OAUTH_CONFIG['api_base_url']}/v1/models"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        response = requests.get(api_url, headers=headers, timeout=30)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data.get("data"), list):
                models: List[str] = []
                for model in data["data"]:
                    model_id = model.get("id")
                    if model_id and (
                        model_id.startswith("gpt-")
                        or model_id.startswith("o1-")
                        or model_id.startswith("o3-")
                    ):
                        models.append(model_id)
                return models
        else:
            logger.error(
                "Failed to fetch models: %s - %s",
                response.status_code,
                response.text,
            )
    except Exception as exc:
        logger.error("Error fetching ChatGPT models: %s", exc)
    return None


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
