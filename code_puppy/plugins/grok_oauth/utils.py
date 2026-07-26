"""Utility helpers for the Grok (x.ai) OAuth plugin."""

from __future__ import annotations

import base64
import datetime
import hashlib
import json
import logging
import secrets
import time
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

import requests

from .config import GROK_OAUTH_CONFIG, get_token_storage_path

logger = logging.getLogger(__name__)

_discovery_cache: Optional[Dict[str, str]] = None


def _urlsafe_b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def generate_pkce_pair() -> Tuple[str, str]:
    """Return a (code_verifier, code_challenge) PKCE S256 pair."""
    code_verifier = _urlsafe_b64encode(secrets.token_bytes(32))
    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    return code_verifier, _urlsafe_b64encode(digest)


def validate_xai_endpoint(url: str) -> str:
    """Ensure a discovered endpoint is HTTPS on x.ai (or a subdomain)."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or (host != "x.ai" and not host.endswith(".x.ai")):
        raise ValueError(f"xAI OAuth discovery returned an unexpected endpoint: {url}")
    return url


def fetch_discovery() -> Dict[str, str]:
    """Fetch (and cache) the xAI OIDC discovery document."""
    global _discovery_cache
    if _discovery_cache:
        return _discovery_cache

    response = requests.get(
        GROK_OAUTH_CONFIG["discovery_url"],
        headers={"Accept": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    authorization_endpoint = data.get("authorization_endpoint")
    token_endpoint = data.get("token_endpoint")
    if not authorization_endpoint or not token_endpoint:
        raise ValueError(
            "xAI OAuth discovery response did not include authorization/token endpoints"
        )

    _discovery_cache = {
        "authorization_endpoint": validate_xai_endpoint(authorization_endpoint),
        "token_endpoint": validate_xai_endpoint(token_endpoint),
    }
    return _discovery_cache


def _utc_now_iso() -> str:
    return (
        datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    )


def tokens_from_payload(
    payload: Dict[str, Any],
    token_endpoint: str,
    fallback_refresh: str = "",
) -> Dict[str, Any]:
    """Normalize an OAuth token response into our stored-token shape."""
    access_token = payload.get("access_token")
    if not access_token:
        raise ValueError("xAI token response did not include an access token")

    expires_in = payload.get("expires_in") or 3600
    return {
        "access_token": access_token,
        "refresh_token": payload.get("refresh_token") or fallback_refresh,
        "id_token": payload.get("id_token", ""),
        "token_type": payload.get("token_type", "Bearer"),
        "expires_at": time.time() + float(expires_in),
        "token_endpoint": token_endpoint,
        "last_refresh": _utc_now_iso(),
    }


def load_stored_tokens() -> Optional[Dict[str, Any]]:
    try:
        token_path = get_token_storage_path()
        if token_path.exists():
            with open(token_path, "r", encoding="utf-8") as handle:
                return json.load(handle)
    except Exception as exc:
        logger.error("Failed to load Grok OAuth tokens: %s", exc)
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
        logger.error("Failed to save Grok OAuth tokens: %s", exc)
    return False


def exchange_token(token_endpoint: str, body: Dict[str, str]) -> Dict[str, Any]:
    """POST a form-encoded token request and return the JSON payload."""
    response = requests.post(
        token_endpoint,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        timeout=30,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"xAI token request failed: {response.status_code} {response.text}"
        )
    return response.json()


def refresh_access_token() -> Optional[str]:
    """Refresh the access token using the stored refresh token."""
    tokens = load_stored_tokens()
    if not tokens:
        return None

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        logger.debug("No refresh_token available for Grok OAuth")
        return None

    try:
        token_endpoint = tokens.get("token_endpoint") or ""
        token_endpoint = (
            validate_xai_endpoint(token_endpoint)
            if token_endpoint
            else fetch_discovery()["token_endpoint"]
        )
        payload = exchange_token(
            token_endpoint,
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": GROK_OAUTH_CONFIG["client_id"],
            },
        )
        new_tokens = tokens_from_payload(payload, token_endpoint, refresh_token)
        if save_tokens(new_tokens):
            logger.info("Successfully refreshed Grok OAuth token")
            return new_tokens["access_token"]
    except Exception as exc:
        logger.error("Grok OAuth token refresh failed: %s", exc)
    return None


def get_valid_access_token() -> Optional[str]:
    """Return a valid access token, refreshing if it is (nearly) expired."""
    tokens = load_stored_tokens()
    if not tokens:
        logger.debug("No stored Grok OAuth tokens found")
        return None

    access_token = tokens.get("access_token")
    if not access_token:
        return None

    expires_at = tokens.get("expires_at")
    skew = GROK_OAUTH_CONFIG["refresh_skew_seconds"]
    if isinstance(expires_at, (int, float)) and time.time() > expires_at - skew:
        logger.info("Grok OAuth token expired, attempting refresh")
        return refresh_access_token()

    return access_token
