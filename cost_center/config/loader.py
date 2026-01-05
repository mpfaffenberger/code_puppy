"""Configuration loader for cost center."""

import json
from pathlib import Path

from cost_center.collectors.types import AppConfig


DEFAULT_CONFIG_PATH = Path("cost_center/config/tenants.json")


def load_config(config_path: Path | str | None = None) -> AppConfig:
    """Load configuration from JSON file."""
    if config_path is None:
        config_path = DEFAULT_CONFIG_PATH

    path = Path(config_path)
    if not path.exists():
        msg = f"Configuration file not found: {path}"
        raise FileNotFoundError(msg)

    with path.open() as f:
        data = json.load(f)

    return AppConfig(**data)
