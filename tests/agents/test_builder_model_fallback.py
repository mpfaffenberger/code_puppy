"""Regression tests for ``load_model_with_fallback`` model resolution."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from code_puppy.agents._builder import load_model_with_fallback


def _config() -> dict[str, dict[str, str]]:
    return {
        "broken": {"type": "openai", "name": "broken-model"},
        "fallback-none": {"type": "openai", "name": "fallback-none-model"},
        "fallback-good": {"type": "openai", "name": "fallback-good-model"},
    }


def test_fallback_skips_none_model_and_uses_next_candidate() -> None:
    """A fallback candidate returning ``None`` must not be treated as success."""
    models_config = _config()
    expected_model = object()
    call_order: list[str] = []

    def _fake_get_model(model_name: str, _cfg: dict[str, object]) -> object | None:
        call_order.append(model_name)
        if model_name == "broken":
            raise ValueError(
                "Model 'broken' was found in configuration but could not be instantiated "
                "(handler returned None)."
            )
        if model_name == "fallback-none":
            return None
        if model_name == "fallback-good":
            return expected_model
        raise AssertionError(f"Unexpected model lookup: {model_name}")

    with (
        patch(
            "code_puppy.agents._builder.ModelFactory.get_model",
            side_effect=_fake_get_model,
        ),
        patch(
            "code_puppy.agents._builder.get_global_model_name",
            return_value="fallback-none",
        ),
        patch("code_puppy.agents._builder.emit_warning"),
        patch("code_puppy.agents._builder.emit_info") as emit_info,
    ):
        model, resolved_name = load_model_with_fallback("broken", models_config, "grp")

    assert model is expected_model
    assert resolved_name == "fallback-good"
    assert call_order == ["broken", "fallback-none", "fallback-good"]
    emit_info.assert_called_once_with(
        "Using fallback model: fallback-good",
        message_group="grp",
    )


def test_fallback_raises_when_all_candidates_are_invalid_or_none() -> None:
    """When every candidate fails, we should raise a clear ValueError."""
    models_config = {
        "broken": {"type": "openai", "name": "broken-model"},
        "fallback-none": {"type": "openai", "name": "fallback-none-model"},
        "fallback-error": {"type": "openai", "name": "fallback-error-model"},
    }

    def _fake_get_model(model_name: str, _cfg: dict[str, object]) -> object | None:
        if model_name == "broken":
            raise ValueError("Model 'broken' could not be instantiated")
        if model_name == "fallback-none":
            return None
        if model_name == "fallback-error":
            raise ValueError("Model 'fallback-error' not found in configuration")
        raise AssertionError(f"Unexpected model lookup: {model_name}")

    with (
        patch(
            "code_puppy.agents._builder.ModelFactory.get_model",
            side_effect=_fake_get_model,
        ),
        patch(
            "code_puppy.agents._builder.get_global_model_name",
            return_value="fallback-none",
        ),
        patch("code_puppy.agents._builder.emit_warning"),
        patch("code_puppy.agents._builder.emit_error") as emit_error,
    ):
        with pytest.raises(ValueError, match="No valid model could be loaded"):
            load_model_with_fallback("broken", models_config, "grp")

    emit_error.assert_called_once()
