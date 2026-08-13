"""Configuration for Meta Muse device-code OAuth."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from code_puppy import config

META_OAUTH_CONFIG: dict[str, Any] = {
    "auth_base_url": "https://auth.meta.com",
    "device_authorization_path": "/oidc/device/authorization/",
    "device_token_path": "/oidc/device/token/",
    "device_code_grant": "urn:ietf:params:oauth:grant-type:device_code",
    # Public client used by the official Muse Code launcher.
    "client_id": "1031625952748946",
    "api_origin": "https://api.meta.ai",
    "api_base_url": "https://api.meta.ai/v1",
    "mint_url": "https://api.meta.ai/muse-code/key",
    "catalog_url": "https://api.meta.ai/muse-code/models",
    "api_version": "1.0.0",
    "request_timeout": 30,
    "poll_timeout": 1_800,
    "prefix": "meta-",
    "default_model": "muse-spark-1.2-contributor",
}

# Used when Meta's richer model catalogue is temporarily unavailable.
FALLBACK_MODELS: dict[str, dict[str, Any]] = {
    "muse-spark-1.2-contributor": {
        "context_length": 1_007_997,
        "supported_settings": ["reasoning_effort"],
    },
    "muse-spark-1.2": {
        "context_length": 1_007_997,
        "supported_settings": ["reasoning_effort"],
    },
}


def get_token_storage_path() -> Path:
    """Return Code Puppy's private Meta credential path."""
    data_dir = Path(config.DATA_DIR)
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    return data_dir / "meta_oauth.json"


def get_muse_auth_path() -> Path:
    """Return the official Muse CLI credential path."""
    override = os.getenv("MUSE_AUTH_PATH")
    if override:
        return Path(override).expanduser()
    config_home = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_home / "muse" / "auth.json"
