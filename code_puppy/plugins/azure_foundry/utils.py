"""Utility functions for the Azure AI Foundry plugin.

This module provides helper functions for configuration management,
environment variable resolution, and model configuration.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from .config import (
    DEFAULT_CONTEXT_LENGTHS,
    ENV_FOUNDRY_RESOURCE,
    get_extra_models_path,
    get_openai_context_length,
)

logger = logging.getLogger(__name__)

# Context window suffix pattern: [<number><unit>] where unit is k or m (case-insensitive)
# Examples: [200k], [500k], [1m], [2m]
_CONTEXT_SUFFIX_PATTERN = re.compile(r"\[(\d+)([km])\]", re.IGNORECASE)

# Multipliers for context window units
_CONTEXT_MULTIPLIERS = {
    "k": 1_000,
    "m": 1_000_000,
}


def parse_context_window_suffix(name: str) -> tuple[str, int | None]:
    """Parse and extract context window suffix from a model/deployment name.

    Supports Claude Code format: [<number><unit>] where unit is 'k' (thousands)
    or 'm' (millions). Examples: [200k], [500k], [1m], [2m]

    Args:
        name: The model or deployment name, possibly with context suffix.
              e.g., "it-entra-claude-opus-4-6[1m]"

    Returns:
        A tuple of (stripped_name, context_length):
        - stripped_name: The name with the suffix removed
        - context_length: The parsed context length in tokens, or None if no suffix

    Examples:
        >>> parse_context_window_suffix("claude-opus-4-6[1m]")
        ('claude-opus-4-6', 1000000)
        >>> parse_context_window_suffix("claude-sonnet[200k]")
        ('claude-sonnet', 200000)
        >>> parse_context_window_suffix("claude-haiku-4-5")
        ('claude-haiku-4-5', None)
    """
    match = _CONTEXT_SUFFIX_PATTERN.search(name)
    if not match:
        return name, None

    number = int(match.group(1))
    unit = match.group(2).lower()
    multiplier = _CONTEXT_MULTIPLIERS[unit]
    context_length = number * multiplier

    # Remove the suffix from the name
    stripped_name = _CONTEXT_SUFFIX_PATTERN.sub("", name).strip()

    return stripped_name, context_length


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


def load_extra_models() -> dict[str, Any]:
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


def save_extra_models(models: dict[str, Any]) -> bool:
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
    foundry_resource: str | None = None,
    context_length: int | None = None,
) -> dict[str, Any]:
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

    resource_value = (
        foundry_resource if foundry_resource else f"${ENV_FOUNDRY_RESOURCE}"
    )

    # All Anthropic models need extended_thinking + budget_tokens for the
    # request body, plus interleaved_thinking for the beta header.
    # Opus additionally supports effort (hand-in-hand with adaptive thinking).
    supported_settings = [
        "temperature",
        "extended_thinking",
        "budget_tokens",
        "interleaved_thinking",
    ]
    if model_tier.lower() == "opus":
        supported_settings.append("effort")

    return {
        "type": "azure_foundry",
        "provider": "azure_foundry",
        "name": deployment_name,
        "foundry_resource": resource_value,
        "context_length": context_length,
        "supported_settings": supported_settings,
    }


def add_foundry_models_to_config(
    resource_name: str,
    opus_deployment: str | None = None,
    sonnet_deployment: str | None = None,
    haiku_deployment: str | None = None,
) -> list[str]:
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
    added_models: list[str] = []

    deployments = [
        ("opus", opus_deployment, "foundry-claude-opus"),
        ("sonnet", sonnet_deployment, "foundry-claude-sonnet"),
        ("haiku", haiku_deployment, "foundry-claude-haiku"),
    ]

    for tier, deployment, model_key in deployments:
        if deployment:
            # Parse context window suffix (Claude Code format: [200k], [1m], etc.)
            actual_deployment, context_length = parse_context_window_suffix(deployment)

            config = build_foundry_model_config(
                deployment_name=actual_deployment,
                model_tier=tier,
                foundry_resource=resource_name,
                context_length=context_length,
            )
            models[model_key] = config
            added_models.append(model_key)

    if added_models and save_extra_models(models):
        return added_models

    return []


FOUNDRY_TYPES = {"azure_foundry", "azure_foundry_openai"}


_GPT5_SUPPORTED_SETTINGS = [
    "reasoning_effort",
    "summary",
    "verbosity",
]


def get_foundry_openai_supported_settings(model_name: str) -> list[str]:
    """Return supported settings for an Azure Foundry OpenAI model.

    Later GPT-5-family models support Code Puppy's reasoning/summary/verbosity
    controls in addition to the baseline temperature setting.
    """
    supported_settings = ["temperature"]
    if model_name.startswith("gpt-5"):
        supported_settings.extend(_GPT5_SUPPORTED_SETTINGS)
    return supported_settings


def add_discovered_models_to_config(
    resource_name: str,
    deployments: list,
) -> list[str]:
    """Add auto-discovered deployments to extra_models.json.

    Classifies each deployment by model format (Anthropic vs OpenAI)
    and creates the appropriate model config.
    """
    from .discovery import AzureDeployment

    models = load_extra_models()
    added: list[str] = []

    for d in deployments:
        if not isinstance(d, AzureDeployment):
            continue

        key = f"foundry-{d.name}"

        if d.model_format == "Anthropic":
            tier = "haiku"
            for t in ("opus", "sonnet"):
                if t in d.model_name.lower():
                    tier = t
                    break
            models[key] = build_foundry_model_config(
                deployment_name=d.name,
                model_tier=tier,
                foundry_resource=resource_name,
            )
            added.append(key)

        elif d.model_format == "OpenAI":
            models[key] = {
                "type": "azure_foundry_openai",
                "provider": "azure_foundry_openai",
                "name": d.name,
                "foundry_resource": resource_name,
                "context_length": get_openai_context_length(d.model_name),
                "supported_settings": get_foundry_openai_supported_settings(
                    d.model_name
                ),
            }
            added.append(key)

    if added and save_extra_models(models):
        return added
    return []


def remove_foundry_models_from_config() -> list[str]:
    """Remove all Azure Foundry model configurations from extra_models.json."""
    models = load_extra_models()
    removed_models: list[str] = []

    keys_to_remove = [
        key
        for key, config in models.items()
        if isinstance(config, dict) and config.get("type") in FOUNDRY_TYPES
    ]

    for key in keys_to_remove:
        del models[key]
        removed_models.append(key)

    if removed_models:
        if not save_extra_models(models):
            logger.error("Failed to persist model removal")
            return []

    return removed_models


def get_foundry_models_from_config() -> dict[str, Any]:
    """Get all Azure Foundry model configurations from extra_models.json."""
    models = load_extra_models()
    return {
        key: config
        for key, config in models.items()
        if isinstance(config, dict) and config.get("type") in FOUNDRY_TYPES
    }
