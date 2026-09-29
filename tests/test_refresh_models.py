"""Tests for ``/refresh_models`` backfilling limits from models.dev.

The matching rules used here are shared with model resolution
(``models_dev_parser.match_limits``), so these tests pin the contract both
callers depend on: never blast anything models.dev can't vouch for.
"""

import json

from code_puppy.command_line.refresh_models import refresh_extra_models
from code_puppy.models_dev_parser import ModelInfo

OPUS = ("anthropic", "claude-opus-5", "Claude Opus 5", 128000, 1000000)


def _models(*specs: tuple[str, str, str, int, int]) -> list[ModelInfo]:
    return [
        ModelInfo(
            provider_id=provider,
            model_id=model_id,
            name=name,
            max_output=max_output,
            context_length=context_length,
        )
        for provider, model_id, name, max_output, context_length in specs
    ]


class _Registry:
    """Just enough registry for the backfill: ``get_models()`` and nothing else."""

    def __init__(self, models: list[ModelInfo]) -> None:
        self._models = list(models)

    def get_models(self) -> list[ModelInfo]:
        return list(self._models)


def _run(tmp_path, entries: dict, models: list[ModelInfo]):
    """Write ``entries``, refresh them, and hand back (report, written file)."""
    path = tmp_path / "extra_models.json"
    path.write_text(json.dumps(entries))
    report = refresh_extra_models(registry=_Registry(models), path=str(path))
    return report, json.loads(path.read_text())


class TestRefreshExtraModels:
    def test_exact_key_gets_limits_filled(self, tmp_path):
        report, written = _run(
            tmp_path,
            {"anthropic-claude-opus-5": {"name": "claude-opus-5"}},
            _models(OPUS),
        )
        assert report.updated == ["anthropic-claude-opus-5"]
        assert written["anthropic-claude-opus-5"]["max_output_tokens"] == 128000
        assert written["anthropic-claude-opus-5"]["context_length"] == 1000000

    def test_name_only_match_fills_missing_limits(self, tmp_path):
        report, written = _run(
            tmp_path, {"hand-written": {"name": "claude-opus-5"}}, _models(OPUS)
        )
        assert report.updated == ["hand-written"]
        assert written["hand-written"]["max_output_tokens"] == 128000

    def test_exact_key_overwrites_existing_limit(self, tmp_path):
        """``/add_model``-shaped keys are auto-populated, so models.dev wins."""
        _, written = _run(
            tmp_path,
            {
                "anthropic-claude-opus-5": {
                    "name": "claude-opus-5",
                    "max_output_tokens": 4096,
                }
            },
            _models(OPUS),
        )
        assert written["anthropic-claude-opus-5"]["max_output_tokens"] == 128000

    def test_name_only_does_not_overwrite_existing_limit(self, tmp_path):
        """A name match is a guess, so a hand-set cap is left alone."""
        _, written = _run(
            tmp_path,
            {"hand-written": {"name": "claude-opus-5", "max_output_tokens": 4096}},
            _models(OPUS),
        )
        assert written["hand-written"]["max_output_tokens"] == 4096

    def test_context_length_is_never_overwritten(self, tmp_path):
        """People hand-tune context_length; only fill it when missing."""
        _, written = _run(
            tmp_path,
            {
                "anthropic-claude-opus-5": {
                    "name": "claude-opus-5",
                    "context_length": 12345,
                }
            },
            _models(OPUS),
        )
        assert written["anthropic-claude-opus-5"]["context_length"] == 12345

    def test_disagreeing_providers_are_reported_ambiguous(self, tmp_path):
        copilot = (
            "github-copilot",
            "claude-opus-5",
            "Opus 5 (Copilot)",
            64000,
            1000000,
        )
        report, written = _run(
            tmp_path,
            {"hand-written": {"name": "claude-opus-5"}},
            _models(OPUS, copilot),
        )
        assert report.ambiguous == ["hand-written"]
        assert "max_output_tokens" not in written["hand-written"]

    def test_unknown_model_is_reported_unmatched(self, tmp_path):
        report, written = _run(
            tmp_path, {"mystery": {"name": "nope-9000"}}, _models(OPUS)
        )
        assert report.unmatched == ["mystery"]
        assert written["mystery"] == {"name": "nope-9000"}

    def test_untouched_entries_are_reported_unchanged(self, tmp_path):
        entries = {
            "anthropic-claude-opus-5": {
                "name": "claude-opus-5",
                "max_output_tokens": 128000,
                "context_length": 1000000,
            }
        }
        report, _ = _run(tmp_path, entries, _models(OPUS))
        assert report.unchanged == ["anthropic-claude-opus-5"]
        assert report.updated == []

    def test_nothing_to_write_leaves_the_file_alone(self, tmp_path):
        path = tmp_path / "extra_models.json"
        original = {"mystery": {"name": "nope-9000"}}
        path.write_text(json.dumps(original))
        refresh_extra_models(registry=_Registry(_models(OPUS)), path=str(path))
        assert json.loads(path.read_text()) == original
