"""Utility helpers for the Claude Code OAuth plugin."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import secrets
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlencode

import requests

from .config import (
    CLAUDE_CODE_OAUTH_CONFIG,
    get_claude_models_path,
    get_token_storage_path,
)

# Proactive refresh buffer default (seconds). Actual buffer is dynamic
# based on expires_in to avoid overly aggressive refreshes.
TOKEN_REFRESH_BUFFER_SECONDS = 300
MIN_REFRESH_BUFFER_SECONDS = 30

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


def assign_redirect_uri(context: OAuthContext, port: int) -> str:
    """Assign redirect URI for the given OAuth context."""
    if context is None:
        raise RuntimeError("OAuth context cannot be None")

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


def _calculate_expires_at(expires_in: Optional[float]) -> Optional[float]:
    if expires_in is None:
        return None
    try:
        return time.time() + float(expires_in)
    except (TypeError, ValueError):
        return None


def _calculate_refresh_buffer(expires_in: Optional[float]) -> float:
    default_buffer = float(TOKEN_REFRESH_BUFFER_SECONDS)
    if expires_in is None:
        return default_buffer
    try:
        expires_value = float(expires_in)
    except (TypeError, ValueError):
        return default_buffer
    return min(default_buffer, max(MIN_REFRESH_BUFFER_SECONDS, expires_value * 0.1))


def _get_expires_at_value(tokens: Dict[str, Any]) -> Optional[float]:
    expires_at = tokens.get("expires_at")
    if expires_at is None:
        return None
    try:
        return float(expires_at)
    except (TypeError, ValueError):
        return None


def _is_token_actually_expired(tokens: Dict[str, Any]) -> bool:
    expires_at_value = _get_expires_at_value(tokens)
    if expires_at_value is None:
        return False
    return time.time() >= expires_at_value


def is_token_expired(tokens: Dict[str, Any]) -> bool:
    expires_at_value = _get_expires_at_value(tokens)
    if expires_at_value is None:
        return False
    buffer_seconds = _calculate_refresh_buffer(tokens.get("expires_in"))
    return time.time() >= expires_at_value - buffer_seconds


def update_claude_code_model_tokens(access_token: str) -> bool:
    try:
        claude_models = load_claude_models()
        if not claude_models:
            return False

        updated = False
        for config in claude_models.values():
            if config.get("oauth_source") != "claude-code-plugin":
                continue
            custom_endpoint = config.get("custom_endpoint")
            if not isinstance(custom_endpoint, dict):
                continue
            custom_endpoint["api_key"] = access_token
            updated = True

        if updated:
            return save_claude_models(claude_models)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Failed to update Claude model tokens: %s", exc)
    return False


def refresh_access_token(force: bool = False) -> Optional[str]:
    tokens = load_stored_tokens()
    if not tokens:
        return None

    if not force and not is_token_expired(tokens):
        return tokens.get("access_token")

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        logger.debug("No refresh_token available")
        return None

    payload = {
        "grant_type": "refresh_token",
        "client_id": CLAUDE_CODE_OAUTH_CONFIG["client_id"],
        "refresh_token": refresh_token,
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "anthropic-beta": "oauth-2025-04-20",
    }

    try:
        response = requests.post(
            CLAUDE_CODE_OAUTH_CONFIG["token_url"],
            json=payload,
            headers=headers,
            timeout=30,
        )
        if response.status_code == 200:
            content_type = response.headers.get("content-type", "")
            if not content_type.startswith("application/json"):
                logger.error(
                    "Token refresh returned non-JSON response (Content-Type: %s): %s",
                    content_type,
                    response.text[:500],
                )
                return None
            try:
                new_tokens = response.json()
            except (ValueError, json.JSONDecodeError) as e:
                logger.error("Failed to parse token refresh response as JSON: %s", e)
                return None
            tokens["access_token"] = new_tokens.get("access_token")
            tokens["refresh_token"] = new_tokens.get("refresh_token", refresh_token)
            expires_in_value = new_tokens.get("expires_in")
            if expires_in_value is None:
                expires_in_value = tokens.get("expires_in")
            if expires_in_value is not None:
                tokens["expires_in"] = expires_in_value
                tokens["expires_at"] = _calculate_expires_at(expires_in_value)
            if save_tokens(tokens):
                update_claude_code_model_tokens(tokens["access_token"])
                return tokens["access_token"]
        else:
            logger.error(
                "Token refresh failed: %s - %s", response.status_code, response.text
            )
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Token refresh error: %s", exc)
    return None


def get_valid_access_token() -> Optional[str]:
    tokens = load_stored_tokens()
    if not tokens:
        logger.debug("No stored Claude Code OAuth tokens found")
        return None

    access_token = tokens.get("access_token")
    if not access_token:
        logger.debug("No access_token in stored tokens")
        return None

    if is_token_expired(tokens):
        logger.info("Claude Code OAuth token expired, attempting refresh")
        refreshed = refresh_access_token()
        if refreshed:
            return refreshed
        if not _is_token_actually_expired(tokens):
            logger.warning(
                "Claude Code token refresh failed; using existing access token until expiry"
            )
            return access_token
        logger.warning("Claude Code token refresh failed")
        return None

    return access_token


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


def load_claude_models_filtered() -> Dict[str, Any]:
    """Load Claude models and filter to only the latest versions.

    This loads the stored models and applies the same filtering logic
    used during saving to ensure only the latest haiku, sonnet, and opus
    models are returned.
    """
    try:
        all_models = load_claude_models()
        if not all_models:
            return {}

        # Extract model names from the configuration
        model_names = []
        for name, config in all_models.items():
            if config.get("oauth_source") == "claude-code-plugin":
                model_names.append(config.get("name", ""))
            else:
                # For non-OAuth models, use the full key
                model_names.append(name)

        # Filter to only latest models
        latest_names = set(
            filter_latest_claude_models(
                model_names, max_per_family={"default": 1, "opus": 3}
            )
        )

        # Return only the filtered models
        filtered_models = {}
        for name, config in all_models.items():
            model_name = config.get("name", name)
            if model_name in latest_names:
                filtered_models[name] = config

        logger.info(
            "Loaded %d models, filtered to %d latest models",
            len(all_models),
            len(filtered_models),
        )
        return filtered_models

    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Failed to load and filter Claude models: %s", exc)
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
            content_type = response.headers.get("content-type", "")
            if not content_type.startswith("application/json"):
                logger.error(
                    "Token exchange returned non-JSON response (Content-Type: %s): %s",
                    content_type,
                    response.text[:500],
                )
                return None
            try:
                token_data = response.json()
            except (ValueError, json.JSONDecodeError) as e:
                logger.error("Failed to parse token exchange response as JSON: %s", e)
                return None
            token_data["expires_at"] = _calculate_expires_at(
                token_data.get("expires_in")
            )
            return token_data
        logger.error(
            "Token exchange failed: %s - %s",
            response.status_code,
            response.text,
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Token exchange error: %s", exc)
    return None


def filter_latest_claude_models(
    models: List[str], max_per_family: Union[int, Dict[str, int]] = 2
) -> List[str]:
    """Filter models to keep the top N latest haiku, sonnet, and opus.

    Parses model names in the format claude-{family}-{major}-{minor}-{date}
    and returns the top ``max_per_family`` versions of each family
    (haiku, sonnet, opus), sorted newest-first.

    Args:
        models: List of model name strings to filter.
        max_per_family: Either a single int applied to all families, or a dict
            mapping family name to its limit (e.g. ``{"opus": 3}``). Families
            not present in the dict fall back to ``"default"`` key, or ``2``.
    """
    # Collect all parsed models per family
    # family -> list of (model_name, major, minor, date)
    family_models: Dict[str, List[Tuple[str, int, int, int]]] = {}

    for model_name in models:
        if model_name == "claude-opus-4-6":
            family_models.setdefault("opus", []).append((model_name, 4, 6, 20260205))
            continue
        # Match pattern: claude-{family}-{major}-{minor}-{date}
        # Examples: claude-haiku-3-5-20241022, claude-sonnet-4-5-20250929
        match = re.match(r"claude-(haiku|sonnet|opus)-(\d+)-(\d+)-(\d+)", model_name)
        if not match:
            # Also try pattern with dots: claude-{family}-{major}.{minor}-{date}
            match = re.match(
                r"claude-(haiku|sonnet|opus)-(\d+)\.(\d+)-(\d+)", model_name
            )

        if not match:
            continue

        family = match.group(1)
        major = int(match.group(2))
        minor = int(match.group(3))
        date = int(match.group(4))

        family_models.setdefault(family, []).append((model_name, major, minor, date))

    # Sort each family descending and keep the top N
    filtered: List[str] = []
    for family, family_entries in family_models.items():
        if isinstance(max_per_family, dict):
            limit = max_per_family.get(family, max_per_family.get("default", 2))
        else:
            limit = max_per_family
        family_entries.sort(key=lambda e: (e[1], e[2], e[3]), reverse=True)
        for entry in family_entries[:limit]:
            filtered.append(entry[0])

    logger.info(
        "Filtered %d models to %d latest models (max_per_family=%s): %s",
        len(models),
        len(filtered),
        max_per_family,
        filtered,
    )
    return filtered


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
            content_type = response.headers.get("content-type", "")
            if not content_type.startswith("application/json"):
                logger.error(
                    "Models fetch returned non-JSON response (Content-Type: %s): %s",
                    content_type,
                    response.text[:500],
                )
                return None
            try:
                data = response.json()
            except (ValueError, json.JSONDecodeError) as e:
                logger.error("Failed to parse models response as JSON: %s", e)
                return None
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


def _build_model_entry(model_name: str, access_token: str, context_length: int) -> dict:
    """Build a single model config entry for claude_models.json."""
    supported_settings = [
        "temperature",
        "extended_thinking",
        "budget_tokens",
        "interleaved_thinking",
    ]

    # Opus 4-6 models support the effort setting
    lower = model_name.lower()
    if "opus-4-6" in lower or "4-6-opus" in lower:
        supported_settings.append("effort")

    return {
        "type": "claude_code",
        "name": model_name,
        "custom_endpoint": {
            "url": CLAUDE_CODE_OAUTH_CONFIG["api_base_url"],
            "api_key": access_token,
            "headers": {
                "anthropic-beta": "oauth-2025-04-20,interleaved-thinking-2025-05-14",
                "x-app": "cli",
                "User-Agent": "claude-cli/2.0.61 (external, cli)",
            },
        },
        "context_length": context_length,
        "oauth_source": "claude-code-plugin",
        "supported_settings": supported_settings,
    }


def add_models_to_extra_config(models: List[str]) -> bool:
    try:
        # Filter to only latest haiku, sonnet, and opus models
        filtered_models = filter_latest_claude_models(
            models, max_per_family={"default": 1, "opus": 3}
        )

        # Start fresh - overwrite the file on every auth instead of loading existing
        claude_models = {}
        added = 0
        access_token = get_valid_access_token() or ""
        prefix = CLAUDE_CODE_OAUTH_CONFIG["prefix"]
        default_ctx = CLAUDE_CODE_OAUTH_CONFIG["default_context_length"]
        long_ctx = CLAUDE_CODE_OAUTH_CONFIG["long_context_length"]
        long_ctx_models = CLAUDE_CODE_OAUTH_CONFIG["long_context_models"]

        for model_name in filtered_models:
            prefixed = f"{prefix}{model_name}"
            claude_models[prefixed] = _build_model_entry(
                model_name, access_token, default_ctx
            )
            added += 1

            # Create a "-long" variant with extended context for eligible models
            if model_name in long_ctx_models:
                long_prefixed = f"{prefix}{model_name}-long"
                claude_models[long_prefixed] = _build_model_entry(
                    model_name, access_token, long_ctx
                )
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
