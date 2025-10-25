from pathlib import Path
from typing import Any, Dict

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
    # Local configuration
    "token_storage": "~/.code_puppy/claude_code_oauth.json",
    # Model configuration
    "prefix": "claude-code-",
    "default_context_length": 200000,
    "api_key_env_var": "CLAUDE_CODE_ACCESS_TOKEN",
    "anthropic_version": "2023-06-01",
}


def get_token_storage_path() -> Path:
    """Get the path for storing OAuth tokens."""
    storage_path = Path(CLAUDE_CODE_OAUTH_CONFIG["token_storage"]).expanduser()
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    return storage_path


def get_config_dir() -> Path:
    """Get the Code Puppy configuration directory."""
    config_dir = Path("~/.code_puppy").expanduser()
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_claude_models_path() -> Path:
    """Get the path to the dedicated claude_models.json file."""
    return get_config_dir() / "claude_models.json"
