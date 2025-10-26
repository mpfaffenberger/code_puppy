"""Utility helpers for the Claude Code OAuth plugin."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import requests

from .config import (
    CLAUDE_CODE_OAUTH_CONFIG,
    get_claude_models_path,
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


_oauth_context: Optional[OAuthContext] = None


def _urlsafe_b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _generate_code_verifier() -> str:
    return _urlsafe_b64encode(secrets.token_bytes(64))


def _compute_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    return _urlsafe_b64encode(digest)


def prepare_oauth_context() -> OAuthContext:
    """Create and cache a new OAuth PKCE context."""
    global _oauth_context
    state = secrets.token_urlsafe(32)
    code_verifier = _generate_code_verifier()
    code_challenge = _compute_code_challenge(code_verifier)
    _oauth_context = OAuthContext(
        state=state,
        code_verifier=code_verifier,
        code_challenge=code_challenge,
        created_at=time.time(),
    )
    return _oauth_context


def get_oauth_context() -> Optional[OAuthContext]:
    return _oauth_context


def clear_oauth_context() -> None:
    global _oauth_context
    _oauth_context = None


def assign_redirect_uri(port: int) -> str:
    """Assign redirect URI for the active OAuth context."""
    context = _oauth_context
    if context is None:
        raise RuntimeError("OAuth context has not been prepared")

    host = CLAUDE_CODE_OAUTH_CONFIG["redirect_host"].rstrip("/")
    path = CLAUDE_CODE_OAUTH_CONFIG["redirect_path"].lstrip("/")
    redirect_uri = f"{host}:{port}/{path}"
    context.redirect_uri = redirect_uri
    return redirect_uri


def build_authorization_url(context: OAuthContext) -> str:
    """Return the Claude authorization URL with PKCE parameters."""
    if not context.redirect_uri:
        raise RuntimeError("Redirect URI has not been assigned for this OAuth context")

    params = {
        "response_type": "code",
        "client_id": CLAUDE_CODE_OAUTH_CONFIG["client_id"],
        "redirect_uri": context.redirect_uri,
        "scope": CLAUDE_CODE_OAUTH_CONFIG["scope"],
        "state": context.state,
        "code": "true",
        "code_challenge": context.code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{CLAUDE_CODE_OAUTH_CONFIG['auth_url']}?{urlencode(params)}"


def parse_authorization_code(raw_input: str) -> Tuple[str, Optional[str]]:
    value = raw_input.strip()
    if not value:
        raise ValueError("Authorization code cannot be empty")

    if "#" in value:
        code, state = value.split("#", 1)
        return code.strip(), state.strip() or None

    parts = value.split()
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip() or None

    return value, None


def load_stored_tokens() -> Optional[Dict[str, Any]]:
    try:
        token_path = get_token_storage_path()
        if token_path.exists():
            with open(token_path, "r", encoding="utf-8") as handle:
                return json.load(handle)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Failed to load tokens: %s", exc)
    return None


def save_tokens(tokens: Dict[str, Any]) -> bool:
    try:
        token_path = get_token_storage_path()
        with open(token_path, "w", encoding="utf-8") as handle:
            json.dump(tokens, handle, indent=2)
        token_path.chmod(0o600)
        return True
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Failed to save tokens: %s", exc)
        return False


def load_claude_models() -> Dict[str, Any]:
    try:
        models_path = get_claude_models_path()
        if models_path.exists():
            with open(models_path, "r", encoding="utf-8") as handle:
                return json.load(handle)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Failed to load Claude models: %s", exc)
    return {}


def save_claude_models(models: Dict[str, Any]) -> bool:
    try:
        models_path = get_claude_models_path()
        with open(models_path, "w", encoding="utf-8") as handle:
            json.dump(models, handle, indent=2)
        return True
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Failed to save Claude models: %s", exc)
        return False


def exchange_code_for_tokens(
    auth_code: str, context: OAuthContext
) -> Optional[Dict[str, Any]]:
    if not context.redirect_uri:
        raise RuntimeError("Redirect URI missing from OAuth context")

    payload = {
        "grant_type": "authorization_code",
        "client_id": CLAUDE_CODE_OAUTH_CONFIG["client_id"],
        "code": auth_code,
        "state": context.state,
        "code_verifier": context.code_verifier,
        "redirect_uri": context.redirect_uri,
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "anthropic-beta": "oauth-2025-04-20",
    }

    logger.info("Exchanging code for tokens: %s", CLAUDE_CODE_OAUTH_CONFIG["token_url"])
    logger.debug("Payload keys: %s", list(payload.keys()))
    logger.debug("Headers: %s", headers)
    try:
        response = requests.post(
            CLAUDE_CODE_OAUTH_CONFIG["token_url"],
            json=payload,
            headers=headers,
            timeout=30,
        )
        logger.info("Token exchange response: %s", response.status_code)
        logger.debug("Response body: %s", response.text)
        if response.status_code == 200:
            return response.json()
        logger.error(
            "Token exchange failed: %s - %s",
            response.status_code,
            response.text,
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Token exchange error: %s", exc)
    return None


def fetch_claude_code_models(access_token: str) -> Optional[List[str]]:
    try:
        api_url = f"{CLAUDE_CODE_OAUTH_CONFIG['api_base_url']}/v1/models"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "anthropic-beta": "oauth-2025-04-20",
            "anthropic-version": CLAUDE_CODE_OAUTH_CONFIG.get(
                "anthropic_version", "2023-06-01"
            ),
        }
        response = requests.get(api_url, headers=headers, timeout=30)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data.get("data"), list):
                models: List[str] = []
                for model in data["data"]:
                    name = model.get("id") or model.get("name")
                    if name:
                        models.append(name)
                return models
        else:
            logger.error(
                "Failed to fetch models: %s - %s",
                response.status_code,
                response.text,
            )
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Error fetching Claude Code models: %s", exc)
    return None


def add_models_to_extra_config(models: List[str]) -> bool:
    try:
        # Start fresh - overwrite the file on every auth instead of loading existing
        claude_models = {}
        added = 0
        tokens = load_stored_tokens()
        access_token = tokens["access_token"]

        for model_name in models:
            prefixed = f"{CLAUDE_CODE_OAUTH_CONFIG['prefix']}{model_name}"
            claude_models[prefixed] = {
                "type": "claude_code",
                "name": model_name,
                "custom_endpoint": {
                    "url": CLAUDE_CODE_OAUTH_CONFIG["api_base_url"],
                    "api_key": access_token,
                    "headers": {"anthropic-beta": "oauth-2025-04-20"},
                },
                "context_length": CLAUDE_CODE_OAUTH_CONFIG["default_context_length"],
                "oauth_source": "claude-code-plugin",
            }
            added += 1
        if save_claude_models(claude_models):
            logger.info("Added %s Claude Code models", added)
            return True
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Error adding models to config: %s", exc)
    return False


def remove_claude_code_models() -> int:
    try:
        claude_models = load_claude_models()
        to_remove = [
            name
            for name, config in claude_models.items()
            if config.get("oauth_source") == "claude-code-plugin"
        ]
        if not to_remove:
            return 0
        for model_name in to_remove:
            claude_models.pop(model_name, None)
        if save_claude_models(claude_models):
            return len(to_remove)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Error removing Claude Code models: %s", exc)
    return 0
