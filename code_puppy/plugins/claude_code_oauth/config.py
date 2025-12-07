from pathlib import Path
from typing import Any, Dict

from code_puppy import config

# Claude Code OAuth configuration
CLAUDE_CODE_OAUTH_CONFIG: Dict[str, Any] = {
    # OAuth endpoints inferred from official Claude Code OAuth flow
    "auth_url": "https://claude.ai/oauth/authorize",
    "token_url": "https://console.anthropic.com/v1/oauth/token",
    "api_base_url": "https://api.anthropic.com",
    # OAuth client configuration observed in Claude Code CLI flow
    "client_id": "9d1c250a-e61b-44d9-88ed-5944d1962f5e",
    "scope": "org:create_api_key user:profile user:inference",
    # Callback handling (we host a localhost callback to capture the redirect)
    "redirect_host": "http://localhost",
    "redirect_path": "callback",
    "callback_port_range": (8765, 8795),
    "callback_timeout": 180,
    # Console redirect fallback (for manual flows, if needed)
    "console_redirect_uri": "https://console.anthropic.com/oauth/code/callback",
    # Local configuration (uses XDG_DATA_HOME)
    "token_storage": None,  # Set dynamically in get_token_storage_path()
    # Model configuration
    "prefix": "claude-code-",
    "default_context_length": 200000,
    "api_key_env_var": "CLAUDE_CODE_ACCESS_TOKEN",
    "anthropic_version": "2023-06-01",
}


def get_token_storage_path() -> Path:
    """Get the path for storing OAuth tokens (uses XDG_DATA_HOME)."""
    data_dir = Path(config.DATA_DIR)
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    return data_dir / "claude_code_oauth.json"


def get_config_dir() -> Path:
    """Get the Code Puppy configuration directory (uses XDG_CONFIG_HOME)."""
    config_dir = Path(config.CONFIG_DIR)
    config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    return config_dir


def get_claude_models_path() -> Path:
    """Get the path to the dedicated claude_models.json file (uses XDG_DATA_HOME)."""
    data_dir = Path(config.DATA_DIR)
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    return data_dir / "claude_models.json"
