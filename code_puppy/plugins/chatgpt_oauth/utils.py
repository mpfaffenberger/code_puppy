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
    if context is None:
        raise RuntimeError("OAuth context cannot be None")
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


def get_valid_access_token() -> Optional[str]:
    """Get a valid access token, refreshing if expired.

    Returns:
        Valid access token string, or None if not authenticated or refresh failed.
    """
    tokens = load_stored_tokens()
    if not tokens:
        logger.debug("No stored ChatGPT OAuth tokens found")
        return None

    access_token = tokens.get("access_token")
    if not access_token:
        logger.debug("No access_token in stored tokens")
        return None

    # Check if token is expired by parsing JWT claims
    claims = parse_jwt_claims(access_token)
    if claims:
        exp = claims.get("exp")
        if exp and isinstance(exp, (int, float)):
            # Add 30 second buffer before expiry
            if time.time() > exp - 30:
                logger.info("ChatGPT OAuth token expired, attempting refresh")
                refreshed = refresh_access_token()
                if refreshed:
                    return refreshed
                logger.warning("Token refresh failed")
                return None

    return access_token


def refresh_access_token() -> Optional[str]:
    """Refresh the access token using the refresh token.

    Returns:
        New access token if refresh succeeded, None otherwise.
    """
    tokens = load_stored_tokens()
    if not tokens:
        return None

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        logger.debug("No refresh_token available")
        return None

    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CHATGPT_OAUTH_CONFIG["client_id"],
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
    }

    try:
        response = requests.post(
            CHATGPT_OAUTH_CONFIG["token_url"],
            data=payload,
            headers=headers,
            timeout=30,
        )

        if response.status_code == 200:
            new_tokens = response.json()
            # Merge with existing tokens (preserve account_id, etc.)
            tokens.update(
                {
                    "access_token": new_tokens.get("access_token"),
                    "refresh_token": new_tokens.get("refresh_token", refresh_token),
                    "id_token": new_tokens.get("id_token", tokens.get("id_token")),
                    "last_refresh": datetime.datetime.now(datetime.timezone.utc)
                    .isoformat()
                    .replace("+00:00", "Z"),
                }
            )
            if save_tokens(tokens):
                logger.info("Successfully refreshed ChatGPT OAuth token")
                return tokens["access_token"]
        else:
            logger.error(
                "Token refresh failed: %s - %s", response.status_code, response.text
            )
    except Exception as exc:
        logger.error("Token refresh error: %s", exc)

    return None


def save_tokens(tokens: Dict[str, Any]) -> bool:
    if tokens is None:
        raise TypeError("tokens cannot be None")
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


# Default models available via ChatGPT Codex API
# These are the known models that work with ChatGPT OAuth tokens
# Based on codex-rs CLI and shell-scripts/codex-call.sh
DEFAULT_CODEX_MODELS = [
    "gpt-5.2",
    "gpt-5.2-codex",
]


def fetch_chatgpt_models(access_token: str, account_id: str) -> Optional[List[str]]:
    """Fetch available models from ChatGPT Codex API.

    Attempts to fetch models from the API, but falls back to a default list
    of known Codex-compatible models if the API is unavailable.

    Args:
        access_token: OAuth access token for authentication
        account_id: ChatGPT account ID (required for the API)

    Returns:
        List of model IDs, or default list if API fails
    """
    import platform

    # Build the models URL with client version
    client_version = CHATGPT_OAUTH_CONFIG.get("client_version", "0.72.0")
    base_url = CHATGPT_OAUTH_CONFIG["api_base_url"].rstrip("/")
    models_url = f"{base_url}/models"

    # Build User-Agent to match codex-rs CLI format
    originator = CHATGPT_OAUTH_CONFIG.get("originator", "codex_cli_rs")
    os_name = platform.system()
    if os_name == "Darwin":
        os_name = "Mac OS"
    os_version = platform.release()
    arch = platform.machine()
    user_agent = (
        f"{originator}/{client_version} ({os_name} {os_version}; {arch}) "
        "Terminal_Codex_CLI"
    )

    headers = {
        "Authorization": f"Bearer {access_token}",
        "ChatGPT-Account-Id": account_id,
        "User-Agent": user_agent,
        "originator": originator,
        "Accept": "application/json",
    }

    # Query params
    params = {"client_version": client_version}

    try:
        response = requests.get(models_url, headers=headers, params=params, timeout=30)

        if response.status_code == 200:
            # Parse JSON response
            try:
                data = response.json()
                # The response has a "models" key with list of model objects
                if "models" in data and isinstance(data["models"], list):
                    models = []
                    for model in data["models"]:
                        if model is None:
                            continue
                        model_id = (
                            model.get("slug") or model.get("id") or model.get("name")
                        )
                        if model_id:
                            models.append(model_id)
                    if models:
                        return models
            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning("Failed to parse models response: %s", exc)

        # API didn't return valid models, use default list
        logger.info(
            "Models endpoint returned %d, using default model list",
            response.status_code,
        )

    except requests.exceptions.Timeout:
        logger.warning("Timeout fetching models, using default list")
    except requests.exceptions.RequestException as exc:
        logger.warning("Network error fetching models: %s, using default list", exc)
    except Exception as exc:
        logger.warning("Error fetching models: %s, using default list", exc)

    # Return default models when API fails
    logger.info("Using default Codex models: %s", DEFAULT_CODEX_MODELS)
    return DEFAULT_CODEX_MODELS


def add_models_to_extra_config(models: List[str]) -> bool:
    """Add ChatGPT models to chatgpt_models.json configuration."""
    try:
        chatgpt_models = load_chatgpt_models()
        added = 0
        for model_name in models:
            prefixed = f"{CHATGPT_OAUTH_CONFIG['prefix']}{model_name}"

            # Determine supported settings based on model type
            # All GPT-5.x models support reasoning_effort and verbosity
            supported_settings = ["reasoning_effort", "verbosity"]

            # Only codex models support xhigh reasoning effort
            # Regular gpt-5.2 is capped at "high"
            is_codex = "codex" in model_name.lower()

            chatgpt_models[prefixed] = {
                "type": "chatgpt_oauth",
                "name": model_name,
                "custom_endpoint": {
                    # Codex API uses chatgpt.com/backend-api/codex, not api.openai.com
                    "url": CHATGPT_OAUTH_CONFIG["api_base_url"],
                },
                "context_length": CHATGPT_OAUTH_CONFIG["default_context_length"],
                "oauth_source": "chatgpt-oauth-plugin",
                "supported_settings": supported_settings,
                "supports_xhigh_reasoning": is_codex,
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
        for model_name in to_remove:
            chatgpt_models.pop(model_name, None)
        # Always save, even if no models were removed (to match test expectations)
        if save_chatgpt_models(chatgpt_models):
            return len(to_remove)
    except Exception as exc:
        logger.error("Error removing ChatGPT models: %s", exc)
    return 0
