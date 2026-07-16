"""Configuration for the Grok (x.ai) OAuth plugin.

Endpoints, client id, and scopes mirror the official Grok CLI OAuth flow
(as implemented by https://pi.dev/packages/pi-xai-oauth).
"""

from pathlib import Path
from typing import Any, Dict

from code_puppy import config

GROK_OAUTH_CONFIG: Dict[str, Any] = {
    # OIDC issuer + discovery. Authorization/token endpoints are resolved
    # dynamically from the discovery document and validated against *.x.ai.
    "issuer": "https://auth.x.ai",
    "discovery_url": "https://auth.x.ai/.well-known/openid-configuration",
    # Public OAuth client used by the official Grok CLI.
    "client_id": "b1a00492-073a-47ea-816f-4c329264a828",
    "scope": "openid profile email offline_access grok-cli:access api:access",
    # Localhost callback. xAI allows an ephemeral-port fallback when the
    # preferred port is busy.
    "redirect_host": "127.0.0.1",
    "redirect_port": 56121,
    "redirect_path": "/callback",
    "callback_timeout": 180,
    # Refresh this many seconds before the token actually expires.
    "refresh_skew_seconds": 120,
    # Grok models are served from the regular xAI API with the OAuth
    # access token as the bearer key.
    "api_base_url": "https://api.x.ai/v1",
    # Registered model names are prefixed to avoid catalogue collisions.
    "prefix": "xai-",
    "default_model": "grok-4.5",
}

# Grok models made available after authentication.
GROK_MODELS: Dict[str, Dict[str, Any]] = {
    "grok-4.5": {
        "context_length": 500_000,
        "supported_settings": ["reasoning_effort"],
    },
}


def get_token_storage_path() -> Path:
    """Path for storing OAuth tokens (uses XDG_DATA_HOME)."""
    data_dir = Path(config.DATA_DIR)
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    return data_dir / "grok_oauth.json"
