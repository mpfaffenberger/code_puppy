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
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import requests

from .config import (
    CLAUDE_CODE_OAUTH_CONFIG,
    get_claude_models_path,
    get_token_storage_path,
)

logger = logging.getLogger(__name__)

# Token refresh tracking
_last_refresh_time: float = 0.0
REFRESH_INTERVAL_SECONDS: float = 30 * 60  # 30 minutes


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
        latest_names = set(filter_latest_claude_models(model_names))

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
            return response.json()
        logger.error(
            "Token exchange failed: %s - %s",
            response.status_code,
            response.text,
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Token exchange error: %s", exc)
    return None


def filter_latest_claude_models(models: List[str]) -> List[str]:
    """Filter models to keep only the latest haiku, sonnet, and opus.

    Parses model names in the format claude-{family}-{major}-{minor}-{date}
    and returns only the latest version of each family (haiku, sonnet, opus).
    """
    # Dictionary to store the latest model for each family
    # family -> (model_name, major, minor, date)
    latest_models: Dict[str, Tuple[str, int, int, int]] = {}

    for model_name in models:
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

        if family not in latest_models:
            latest_models[family] = (model_name, major, minor, date)
        else:
            # Compare versions: first by major, then minor, then date
            _, cur_major, cur_minor, cur_date = latest_models[family]
            if (major, minor, date) > (cur_major, cur_minor, cur_date):
                latest_models[family] = (model_name, major, minor, date)

    # Return only the model names
    filtered = [model_data[0] for model_data in latest_models.values()]
    logger.info(
        "Filtered %d models to %d latest models: %s",
        len(models),
        len(filtered),
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
        # Filter to only latest haiku, sonnet, and opus models
        filtered_models = filter_latest_claude_models(models)

        # Start fresh - overwrite the file on every auth instead of loading existing
        claude_models = {}
        added = 0
        tokens = load_stored_tokens()

        # Handle case where tokens are None or empty
        access_token = ""
        if tokens and "access_token" in tokens:
            access_token = tokens["access_token"]

        for model_name in filtered_models:
            prefixed = f"{CLAUDE_CODE_OAUTH_CONFIG['prefix']}{model_name}"
            claude_models[prefixed] = {
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
                "context_length": CLAUDE_CODE_OAUTH_CONFIG["default_context_length"],
                "oauth_source": "claude-code-plugin",
                "supported_settings": [
                    "temperature",
                    "extended_thinking",
                    "budget_tokens",
                    "interleaved_thinking",
                ],
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


def _update_model_tokens(new_access_token: str) -> bool:
    """Update all Claude Code models with the new access token.

    Args:
        new_access_token: The new access token to set

    Returns:
        True if successful, False otherwise
    """
    try:
        claude_models = load_claude_models()
        if not claude_models:
            logger.debug("No models to update")
            return True

        updated = 0
        for _model_name, config in claude_models.items():
            if config.get("oauth_source") == "claude-code-plugin":
                if (
                    "custom_endpoint" in config
                    and "api_key" in config["custom_endpoint"]
                ):
                    config["custom_endpoint"]["api_key"] = new_access_token
                    updated += 1

        if updated > 0:
            if save_claude_models(claude_models):
                logger.info("Updated %s model configurations with new token", updated)
                return True
            else:
                logger.error("Failed to save updated model configurations")
                return False

        return True

    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Error updating model tokens: %s", exc)
        return False


def refresh_access_token() -> Optional[str]:
    """Refresh the access token using the refresh token.

    Returns:
        New access token if successful, None otherwise
    """
    try:
        tokens = load_stored_tokens()
        if not tokens:
            logger.debug("No stored tokens found for refresh")
            return None

        if "refresh_token" not in tokens:
            logger.debug("No refresh token available")
            return None

        refresh_token = tokens["refresh_token"]

        # Prepare refresh request
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

        logger.info("Refreshing Claude Code access token...")
        response = requests.post(
            CLAUDE_CODE_OAUTH_CONFIG["token_url"],
            json=payload,
            headers=headers,
            timeout=30,
        )

        if response.status_code == 200:
            token_data = response.json()

            # Update tokens with new access token and expiry
            new_access_token = token_data.get("access_token")
            if not new_access_token:
                logger.error("No access_token in refresh response")
                return None

            # Update stored tokens
            tokens["access_token"] = new_access_token

            # Update expiry if provided
            if "expires_in" in token_data:
                tokens["expires_at"] = time.time() + token_data["expires_in"]

            # Update refresh token if a new one was provided
            if "refresh_token" in token_data:
                tokens["refresh_token"] = token_data["refresh_token"]

            # Save updated tokens
            if save_tokens(tokens):
                logger.info("Claude Code access token refreshed successfully")

                # Update model configurations with new token
                _update_model_tokens(new_access_token)

                return new_access_token
            else:
                logger.error("Failed to save refreshed tokens")
                return None
        else:
            logger.warning(
                "Token refresh failed: %s - %s",
                response.status_code,
                response.text,
            )
            return None

    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Error refreshing access token: %s", exc)
        return None


def _is_using_claude_code_model() -> bool:
    """Check if the current agent is using a Claude Code OAuth model.

    Returns:
        True if currently using a claude-code-* model, False otherwise
    """
    try:
        from code_puppy.agents import get_current_agent
        from code_puppy.model_utils import is_claude_code_model

        agent = get_current_agent()
        if agent is None:
            return False

        model_name = agent.get_model_name()
        if not model_name:
            return False

        return is_claude_code_model(model_name)
    except Exception as exc:
        logger.debug("Could not determine current model: %s", exc)
        return False


def maybe_refresh_token() -> bool:
    """Refresh the token if 30 minutes have passed since last refresh.

    This function is designed to be called on every prompt, but will only
    actually refresh the token if:
    1. The current model is a Claude Code OAuth model (starts with 'claude-code-')
    2. REFRESH_INTERVAL_SECONDS (30 min) has passed since last refresh

    Returns:
        True if refresh was attempted (regardless of success), False if skipped
    """
    global _last_refresh_time

    # Only refresh if we're actually using a Claude Code model
    if not _is_using_claude_code_model():
        return False

    # Check if we have tokens at all
    tokens = load_stored_tokens()
    if not tokens or "refresh_token" not in tokens:
        return False

    current_time = time.time()
    time_since_last = current_time - _last_refresh_time

    if time_since_last < REFRESH_INTERVAL_SECONDS:
        logger.debug(
            "Skipping token refresh, %.1f minutes until next refresh",
            (REFRESH_INTERVAL_SECONDS - time_since_last) / 60,
        )
        return False

    logger.info(
        "Token refresh interval reached (%.1f min since last refresh)",
        time_since_last / 60,
    )

    # Attempt refresh
    result = refresh_access_token()
    if result:
        _last_refresh_time = current_time
        logger.info("Token refresh successful, next refresh in 30 minutes")
    else:
        # Even on failure, update the timestamp to avoid hammering the API
        # We'll retry on the next 30-min interval
        _last_refresh_time = current_time
        logger.warning("Token refresh failed, will retry in 30 minutes")

    return True
