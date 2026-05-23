from __future__ import annotations

from code_puppy.model_descriptions import (
    DEFAULT_MODEL_DESCRIPTION,
    apply_description_overlays,
    get_model_description,
)


def test_apply_description_overlays_injects_only_description() -> None:
    base = {
        "remote-model": {
            "type": "custom_openai",
            "name": "gpt-something",
            "context_length": 123,
        }
    }

    overlay = {"remote-model": "Hello I am a model."}
    apply_description_overlays(base, overlay)

    assert base["remote-model"]["description"] == "Hello I am a model."
    assert base["remote-model"]["type"] == "custom_openai"
    assert base["remote-model"]["name"] == "gpt-something"
    assert base["remote-model"]["context_length"] == 123


def test_apply_description_overlays_does_not_override_existing() -> None:
    base = {"m": {"description": "Existing"}}
    apply_description_overlays(base, {"m": "New"})
    assert base["m"]["description"] == "Existing"


def test_apply_description_overlays_does_not_create_new_models() -> None:
    base = {"m": {"type": "x"}}
    apply_description_overlays(base, {"new": "desc"})
    assert "new" not in base


def test_get_model_description_falls_back_for_missing_or_blank() -> None:
    assert get_model_description({}, "missing") == DEFAULT_MODEL_DESCRIPTION
    assert (
        get_model_description({"m": {"description": "   "}}, "m")
        == DEFAULT_MODEL_DESCRIPTION
    )
