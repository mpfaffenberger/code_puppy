from pathlib import Path
from typing import Any, Dict

# ChatGPT OAuth configuration based on OpenAI's Codex CLI flow
CHATGPT_OAUTH_CONFIG: Dict[str, Any] = {
    # OAuth endpoints from OpenAI auth service
    "issuer": "https://auth.openai.com",
    "auth_url": "https://auth.openai.com/oauth/authorize",
    "token_url": "https://auth.openai.com/oauth/token",
    "api_base_url": "https://api.openai.com",
    # OAuth client configuration for Code Puppy
    "client_id": "app_EMoamEEZ73f0CkXaXp7hrann",
    "scope": "openid profile email offline_access",
    # Callback handling (we host a localhost callback to capture the redirect)
    "redirect_host": "http://localhost",
    "redirect_path": "auth/callback",
    "required_port": 1455,
    "callback_timeout": 120,
    # Local configuration
    "token_storage": "~/.code_puppy/chatgpt_oauth.json",
    # Model configuration
    "prefix": "chatgpt-",
    "default_context_length": 272000,
    "api_key_env_var": "CHATGPT_OAUTH_API_KEY",
}


def get_token_storage_path() -> Path:
    """Get the path for storing OAuth tokens."""
    storage_path = Path(CHATGPT_OAUTH_CONFIG["token_storage"]).expanduser()
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    return storage_path


def get_config_dir() -> Path:
    """Get the Code Puppy configuration directory."""
    config_dir = Path("~/.code_puppy").expanduser()
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_chatgpt_models_path() -> Path:
    """Get the path to the dedicated chatgpt_models.json file."""
    return get_config_dir() / "chatgpt_models.json"
