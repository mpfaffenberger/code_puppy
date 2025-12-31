"""Utility helpers for the Antigravity OAuth plugin."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from .config import (
    ANTIGRAVITY_OAUTH_CONFIG,
    get_antigravity_models_path,
    get_token_storage_path,
)
from .constants import ANTIGRAVITY_ENDPOINT, ANTIGRAVITY_HEADERS, ANTIGRAVITY_MODELS

logger = logging.getLogger(__name__)


def load_stored_tokens() -> Optional[Dict[str, Any]]:
    """Load stored OAuth tokens from disk."""
    try:
        token_path = get_token_storage_path()
        if token_path.exists():
            with open(token_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.error("Failed to load tokens: %s", e)
    return None


def save_tokens(tokens: Dict[str, Any]) -> bool:
    """Save OAuth tokens to disk."""
    try:
        token_path = get_token_storage_path()
        with open(token_path, "w", encoding="utf-8") as f:
            json.dump(tokens, f, indent=2)
        token_path.chmod(0o600)
        return True
    except Exception as e:
        logger.error("Failed to save tokens: %s", e)
        return False


def load_antigravity_models() -> Dict[str, Any]:
    """Load configured Antigravity models from disk."""
    try:
        models_path = get_antigravity_models_path()
        if models_path.exists():
            with open(models_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.error("Failed to load Antigravity models: %s", e)
    return {}


def save_antigravity_models(models: Dict[str, Any]) -> bool:
    """Save Antigravity models configuration to disk."""
    try:
        models_path = get_antigravity_models_path()
        with open(models_path, "w", encoding="utf-8") as f:
            json.dump(models, f, indent=2)
        return True
    except Exception as e:
        logger.error("Failed to save Antigravity models: %s", e)
        return False


def add_models_to_config(access_token: str, project_id: str = "") -> bool:
    """Add all available Antigravity models to the configuration."""
    try:
        models_config: Dict[str, Any] = {}
        prefix = ANTIGRAVITY_OAUTH_CONFIG["prefix"]

        for model_id, model_info in ANTIGRAVITY_MODELS.items():
            prefixed_name = f"{prefix}{model_id}"

            # Build custom headers
            headers = dict(ANTIGRAVITY_HEADERS)

            # Use custom_gemini type with Antigravity transport
            models_config[prefixed_name] = {
                "type": "custom_gemini",
                "name": model_id,
                "custom_endpoint": {
                    "url": ANTIGRAVITY_ENDPOINT,
                    "api_key": access_token,
                    "headers": headers,
                },
                "project_id": project_id,
                "context_length": model_info.get("context_length", 200000),
                "family": model_info.get("family", "other"),
                "oauth_source": "antigravity-plugin",
                "antigravity": True,  # Flag to use Antigravity transport
            }

            # Add thinking budget if present
            if model_info.get("thinking_budget"):
                models_config[prefixed_name]["thinking_budget"] = model_info[
                    "thinking_budget"
                ]

        if save_antigravity_models(models_config):
            logger.info("Added %d Antigravity models", len(models_config))
            return True

    except Exception as e:
        logger.error("Error adding models to config: %s", e)
    return False


def remove_antigravity_models() -> int:
    """Remove all Antigravity models from configuration."""
    try:
        models = load_antigravity_models()
        to_remove = [
            name
            for name, config in models.items()
            if config.get("oauth_source") == "antigravity-plugin"
        ]

        if not to_remove:
            return 0

        for model_name in to_remove:
            models.pop(model_name, None)

        if save_antigravity_models(models):
            return len(to_remove)
    except Exception as e:
        logger.error("Error removing Antigravity models: %s", e)
    return 0


def get_model_families_summary() -> Dict[str, List[str]]:
    """Get a summary of available models by family."""
    families: Dict[str, List[str]] = {
        "gemini": [],
        "claude": [],
        "other": [],
    }

    for model_id, info in ANTIGRAVITY_MODELS.items():
        family = info.get("family", "other")
        if family in families:
            families[family].append(model_id)

    return families


def reload_current_agent() -> None:
    """Reload the current agent so new auth tokens are picked up immediately."""
    try:
        from code_puppy.agents import get_current_agent

        current_agent = get_current_agent()
        if current_agent is None:
            logger.debug("No current agent to reload")
            return

        if hasattr(current_agent, "refresh_config"):
            try:
                current_agent.refresh_config()
            except Exception:
                pass

        current_agent.reload_code_generation_agent()
        logger.info("Active agent reloaded with new authentication")
    except Exception as e:
        logger.warning("Agent reload failed: %s", e)
