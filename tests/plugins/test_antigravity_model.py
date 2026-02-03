"""Core initialization tests for antigravity_model."""

from __future__ import annotations

import pytest

from code_puppy.plugins.antigravity_oauth.antigravity_model import AntigravityModel


class TestAntigravityModelInitialization:
    """Test AntigravityModel initialization and basic properties."""

    def test_model_initialization(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that model initializes with correct attributes."""
        model = AntigravityModel("gemini-1.5-pro", api_key="test-key-for-ci")
        assert model._model_name == "gemini-1.5-pro"
        assert model.system == "google"

    @pytest.mark.parametrize(
        "model_name", ["gemini-1.5-pro", "claude-3-5-sonnet", "custom-model"]
    )
    def test_various_model_names(
        self, model_name: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test model initialization with various model names."""
        model = AntigravityModel(model_name, api_key="test-key-for-ci")
        assert model._model_name == model_name
