"""ModelFactory's model-catalog seams that plugins feed."""

from __future__ import annotations

import json

import pytest

from code_puppy import callbacks
from code_puppy import config as cp_config
from code_puppy import model_factory
from code_puppy.model_factory import ModelFactory, get_custom_config


@pytest.fixture
def claude_models_file(tmp_path, monkeypatch):
    """Only the Claude OAuth models file exists, holding one raw entry."""
    claude = tmp_path / "claude_models.json"
    claude.write_text(json.dumps({"raw-from-file": {"type": "anthropic"}}))
    missing = str(tmp_path / "missing.json")
    monkeypatch.setattr(model_factory, "EXTRA_MODELS_FILE", missing)
    for name in ("CHATGPT_MODELS_FILE", "GEMINI_MODELS_FILE", "COPILOT_MODELS_FILE"):
        monkeypatch.setattr(cp_config, name, missing)
    monkeypatch.setattr(cp_config, "CLAUDE_MODELS_FILE", str(claude))
    for phase in ("load_model_config", "load_claude_oauth_models"):
        monkeypatch.setitem(callbacks._callbacks, phase, [])


def test_claude_models_come_filtered_from_the_plugin(claude_models_file):
    callbacks.register_callback(
        "load_claude_oauth_models", lambda: {"filtered-latest": {"type": "anthropic"}}
    )
    config = ModelFactory.load_config()
    assert "filtered-latest" in config
    assert "raw-from-file" not in config


def test_claude_models_fall_back_to_plain_json_without_the_plugin(claude_models_file):
    config = ModelFactory.load_config()
    assert "raw-from-file" in config


def test_custom_endpoint_literal_api_key_is_used_verbatim():
    _, _, _, api_key, _ = get_custom_config(
        {"custom_endpoint": {"url": "https://example.test", "api_key": "sk-literal"}}
    )
    assert api_key == "sk-literal"
