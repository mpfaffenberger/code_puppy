"""Configuration for the Antigravity OAuth plugin."""

from pathlib import Path
from typing import Any, Dict

from code_puppy import config

# Antigravity OAuth configuration
ANTIGRAVITY_OAUTH_CONFIG: Dict[str, Any] = {
    # OAuth endpoints
    "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
    "token_url": "https://oauth2.googleapis.com/token",
    # Callback handling
    "redirect_host": "http://localhost",
    "redirect_path": "oauth-callback",
    "callback_port_range": (51121, 51150),
    "callback_timeout": 180,
    # Model configuration
    "prefix": "antigravity-",
    "default_context_length": 200000,
}


def get_token_storage_path() -> Path:
    """Get the path for storing OAuth tokens."""
    data_dir = Path(config.DATA_DIR)
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    return data_dir / "antigravity_oauth.json"


def get_accounts_storage_path() -> Path:
    """Get the path for storing multi-account data."""
    data_dir = Path(config.DATA_DIR)
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    return data_dir / "antigravity_accounts.json"


def get_antigravity_models_path() -> Path:
    """Get the path to the antigravity_models.json file."""
    data_dir = Path(config.DATA_DIR)
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    return data_dir / "antigravity_models.json"
