"""Utility functions for the AWS Bedrock plugin."""

from __future__ import annotations

import json
import logging
from typing import Any

from code_puppy import atomic_io, atomic_json

from .config import (
    MODELS,
    get_extra_models_path,
)

logger = logging.getLogger(__name__)


def load_extra_models() -> dict[str, Any]:
    """Load the extra_models.json configuration file.

    Bounded and lock-aware via :mod:`code_puppy.atomic_json` -- a large or
    concurrently-being-written file can no longer balloon memory or read a
    torn write. Preserves the original never-raise contract: any failure
    (missing file, invalid JSON, oversized file, I/O error) logs and
    returns ``{}`` rather than propagating.
    """
    extra_models_path = str(get_extra_models_path())
    try:
        return atomic_json.load_json(extra_models_path, default={})
    except (atomic_json.JsonFileCorrupt, OSError) as e:
        logger.error("Error loading extra_models.json: %s", e)
        return {}


def save_extra_models(models: dict[str, Any]) -> bool:
    """Save model configurations to extra_models.json (atomic, locked write)."""
    extra_models_path = str(get_extra_models_path())

    try:
        with atomic_io.path_lock(extra_models_path):
            atomic_io.atomic_write_bytes(
                extra_models_path,
                json.dumps(models, indent=2, ensure_ascii=False).encode("utf-8"),
            )
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
    """Add Bedrock model configurations (with effort variants) to extra_models.json.

    Uses :func:`code_puppy.atomic_json.mutate_json` so the read and write
    happen inside one locked transaction -- extra_models.json is also
    touched by add_model_menu.py and the ollama_setup/azure_foundry
    plugins, so a read-then-write split across two unlocked calls could
    lose one of those concurrent updates.
    """
    entries: dict[str, dict[str, Any]] = {}
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

                entries[key] = _build_model_entry(
                    model_id=model_id,
                    context_length=context_length,
                    has_effort=True,
                    effort=effort,
                    aws_region=aws_region,
                    aws_profile=aws_profile,
                )
        else:
            entries[base_key] = _build_model_entry(
                model_id=model_id,
                context_length=context_length,
                has_effort=False,
                aws_region=aws_region,
                aws_profile=aws_profile,
            )

    if not entries:
        return []

    def _mutate(models: dict[str, Any]) -> dict[str, Any]:
        models.update(entries)
        return models

    extra_models_path = str(get_extra_models_path())
    try:
        atomic_json.mutate_json(extra_models_path, _mutate, default={})
    except (atomic_json.JsonFileCorrupt, OSError) as e:
        logger.error("Error saving extra_models.json: %s", e)
        return []

    return list(entries.keys())


def remove_bedrock_models_from_config() -> list[str]:
    """Remove all Bedrock model configurations from extra_models.json.

    Uses :func:`code_puppy.atomic_json.mutate_json` so the read and write
    happen inside one locked transaction (see :func:`add_bedrock_models_to_config`).
    """
    extra_models_path = str(get_extra_models_path())
    removed: list[str] = []

    def _mutate(models: dict[str, Any]) -> dict[str, Any]:
        removed[:] = [
            key
            for key, cfg in models.items()
            if isinstance(cfg, dict) and cfg.get("type") == "aws_bedrock"
        ]
        for key in removed:
            del models[key]
        return models

    try:
        atomic_json.mutate_json(extra_models_path, _mutate, default={})
    except (atomic_json.JsonFileCorrupt, OSError) as e:
        logger.error(
            "Failed to save extra_models.json after removing Bedrock models: %s", e
        )
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
