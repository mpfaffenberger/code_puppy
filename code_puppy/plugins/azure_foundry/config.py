"""Configuration constants for the Azure AI Foundry plugin.

This module defines constants used throughout the plugin for Azure AD
authentication and model configuration.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from code_puppy.config import DATA_DIR

# Azure AD scope for Cognitive Services (used for token acquisition)
# This scope is required for authenticating with Azure AI Foundry
AZURE_COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"

# Token refresh buffer in seconds (refresh 5 minutes before expiry)
TOKEN_REFRESH_BUFFER = 300

# Default context lengths for different model tiers
DEFAULT_CONTEXT_LENGTHS: dict[str, int] = {
    "opus": 1000000,  # 1M tokens for Opus models
    "sonnet": 1000000,  # 1M tokens for Sonnet models
    "haiku": 200000,  # 200K tokens for Haiku models
}

# Context lengths for OpenAI models (Azure doesn't expose this in the catalog API).
# Prefixes are matched longest-first against the model name.
OPENAI_CONTEXT_LENGTHS: dict[str, int] = {
    "gpt-5.4": 1000000,
    "gpt-5.4-mini": 1000000,
    "gpt-5.3-codex": 1000000,
    "gpt-5.3": 1000000,
    "gpt-5.2-codex": 1000000,
    "gpt-5.2": 1000000,
    "gpt-5.1-codex-max": 1000000,
    "gpt-5.1-codex-mini": 1000000,
    "gpt-5.1-codex": 1000000,
    "gpt-5.1": 1000000,
    "gpt-5-codex": 1000000,
    "gpt-5": 1000000,
    "gpt-4.1": 1000000,
    "gpt-4.1-mini": 1000000,
    "gpt-4.1-nano": 1000000,
    "o4-mini": 200000,
    "o3": 200000,
    "o3-mini": 200000,
    "o1": 200000,
    "o1-mini": 128000,
    "codex-mini": 200000,
}
DEFAULT_OPENAI_CONTEXT_LENGTH = 128000


def get_openai_context_length(model_name: str) -> int:
    """Look up the context length for an OpenAI model by name.

    Matches the longest prefix first so 'gpt-5.4-mini' matches before 'gpt-5.4'.
    Falls back to DEFAULT_OPENAI_CONTEXT_LENGTH if no match.
    """
    for prefix in sorted(OPENAI_CONTEXT_LENGTHS, key=len, reverse=True):
        if model_name.startswith(prefix):
            return OPENAI_CONTEXT_LENGTHS[prefix]
    return DEFAULT_OPENAI_CONTEXT_LENGTH


# Default deployment name patterns (can be overridden by user)
DEFAULT_DEPLOYMENT_NAMES: dict[str, str] = {
    "opus": "claude-opus-4-6",
    "sonnet": "claude-sonnet-4-6",
    "haiku": "claude-haiku-4-5",
}

# Environment variable names
ENV_FOUNDRY_RESOURCE = "ANTHROPIC_FOUNDRY_RESOURCE"
ENV_FOUNDRY_BASE_URL = "ANTHROPIC_FOUNDRY_BASE_URL"


def get_foundry_resource() -> str | None:
    """Get the Azure Foundry resource name from environment.

    Returns:
        The resource name if set, None otherwise.
    """
    return os.environ.get(ENV_FOUNDRY_RESOURCE)


def get_foundry_base_url() -> str | None:
    """Get the Azure Foundry base URL from environment.

    If ANTHROPIC_FOUNDRY_BASE_URL is set, use it directly.
    Otherwise, construct from ANTHROPIC_FOUNDRY_RESOURCE.

    Returns:
        The base URL if determinable, None otherwise.
    """
    base_url = os.environ.get(ENV_FOUNDRY_BASE_URL)
    if base_url:
        return base_url

    resource = get_foundry_resource()
    if resource:
        return f"https://{resource}.services.ai.azure.com/anthropic/v1"

    return None


def get_extra_models_path() -> Path:
    """Get the path to the extra_models.json file.

    Returns:
        Path to the extra models configuration file.
    """
    return Path(DATA_DIR) / "extra_models.json"


# Plugin configuration for model creation
AZURE_FOUNDRY_CONFIG: dict[str, Any] = {
    "scope": AZURE_COGNITIVE_SCOPE,
    "token_refresh_buffer": TOKEN_REFRESH_BUFFER,
}

# Note: supported_settings is determined per-tier in build_foundry_model_config():
# - Opus 4.6: ["temperature", "extended_thinking", "effort"]
# - Sonnet/Haiku: ["temperature", "interleaved_thinking", "thinking_budget"]
