"""Utility helpers for the GitHub Models OAuth plugin."""

from __future__ import annotations

import getpass
import json
import logging
import os
import subprocess
from typing import Any, Dict, List, Optional

import requests

from .config import (
    GITHUB_MODELS_OAUTH_CONFIG,
    get_github_models_path,
    get_token_storage_path,
)

logger = logging.getLogger(__name__)


def get_gh_cli_token() -> Optional[str]:
    """Get a GitHub token from the ``gh`` CLI if installed and authenticated."""
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except FileNotFoundError:
        logger.debug("gh CLI not found in PATH")
    except Exception as exc:
        logger.debug("Failed to get gh CLI token: %s", exc)
    return None


def get_env_token() -> Optional[str]:
    """Get a GitHub token from ``GITHUB_TOKEN`` or ``GH_TOKEN``."""
    for var in ("GITHUB_TOKEN", "GH_TOKEN"):
        token = os.environ.get(var, "").strip()
        if token:
            return token
    return None


def prompt_for_token() -> Optional[str]:
    """Prompt the user to paste a GitHub PAT (hidden input via ``getpass``)."""
    from code_puppy.command_line.utils import _reset_windows_console
    from code_puppy.messaging import emit_info

    emit_info(
        "🔑 Create a Personal Access Token at:\n"
        "   https://github.com/settings/tokens\n"
        "   Fine-grained PAT with 'models:read' permission recommended.\n"
        "   Classic PATs also work without specific scopes."
    )
    try:
        _reset_windows_console()
        token = getpass.getpass("Paste your GitHub token (hidden) or press Enter to skip: ")
        if token and len(token) >= 4:
            return token.strip()
    except (EOFError, KeyboardInterrupt):
        pass
    return None


# Fallback model lists used when the catalog/API is unreachable.
DEFAULT_GITHUB_MODELS: List[str] = [
    "openai/gpt-5.4",
    "openai/gpt-5.4-mini",
    "openai/gpt-4.1",
    "openai/gpt-4.1-mini",
    "openai/gpt-4.1-nano",
    "openai/o3",
    "openai/o4-mini",
    "meta/llama-4-scout-17b-16e-instruct",
    "meta/llama-4-maverick-17b-128e-instruct-fp8",
    "mistral-ai/mistral-medium-2505",
    "deepseek/deepseek-r1",
    "deepseek/deepseek-v3-0324",
    "xai/grok-3",
]

DEFAULT_COPILOT_MODELS: List[str] = [
    "claude-sonnet-4.6",
    "claude-opus-4.6",
    "claude-haiku-4.5",
    "gpt-5.4",
    "gemini-3-pro",
    "gemini-3-flash-preview",
]


def save_tokens(tokens: Dict[str, Any]) -> bool:
    """Save OAuth tokens to disk with restrictive permissions."""
    if tokens is None:
        raise TypeError("tokens cannot be None")
    try:
        token_path = get_token_storage_path()
        with open(token_path, "w", encoding="utf-8") as fh:
            json.dump(tokens, fh, indent=2)
        token_path.chmod(0o600)
        return True
    except Exception as exc:
        logger.error("Failed to save GitHub tokens: %s", exc)
    return False


def load_stored_tokens() -> Optional[Dict[str, Any]]:
    """Load previously stored OAuth tokens from disk."""
    try:
        token_path = get_token_storage_path()
        if token_path.exists():
            with open(token_path, "r", encoding="utf-8") as fh:
                return json.load(fh)
    except Exception as exc:
        logger.error("Failed to load GitHub tokens: %s", exc)
    return None


def get_github_username(access_token: str) -> Optional[str]:
    """Fetch the authenticated user's GitHub login."""
    try:
        response = requests.get(
            GITHUB_MODELS_OAUTH_CONFIG["user_api_url"],
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "User-Agent": GITHUB_MODELS_OAUTH_CONFIG["user_agent"],
            },
            timeout=15,
        )
        if response.status_code == 200:
            return response.json().get("login")
    except Exception as exc:
        logger.warning("Failed to fetch GitHub user: %s", exc)
    return None


def _parse_model_list(data: Any) -> List[str]:
    """Extract model IDs from a catalog or API response."""
    items = data if isinstance(data, list) else data.get("models", data.get("data", []))
    models: List[str] = []
    for item in items:
        if isinstance(item, str):
            models.append(item)
        elif isinstance(item, dict):
            mid = item.get("id") or item.get("name") or item.get("model")
            if mid and "embedding" not in mid and "accounts/" not in mid:
                models.append(mid)
    return models


