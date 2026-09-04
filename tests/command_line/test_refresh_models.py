"""Tests for ``/refresh_models`` -- backfilling extra_models.json from models.dev."""

import json

import pytest

from code_puppy.command_line.refresh_models import refresh_extra_models
from code_puppy.models_dev_parser import ModelInfo


class FakeRegistry:
    def __init__(self, models):
        self._models = models

    def get_models(self, provider_id=None):
        return list(self._models)


def model(provider_id, model_id, max_output=0, context_length=0):
    return ModelInfo(
        provider_id=provider_id,
        model_id=model_id,
        name=model_id,
        max_output=max_output,
        context_length=context_length,
    )


@pytest.fixture
def registry():
    return FakeRegistry(
        [
            model("acme", "acme-large", max_output=64000, context_length=200000),
            # Same model id from two providers, same cap -> unambiguous by name.
            model("openai", "gpt-5", max_output=128000, context_length=400000),
            model("openrouter", "openai/gpt-5", max_output=128000),
            model("azure", "gpt-5", max_output=128000, context_length=400000),
            # Same id, different caps -> ambiguous by name.
            model("groq", "llama-3", max_output=8192),
            model("together-ai", "llama-3", max_output=4096),
        ]
    )


@pytest.fixture
def extra(tmp_path):
    """Write ``entries`` to a temp extra_models.json, return (path, reader)."""
    path = tmp_path / "extra_models.json"

    def write(entries):
        path.write_text(json.dumps(entries))
        return str(path)

    def read():
        return json.loads(path.read_text())

    return write, read


class TestRefreshExtraModels:
    def test_exact_key_match_backfills_both_limits(self, registry, extra):
        write, read = extra
        path = write(
            {"acme-acme-large": {"type": "custom_openai", "name": "acme-large"}}
        )

        report = refresh_extra_models(registry, path)

        assert report.updated == ["acme-acme-large"]
        entry = read()["acme-acme-large"]
        assert entry["max_output_tokens"] == 64000
        assert entry["context_length"] == 200000

    def test_overwrites_stale_max_output_but_keeps_hand_tuned_context(
        self, registry, extra
    ):
        write, read = extra
        path = write(
            {
                "acme-acme-large": {
                    "name": "acme-large",
                    "max_output_tokens": 1234,
                    "context_length": 195000,
                }
            }
        )

        refresh_extra_models(registry, path)

        entry = read()["acme-acme-large"]
        assert entry["max_output_tokens"] == 64000
        assert entry["context_length"] == 195000

    def test_already_current_is_reported_unchanged(self, registry, extra):
        write, read = extra
        path = write(
            {
                "acme-acme-large": {
                    "name": "acme-large",
                    "max_output_tokens": 64000,
                    "context_length": 200000,
                }
            }
        )

        report = refresh_extra_models(registry, path)

        assert report.unchanged == ["acme-acme-large"]
        assert report.updated == []

    def test_hand_written_entry_matched_by_name_fills_missing(self, registry, extra):
        write, read = extra
        path = write({"my-gpt5": {"type": "openai", "name": "gpt-5"}})

        report = refresh_extra_models(registry, path)

        assert report.updated == ["my-gpt5"]
        assert read()["my-gpt5"]["max_output_tokens"] == 128000

    def test_name_match_never_overwrites_hand_set_values(self, registry, extra):
        """A name-only match is a guess: fill blanks, never clobber."""
        write, read = extra
        hand_written = {
            "type": "openai",
            "name": "gpt-5",
            "max_output_tokens": 4096,
            "context_length": 50000,
        }
        path = write({"my-gpt5": dict(hand_written)})

        report = refresh_extra_models(registry, path)

        assert report.unchanged == ["my-gpt5"]
        assert read()["my-gpt5"] == hand_written

    def test_ambiguous_name_left_alone(self, registry, extra):
        write, read = extra
        path = write({"my-llama": {"type": "custom_openai", "name": "llama-3"}})

        report = refresh_extra_models(registry, path)

        assert report.ambiguous == ["my-llama"]
        assert "max_output_tokens" not in read()["my-llama"]

    def test_unknown_model_left_alone(self, registry, extra):
        write, read = extra
        path = write({"mystery": {"type": "custom_openai", "name": "claude-fable-5"}})

        report = refresh_extra_models(registry, path)

        assert report.unmatched == ["mystery"]
        assert read()["mystery"] == {"type": "custom_openai", "name": "claude-fable-5"}

    def test_unmatched_entries_survive_verbatim_alongside_updates(
        self, registry, extra
    ):
        """Blast radius check: only matched entries change, byte for byte."""
        write, read = extra
        untouchables = {
            "boodleton-glm-flash": {
                "type": "custom_openai",
                "name": "glm-5.3-flash-exl3",
                "custom_endpoint": {"url": "https://x.example/v1", "api_key": "$K"},
                "context_length": 195000,
                "supported_settings": ["temperature"],
                "some_future_key": {"nested": [1, 2, 3]},
            },
            "my-llama": {"type": "custom_openai", "name": "llama-3"},
        }
        path = write({**untouchables, "acme-acme-large": {"name": "acme-large"}})

        report = refresh_extra_models(registry, path)

        assert report.updated == ["acme-acme-large"]
        after = read()
        for key, original in untouchables.items():
            assert after[key] == original
        assert list(after) == list(untouchables) + ["acme-acme-large"]

    def test_file_not_rewritten_when_nothing_changes(self, registry, extra, tmp_path):
        write, read = extra
        original_text = '{"mystery": {"name": "claude-fable-5"}}'
        path = write({"mystery": {"name": "claude-fable-5"}})
        (tmp_path / "extra_models.json").write_text(original_text)  # odd formatting

        refresh_extra_models(registry, path)

        assert (tmp_path / "extra_models.json").read_text() == original_text

    def test_non_dict_entries_skipped(self, registry, extra):
        write, read = extra
        path = write({"weird": "not a dict"})

        report = refresh_extra_models(registry, path)

        assert report.updated == report.unmatched == []
        assert read() == {"weird": "not a dict"}

    def test_missing_file_is_a_noop(self, registry, tmp_path):
        report = refresh_extra_models(registry, str(tmp_path / "nope.json"))
        assert report.updated == []

    def test_list_file_raises(self, registry, extra):
        write, _ = extra
        path = write([1, 2, 3])
        with pytest.raises(ValueError):
            refresh_extra_models(registry, path)
