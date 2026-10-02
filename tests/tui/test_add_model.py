"""Phase 3 Wave C: /add_model manual form."""

import json

import pytest

from code_puppy.tui.app import build_app
from code_puppy.tui.screens.form import FormScreen


@pytest.mark.asyncio
async def test_add_model_opens_form():
    app = build_app()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        app.submit_prompt("/add_model")
        await pilot.pause(0.2)
        assert isinstance(app.screen, FormScreen)


def test_save_custom_model_writes_endpoint(monkeypatch, tmp_path):
    models_file = tmp_path / "extra_models.json"
    monkeypatch.setattr("code_puppy.config.EXTRA_MODELS_FILE", str(models_file))
    from code_puppy.tui.menu_add_model import _save_extra_model

    _save_extra_model(
        {
            "key": "openrouter-llama",
            "type": "custom_openai",
            "name": "meta-llama/llama-3.3-70b",
            "url": "https://openrouter.ai/api/v1",
            "api_key_env": "OPENROUTER_API_KEY",
            "context_length": "128000",
        }
    )
    data = json.loads(models_file.read_text())
    entry = data["openrouter-llama"]
    assert entry["type"] == "custom_openai"
    assert entry["name"] == "meta-llama/llama-3.3-70b"
    assert entry["custom_endpoint"] == {
        "url": "https://openrouter.ai/api/v1",
        "api_key": "$OPENROUTER_API_KEY",
    }
    assert entry["context_length"] == 128000


def test_save_model_rejects_duplicate(monkeypatch, tmp_path):
    models_file = tmp_path / "extra_models.json"
    models_file.write_text(json.dumps({"dup": {"type": "openai", "name": "x"}}))
    monkeypatch.setattr("code_puppy.config.EXTRA_MODELS_FILE", str(models_file))
    errors = []
    monkeypatch.setattr(
        "code_puppy.messaging.emit_error", lambda msg, *a, **k: errors.append(msg)
    )
    from code_puppy.tui.menu_add_model import _save_extra_model

    _save_extra_model(
        {
            "key": "dup",
            "type": "openai",
            "name": "y",
            "url": "",
            "api_key_env": "",
            "context_length": "",
        }
    )
    assert errors and "already exists" in errors[0]


def test_save_model_bad_context_length(monkeypatch, tmp_path):
    models_file = tmp_path / "extra_models.json"
    monkeypatch.setattr("code_puppy.config.EXTRA_MODELS_FILE", str(models_file))
    errors = []
    monkeypatch.setattr(
        "code_puppy.messaging.emit_error", lambda msg, *a, **k: errors.append(msg)
    )
    from code_puppy.tui.menu_add_model import _save_extra_model

    _save_extra_model(
        {
            "key": "k",
            "type": "openai",
            "name": "n",
            "url": "",
            "api_key_env": "",
            "context_length": "lots",
        }
    )
    assert errors and "whole number" in errors[0]
    assert not models_file.exists()