def fetch_github_models(access_token: str) -> List[str]:
    """Fetch models from the GitHub Models catalog, falling back to defaults."""
    from code_puppy.messaging import emit_info, emit_warning

    catalog_url = (
        GITHUB_MODELS_OAUTH_CONFIG["api_base_url"].rstrip("/").replace("/inference", "")
        + "/catalog/models"
    )
    try:
        response = requests.get(
            catalog_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "User-Agent": GITHUB_MODELS_OAUTH_CONFIG["user_agent"],
            },
            timeout=30,
        )
        if response.status_code in (401, 403):
            emit_warning(
                f"   Catalog returned HTTP {response.status_code} — token lacks access.\n"
                "   💡 Fine-grained PATs need 'models:read' permission.\n"
                "   Skipping GitHub Models registration."
            )
            return []
        if response.status_code == 200:
            models = _parse_model_list(response.json())
            if models:
                emit_info(f"   📡 Fetched {len(models)} models from GitHub catalog")
                return models
        emit_warning(
            f"   Catalog returned HTTP {response.status_code}; using {len(DEFAULT_GITHUB_MODELS)} built-in models.\n"
            "   💡 For the full list, use a PAT or re-run: gh auth login -s read:user"
        )
    except Exception as exc:
        logger.warning("Error fetching GitHub Models catalog: %s", exc)
        emit_warning(f"   Catalog unavailable; using {len(DEFAULT_GITHUB_MODELS)} built-in models")

    return list(DEFAULT_GITHUB_MODELS)


def fetch_copilot_models(access_token: str) -> List[str]:
    """Fetch models from the GitHub Copilot API, falling back to defaults."""
    from code_puppy.messaging import emit_info, emit_warning

    copilot_url = GITHUB_MODELS_OAUTH_CONFIG["copilot_api_base_url"]
    try:
        response = requests.get(
            f"{copilot_url}/models",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Copilot-Integration-Id": GITHUB_MODELS_OAUTH_CONFIG["copilot_integration_id"],
                "User-Agent": GITHUB_MODELS_OAUTH_CONFIG["user_agent"],
            },
            timeout=30,
        )
        if response.status_code in (401, 403):
            emit_warning(
                f"   Copilot API returned HTTP {response.status_code} — token lacks access.\n"
                "   Skipping Copilot models registration."
            )
            return []
        if response.status_code == 200:
            models = _parse_model_list(response.json())
            if models:
                emit_info(f"   📡 Fetched {len(models)} models from Copilot API")
                return models
        emit_warning(f"   Copilot API returned HTTP {response.status_code}; using {len(DEFAULT_COPILOT_MODELS)} built-in models")
    except Exception as exc:
        logger.warning("Error fetching Copilot models: %s", exc)
        emit_warning(f"   Copilot API unavailable; using {len(DEFAULT_COPILOT_MODELS)} built-in models")

    return list(DEFAULT_COPILOT_MODELS)


def add_models_to_config(model_ids: List[str]) -> bool:
    """Register GitHub Models (``github-`` prefix, ``github_models`` type)."""
    return _add_models_to_config(
        model_ids,
        model_type="github_models",
        prefix=GITHUB_MODELS_OAUTH_CONFIG["prefix"],
        base_url=GITHUB_MODELS_OAUTH_CONFIG["api_base_url"],
    )


def add_copilot_models_to_config(model_ids: List[str]) -> bool:
    """Register Copilot API models (``copilot-`` prefix, ``github_copilot`` type)."""
    return _add_models_to_config(
        model_ids,
        model_type="github_copilot",
        prefix=GITHUB_MODELS_OAUTH_CONFIG["copilot_prefix"],
        base_url=GITHUB_MODELS_OAUTH_CONFIG["copilot_api_base_url"],
    )


def _add_models_to_config(
    model_ids: List[str], *, model_type: str, prefix: str, base_url: str,
) -> bool:
    """Register models in the local config file with the given type and prefix."""
    default_ctx = GITHUB_MODELS_OAUTH_CONFIG["default_context_length"]
    try:
        config = load_github_models_config()
        for model_id in model_ids:
            config[f"{prefix}{model_id.replace('/', '-')}"] = {
                "type": model_type,
                "name": model_id,
                "custom_endpoint": {"url": base_url},
                "context_length": default_ctx,
                "oauth_source": "github-models-plugin",
                "supported_settings": ["temperature", "top_p"],
            }
        if save_github_models_config(config):
            return True
    except Exception as exc:
        logger.error("Error adding %s models to config: %s", model_type, exc)
    return False


def load_github_models_config() -> Dict[str, Any]:
    """Load model configurations from the github_models.json file."""
    try:
        models_path = get_github_models_path()
        if models_path.exists():
            with open(models_path, "r", encoding="utf-8") as fh:
                return json.load(fh)
    except Exception as exc:
        logger.error("Failed to load GitHub models config: %s", exc)
    return {}


def save_github_models_config(models: Dict[str, Any]) -> bool:
    """Save model configurations to disk."""
    try:
        models_path = get_github_models_path()
        with open(models_path, "w", encoding="utf-8") as fh:
            json.dump(models, fh, indent=2)
        return True
    except Exception as exc:
        logger.error("Failed to save GitHub models config: %s", exc)
    return False


def remove_github_models() -> int:
    """Remove all GitHub Models OAuth models from configuration."""
    try:
        config = load_github_models_config()
        to_remove = [
            name for name, cfg in config.items()
            if cfg.get("oauth_source") == "github-models-plugin"
        ]
        for name in to_remove:
            config.pop(name, None)
        if save_github_models_config(config):
            return len(to_remove)
    except Exception as exc:
        logger.error("Error removing GitHub models: %s", exc)
    return 0
