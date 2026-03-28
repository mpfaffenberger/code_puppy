"""Configuration for the GitHub Models OAuth plugin."""

from pathlib import Path
from typing import Any, Dict

from code_puppy import config

# GitHub Models OAuth configuration
GITHUB_MODELS_OAUTH_CONFIG: Dict[str, Any] = {
    # GitHub OAuth Device Flow endpoints
    "device_code_url": "https://github.com/login/device/code",
    "access_token_url": "https://github.com/login/oauth/access_token",
    "user_api_url": "https://api.github.com/user",
    # GitHub Models Inference API (OpenAI-compatible)
    "api_base_url": "https://models.github.ai/inference",
    "api_version": "2026-03-10",
    # GitHub Copilot API (OpenAI-compatible, has Claude/Gemini)
    "copilot_api_base_url": "https://api.githubcopilot.com",
    "copilot_integration_id": "vscode-chat",
    "copilot_prefix": "copilot-",
    # OAuth configuration — client_id from a registered GitHub OAuth App
    # with device flow enabled.  Set via GITHUB_MODELS_CLIENT_ID env var.
    # No default — users must register their own app or use `gh` CLI auth.
    "default_client_id": "",
    "client_id_env_var": "GITHUB_MODELS_CLIENT_ID",
    "scope": "read:user",
    # Device flow polling
    "poll_timeout": 900,  # 15 minutes (matches GitHub's device_code expiry)
    # Model configuration
    "prefix": "github-",
    "default_context_length": 200000,
    # User-Agent for API calls
    "user_agent": "code-puppy/github-models-oauth",
}


def get_client_id() -> str:
    """Get the GitHub OAuth App client ID.

    Checks the environment variable first, then falls back to the default.
    """
    import os

    return os.environ.get(
        GITHUB_MODELS_OAUTH_CONFIG["client_id_env_var"],
        GITHUB_MODELS_OAUTH_CONFIG["default_client_id"],
    )


def get_token_storage_path() -> Path:
    """Get the path for storing GitHub OAuth tokens."""
    data_dir = Path(config.DATA_DIR)
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    return data_dir / "github_models_oauth.json"


def get_github_models_path() -> Path:
    """Get the path to the github_models.json model config file."""
    data_dir = Path(config.DATA_DIR)
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    return data_dir / "github_models.json"
