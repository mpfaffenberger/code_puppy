"""ACP Gateway configuration.

All settings are read from environment variables with sensible defaults.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ACPConfig:
    """Immutable configuration for the ACP Gateway."""

    enabled: bool
    transport: str  # "http" or "stdio"
    host: str
    port: int
    auth_required: bool
    auth_token: str

    @staticmethod
    def _safe_int(value: str, default: int) -> int:
        """Parse an integer from string, returning *default* on failure."""
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    @classmethod
    def from_env(cls) -> "ACPConfig":
        """Build config from environment variables.

        Environment variables:
            ACP_ENABLED:       "true" / "false" (default: "true")
            ACP_TRANSPORT:     "http" / "stdio" (default: "http")
            ACP_HOST:          bind host (default: "127.0.0.1", set to "0.0.0.0" for network access)
            ACP_PORT:          bind port (default: 9001)
            ACP_AUTH_REQUIRED: "true" / "false" (default: "false")
            ACP_AUTH_TOKEN:    pre-shared bearer token (default: "")
        """
        return cls(
            enabled=os.getenv("ACP_ENABLED", "true").lower() in ("true", "1", "yes"),
            transport=os.getenv("ACP_TRANSPORT", "http").lower(),
            host=os.getenv("ACP_HOST", "127.0.0.1"),
            port=cls._safe_int(os.getenv("ACP_PORT", "9001"), default=9001),
            auth_required=os.getenv("ACP_AUTH_REQUIRED", "false").lower() in ("true", "1", "yes"),
            auth_token=os.getenv("ACP_AUTH_TOKEN", ""),
        )
