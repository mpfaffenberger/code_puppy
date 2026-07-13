"""Configuration management API endpoints."""

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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


@router.get("/schema")
async def get_config_schema() -> Dict[str, Any]:
    """Get configuration schema with metadata for all config keys.

    Returns metadata including:
    - description: Human-readable description of the config key
    - category: Config category (core, behavior, model, advanced, experimental)
    - type: Data type (boolean, string, number, choice)
    - choices: Valid values (for choice type)
    - default: Default value

    This endpoint allows frontends to dynamically render config UIs
    without hardcoding config key metadata.

    Returns:
        Dict with 'keys' mapping config names to their metadata
    """
    try:
        from code_puppy.config import CONFIG_SCHEMA

        return {"keys": CONFIG_SCHEMA}
    except Exception:
        # Migration-compat fallback: synthesize a minimal schema so the
        # endpoint remains functional even if CONFIG_SCHEMA is not exported.
        from code_puppy.config import get_config_keys, get_value

        inferred: Dict[str, Dict[str, Any]] = {}
        for key in get_config_keys():
            value = get_value(key)
            inferred[key] = {
                "description": "",
                "category": "legacy",
                "type": type(value).__name__ if value is not None else "unknown",
                "default": value,
            }
        return {"keys": inferred}


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


# =============================================================================
# Model Settings Endpoints
# =============================================================================


class ModelSettingsResponse(BaseModel):
    """Response containing model-specific settings."""

    model_name: str
    settings: Dict[str, Any]


class ModelSettingsUpdateRequest(BaseModel):
    """Request to update a model setting."""

    setting: str
    value: Any


@router.get("/model_settings/{model_name}")
async def get_model_settings(model_name: str) -> ModelSettingsResponse:
    """Get all settings for a specific model.

    Returns the persisted settings from ~/.code_puppy/code_puppy.ini
    for the specified model name.

    Args:
        model_name: The model name (e.g., 'gpt-5-2-0125', 'claude-4-5-sonnet')

    Returns:
        ModelSettingsResponse with model name and settings dict
    """
    from code_puppy.config import get_all_model_settings

    settings = get_all_model_settings(model_name)
    return ModelSettingsResponse(model_name=model_name, settings=settings)


@router.put("/model_settings/{model_name}")
async def update_model_setting(
    model_name: str, request: ModelSettingsUpdateRequest
) -> ModelSettingsResponse:
    """Update a specific setting for a model.

    Persists the setting to ~/.code_puppy/code_puppy.ini

    Args:
        model_name: The model name
        request: ModelSettingsUpdateRequest with setting name and value

    Returns:
        Updated ModelSettingsResponse
    """
    from code_puppy.config import get_all_model_settings, set_model_setting

    set_model_setting(model_name, request.setting, request.value)
    settings = get_all_model_settings(model_name)
    return ModelSettingsResponse(model_name=model_name, settings=settings)


@router.delete("/model_settings/{model_name}")
async def clear_model_settings(model_name: str) -> Dict[str, str]:
    """Clear all settings for a specific model.

    Removes all per-model settings, reverting to defaults.

    Args:
        model_name: The model name

    Returns:
        Success message
    """
    from code_puppy.config import clear_model_settings

    clear_model_settings(model_name)
    return {"message": f"All settings cleared for model '{model_name}'"}


@router.delete("/model_settings/{model_name}/{setting}")
async def clear_model_setting(model_name: str, setting: str) -> ModelSettingsResponse:
    """Clear a specific setting for a model.

    Removes the setting, reverting it to the default.

    Args:
        model_name: The model name
        setting: The setting name to clear

    Returns:
        Updated ModelSettingsResponse
    """
    from code_puppy.config import get_all_model_settings, set_model_setting

    set_model_setting(model_name, setting, None)
    settings = get_all_model_settings(model_name)
    return ModelSettingsResponse(model_name=model_name, settings=settings)
