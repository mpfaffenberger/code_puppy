"""Utility functions for the AWS Bedrock plugin."""

from __future__ import annotations

import json
import logging
from typing import Any

from .config import (
    MODELS,
    get_extra_models_path,
)

logger = logging.getLogger(__name__)


def load_extra_models() -> dict[str, Any]:
    """Load the extra_models.json configuration file."""
    extra_models_path = get_extra_models_path()
    if not extra_models_path.exists():
        return {}

    try:
        with open(extra_models_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error("Error loading extra_models.json: %s", e)
        return {}


def save_extra_models(models: dict[str, Any]) -> bool:
    """Save model configurations to extra_models.json (atomic write)."""
    extra_models_path = get_extra_models_path()

    try:
        extra_models_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = extra_models_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(models, f, indent=2, ensure_ascii=False)
        temp_path.replace(extra_models_path)
        return True
    except Exception as e:
        logger.error("Error saving extra_models.json: %s", e)
        return False


def _build_model_entry(
    model_id: str,
    context_length: int,
    has_effort: bool,
    effort: str | None = None,
    aws_region: str | None = None,
    aws_profile: str | None = None,
) -> dict[str, Any]:
    """Build a single model config entry for extra_models.json."""
    supported_settings = [
        "temperature",
        "extended_thinking",
        "budget_tokens",
        "interleaved_thinking",
    ]
    if has_effort:
        supported_settings.append("effort")

    config: dict[str, Any] = {
        "type": "aws_bedrock",
        "provider": "aws_bedrock",
        "name": model_id,
        "context_length": context_length,
        "supported_settings": supported_settings,
    }
    if effort:
        config["default_effort"] = effort
    if aws_region:
        config["aws_region"] = aws_region
    if aws_profile:
        config["aws_profile"] = aws_profile

    return config


def add_bedrock_models_to_config(
    aws_region: str | None = None,
    aws_profile: str | None = None,
) -> list[str]:
    """Add Bedrock model configurations (with effort variants) to extra_models.json."""
    models = load_extra_models()
    added: list[str] = []

    for spec in MODELS:
        base_key = spec["base_key"]
        model_id = spec["model_id"]
        context_length = spec["context_length"]
        variants = spec.get("variants")

        if variants:
            for variant in variants:
                if variant == "default":
                    key = base_key
                    effort = None
                else:
                    key = f"{base_key}-{variant}"
                    effort = variant

                models[key] = _build_model_entry(
                    model_id=model_id,
                    context_length=context_length,
                    has_effort=True,
                    effort=effort,
                    aws_region=aws_region,
                    aws_profile=aws_profile,
                )
                added.append(key)
        else:
            models[base_key] = _build_model_entry(
                model_id=model_id,
                context_length=context_length,
                has_effort=False,
                aws_region=aws_region,
                aws_profile=aws_profile,
            )
            added.append(base_key)

    if added and save_extra_models(models):
        return added
    return []


def remove_bedrock_models_from_config() -> list[str]:
    """Remove all Bedrock model configurations from extra_models.json."""
    models = load_extra_models()
    removed = [
        key
        for key, cfg in models.items()
        if isinstance(cfg, dict) and cfg.get("type") == "aws_bedrock"
    ]

    for key in removed:
        del models[key]

    if removed and not save_extra_models(models):
        logger.error("Failed to save extra_models.json after removing Bedrock models")
        return []

    return removed


def get_bedrock_models_from_config() -> dict[str, Any]:
    """Get all Bedrock model configurations from extra_models.json."""
    models = load_extra_models()
    return {
        key: cfg
        for key, cfg in models.items()
        if isinstance(cfg, dict) and cfg.get("type") == "aws_bedrock"
    }
