"""Configuration constants for the GitHub Copilot auth plugin."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from code_puppy import config

# GitHub Copilot auth configuration
COPILOT_AUTH_CONFIG: Dict[str, Any] = {
    # Copilot session-token endpoints
    "github_token_url": "https://api.github.com/copilot_internal/v2/token",
    # GHE template: replace {host}
    "ghe_token_url_template": "https://{host}/api/v3/copilot_internal/v2/token",
    # OpenAI-compatible Copilot chat API (default; overridden per-host at runtime)
    "api_base_url": "https://api.githubcopilot.com",
    # Model prefix in Code Puppy
    "prefix": "copilot-",
    "default_context_length": 128000,
    # Headers expected by the Copilot API
    "editor_version": "JetBrains-IU/2024.3",
    "editor_plugin_version": "copilot/2.0.0",
    "copilot_integration_id": "vscode-chat",
    "openai_intent": "conversation-panel",
}

# GitHub Device Flow configuration — browser-based auth with no IDE required.
# Uses the VS Code Copilot extension's public client ID which supports Device Flow.
DEVICE_FLOW_CONFIG: Dict[str, Any] = {
    "client_id": "Iv1.b507a08c87ecfe98",
    "scope": "read:user",
    # Endpoint templates — {host} is replaced at runtime
    "device_code_url": "https://{host}/login/device/code",
    "access_token_url": "https://{host}/login/oauth/access_token",
    # Polling defaults (server may override via response)
    "default_poll_interval": 5,
    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
}

# Models known to be available via Copilot (costs are $0 via Copilot).
# The /copilot-login flow will also try to fetch the live model list.
DEFAULT_COPILOT_MODELS = [
    "gpt-4o",
    "gpt-4.1",
    "gpt-4.1-mini",
    "o4-mini",
    "o3",
    "claude-opus-4.6",
    "claude-opus-4",
    "claude-sonnet-4",
    "claude-sonnet-4.5",
    "claude-haiku-4.5",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
]

# Per-model context-length overrides (tokens).
COPILOT_MODEL_CONTEXT_LENGTHS: Dict[str, int] = {
    "gpt-4o": 64000,
    "gpt-4.1": 128000,
    "gpt-4.1-mini": 128000,
    "o4-mini": 128000,
    "o3": 128000,
    "claude-opus-4.6": 200000,
    "claude-opus-4": 200000,
    "claude-sonnet-4": 128000,
    "claude-sonnet-4.5": 128000,
    "claude-haiku-4.5": 128000,
    "gemini-2.5-pro": 128000,
    "gemini-2.5-flash": 128000,
}



def get_copilot_models_path() -> Path:
    """Return path for persisted copilot_models.json (XDG_DATA_HOME)."""
    data_dir = Path(config.DATA_DIR)
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    return data_dir / "copilot_models.json"


def get_session_cache_path() -> Path:
    """Return path for caching the short-lived Copilot session token."""
    data_dir = Path(config.DATA_DIR)
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    return data_dir / "copilot_session.json"


def get_device_token_storage_path() -> Path:
    """Return path for storing tokens obtained via the GitHub Device Flow."""
    data_dir = Path(config.DATA_DIR)
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    return data_dir / "copilot_device_tokens.json"

