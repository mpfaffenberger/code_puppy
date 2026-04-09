"""Utility functions for the Azure AI Foundry plugin.

This module provides helper functions for configuration management,
environment variable resolution, and model configuration.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from .config import (
    DEFAULT_CONTEXT_LENGTHS,
    ENV_FOUNDRY_RESOURCE,
    get_extra_models_path,
)

logger = logging.getLogger(__name__)


def resolve_env_var(value: str) -> str:
    """Resolve a value that may contain an environment variable reference.

    If the value starts with '$', it's treated as an environment variable
    reference and resolved. Otherwise, the value is returned as-is.

    Args:
        value: The value to resolve, possibly starting with '$'.

    Returns:
        The resolved value.

    Example:
        >>> os.environ["MY_VAR"] = "test"
        >>> resolve_env_var("$MY_VAR")
        'test'
        >>> resolve_env_var("literal")
        'literal'
    """
    if value and value.startswith("$"):
        env_var = value[1:]
        resolved = os.environ.get(env_var)
        if resolved is None:
            logger.warning(f"Environment variable '{env_var}' not set")
            return ""
        return resolved
    return value


def load_extra_models() -> Dict[str, Any]:
    """Load the extra_models.json configuration file.

    Returns:
        Dictionary containing model configurations, or empty dict if file
        doesn't exist or is invalid.
    """
    extra_models_path = get_extra_models_path()
    if not extra_models_path.exists():
        return {}

    try:
        with open(extra_models_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in extra_models.json: {e}")
        return {}
    except Exception as e:
        logger.error(f"Error loading extra_models.json: {e}")
        return {}


def save_extra_models(models: Dict[str, Any]) -> bool:
    """Save model configurations to extra_models.json.

    Args:
        models: Dictionary of model configurations to save.

    Returns:
        True if save succeeded, False otherwise.
    """
    extra_models_path = get_extra_models_path()

    try:
        # Ensure directory exists
        extra_models_path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write using temp file
        temp_path = extra_models_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(models, f, indent=2, ensure_ascii=False)
        temp_path.replace(extra_models_path)

        logger.info(f"Saved {len(models)} models to extra_models.json")
        return True

    except Exception as e:
        logger.error(f"Error saving extra_models.json: {e}")
        return False


def build_foundry_model_config(
    deployment_name: str,
    model_tier: str,
    foundry_resource: Optional[str] = None,
    context_length: Optional[int] = None,
) -> Dict[str, Any]:
    """Build a Code Puppy model configuration for an Azure Foundry deployment.

    Args:
        deployment_name: The deployment name in Azure Foundry.
        model_tier: One of "opus", "sonnet", or "haiku".
        foundry_resource: The Foundry resource name. If None, uses env var reference.
        context_length: Override for context length. If None, uses default for tier.

    Returns:
        Dictionary containing the model configuration.
    """
    if context_length is None:
        context_length = DEFAULT_CONTEXT_LENGTHS.get(model_tier.lower(), 200000)

    resource_value = foundry_resource if foundry_resource else f"${ENV_FOUNDRY_RESOURCE}"

    return {
        "type": "azure_foundry",
        "provider": "azure_foundry",
        "name": deployment_name,
        "foundry_resource": resource_value,
        "context_length": context_length,
        "supported_settings": ["temperature", "extended_thinking", "budget_tokens"],
    }


def add_foundry_models_to_config(
    resource_name: str,
    opus_deployment: Optional[str] = None,
    sonnet_deployment: Optional[str] = None,
    haiku_deployment: Optional[str] = None,
) -> List[str]:
    """Add Azure Foundry model configurations to extra_models.json.

    Args:
        resource_name: The Azure Foundry resource name.
        opus_deployment: Deployment name for Opus model (optional).
        sonnet_deployment: Deployment name for Sonnet model (optional).
        haiku_deployment: Deployment name for Haiku model (optional).

    Returns:
        List of model keys that were added.
    """
    models = load_extra_models()
    added_models: List[str] = []

    deployments = [
        ("opus", opus_deployment, "foundry-claude-opus"),
        ("sonnet", sonnet_deployment, "foundry-claude-sonnet"),
        ("haiku", haiku_deployment, "foundry-claude-haiku"),
    ]

    for tier, deployment, model_key in deployments:
        if deployment:
            # Check for 1M context indicator in deployment name
            context_length = None
            if "[1m]" in deployment.lower() or "1m" in deployment.lower():
                context_length = 1000000

            config = build_foundry_model_config(
                deployment_name=deployment,
                model_tier=tier,
                foundry_resource=resource_name,
                context_length=context_length,
            )
            models[model_key] = config
            added_models.append(model_key)

    if added_models and save_extra_models(models):
        return added_models

    return []


def remove_foundry_models_from_config() -> List[str]:
    """Remove all Azure Foundry model configurations from extra_models.json.

    Returns:
        List of model keys that were removed.
    """
    models = load_extra_models()
    removed_models: List[str] = []

    keys_to_remove = [
        key for key, config in models.items()
        if isinstance(config, dict) and config.get("type") == "azure_foundry"
    ]

    for key in keys_to_remove:
        del models[key]
        removed_models.append(key)

    if removed_models:
        save_extra_models(models)

    return removed_models


def get_foundry_models_from_config() -> Dict[str, Any]:
    """Get all Azure Foundry model configurations from extra_models.json.

    Returns:
        Dictionary of model key -> config for all Foundry models.
    """
    models = load_extra_models()
    return {
        key: config for key, config in models.items()
        if isinstance(config, dict) and config.get("type") == "azure_foundry"
    }
