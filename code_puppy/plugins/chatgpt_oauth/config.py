from pathlib import Path
from typing import Any, Dict

from code_puppy import config

# ChatGPT OAuth configuration based on OpenAI's Codex CLI flow
CHATGPT_OAUTH_CONFIG: Dict[str, Any] = {
    # OAuth endpoints from OpenAI auth service
    "issuer": "https://auth.openai.com",
    "auth_url": "https://auth.openai.com/oauth/authorize",
    "token_url": "https://auth.openai.com/oauth/token",
    # API endpoints - Codex uses chatgpt.com backend, not api.openai.com
    "api_base_url": "https://chatgpt.com/backend-api/codex",
    # OAuth client configuration for Code Puppy
    "client_id": "app_EMoamEEZ73f0CkXaXp7hrann",
    "scope": "openid profile email offline_access",
    # Callback handling (we host a localhost callback to capture the redirect)
    "redirect_host": "http://localhost",
    "redirect_path": "auth/callback",
    "required_port": 1455,
    "callback_timeout": 120,
    # Local configuration (uses XDG_DATA_HOME)
    "token_storage": None,  # Set dynamically in get_token_storage_path()
    # Model configuration
    "prefix": "chatgpt-",
    "default_context_length": 272000,
    "api_key_env_var": "CHATGPT_OAUTH_API_KEY",
    # Codex CLI version info (for User-Agent header)
    "client_version": "0.72.0",
    "originator": "codex_cli_rs",
}


def get_token_storage_path() -> Path:
    """Get the path for storing OAuth tokens (uses XDG_DATA_HOME)."""
    data_dir = Path(config.DATA_DIR)
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    return data_dir / "chatgpt_oauth.json"


def get_config_dir() -> Path:
    """Get the Code Puppy configuration directory (uses XDG_CONFIG_HOME)."""
    config_dir = Path(config.CONFIG_DIR)
    config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    return config_dir


def get_chatgpt_models_path() -> Path:
    """Get the path to the dedicated chatgpt_models.json file (uses XDG_DATA_HOME)."""
    data_dir = Path(config.DATA_DIR)
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    return data_dir / "chatgpt_models.json"
