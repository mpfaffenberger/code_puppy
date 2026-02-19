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

    @classmethod
    def from_env(cls) -> "ACPConfig":
        """Build config from environment variables.

        Environment variables:
            ACP_ENABLED:   "true" / "false" (default: "true")
            ACP_TRANSPORT: "http" / "stdio" (default: "http")
            ACP_HOST:      bind host (default: "0.0.0.0")
            ACP_PORT:      bind port (default: 9001)
        """
        return cls(
            enabled=os.getenv("ACP_ENABLED", "true").lower() in ("true", "1", "yes"),
            transport=os.getenv("ACP_TRANSPORT", "http").lower(),
            host=os.getenv("ACP_HOST", "0.0.0.0"),
            port=int(os.getenv("ACP_PORT", "9001")),
        )
