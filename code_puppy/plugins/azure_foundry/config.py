"""Configuration constants for the Azure AI Foundry plugin.

This module defines constants used throughout the plugin for Azure AD
authentication and model configuration.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from code_puppy.config import DATA_DIR

# Azure AD scope for Cognitive Services (used for token acquisition)
# This scope is required for authenticating with Azure AI Foundry
AZURE_COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"

# Token refresh buffer in seconds (refresh 5 minutes before expiry)
TOKEN_REFRESH_BUFFER = 300

# Default context lengths for different model tiers
DEFAULT_CONTEXT_LENGTHS: Dict[str, int] = {
    "opus": 1000000,    # 1M tokens for Opus models
    "sonnet": 1000000,  # 1M tokens for Sonnet models
    "haiku": 200000,    # 200K tokens for Haiku models
}

# Default deployment name patterns (can be overridden by user)
DEFAULT_DEPLOYMENT_NAMES: Dict[str, str] = {
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
AZURE_FOUNDRY_CONFIG: Dict[str, Any] = {
    "scope": AZURE_COGNITIVE_SCOPE,
    "token_refresh_buffer": TOKEN_REFRESH_BUFFER,
    "supported_settings": ["temperature", "extended_thinking", "budget_tokens"],
}
