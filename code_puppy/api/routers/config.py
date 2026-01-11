"""Configuration management API endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List

router = APIRouter()


class ConfigValue(BaseModel):
    key: str
    value: Any


class ConfigUpdate(BaseModel):
    value: Any


@router.get("/")
async def list_config() -> Dict[str, Any]:
    """List all configuration keys and their current values."""
    from code_puppy.config import get_config_keys, get_value

    config = {}
    for key in get_config_keys():
        config[key] = get_value(key)
    return {"config": config}


@router.get("/keys")
async def get_config_keys_list() -> List[str]:
    """Get list of all valid configuration keys."""
    from code_puppy.config import get_config_keys

    return get_config_keys()


@router.get("/{key}")
async def get_config_value(key: str) -> ConfigValue:
    """Get a specific configuration value."""
    from code_puppy.config import get_config_keys, get_value

    valid_keys = get_config_keys()
    if key not in valid_keys:
        raise HTTPException(
            404, f"Config key '{key}' not found. Valid keys: {valid_keys}"
        )

    value = get_value(key)
    return ConfigValue(key=key, value=value)


@router.put("/{key}")
async def set_config_value(key: str, update: ConfigUpdate) -> ConfigValue:
    """Set a configuration value."""
    from code_puppy.config import get_config_keys, get_value, set_value

    valid_keys = get_config_keys()
    if key not in valid_keys:
        raise HTTPException(
            404, f"Config key '{key}' not found. Valid keys: {valid_keys}"
        )

    set_value(key, str(update.value))
    return ConfigValue(key=key, value=get_value(key))


@router.delete("/{key}")
async def reset_config_value(key: str) -> Dict[str, str]:
    """Reset a configuration value to default (remove from config file)."""
    from code_puppy.config import reset_value

    reset_value(key)
    return {"message": f"Config key '{key}' reset to default"}
