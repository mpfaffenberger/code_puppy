"""Tests for best-effort Claude output-cap inference."""

import pytest

from code_puppy.models_dev_family import infer_family_output_cap, parse_claude_alias
from code_puppy.models_dev_parser import ModelInfo


def _model(model_id: str, max_output: int, provider: str = "anthropic") -> ModelInfo:
    return ModelInfo(
        provider_id=provider, model_id=model_id, name=model_id, max_output=max_output
    )


SNAPSHOT = [
    _model("claude-opus-4-0", 32000),
    _model("claude-opus-4-1", 32000),
    _model("claude-opus-4-5", 64000),
    _model("claude-sonnet-4-20250514", 64000),
    _model("claude-sonnet-4-5-20250929", 64000),
    _model("claude-3-7-sonnet-latest", 64000),
    _model("claude-3-5-haiku-latest", 8192),
    _model("claude-haiku-4-5-20251001", 64000),
    _model("claude-opus-4-9", 99999, provider="github-copilot"),
]


class TestParseClaudeAlias:
    @pytest.mark.parametrize(
        "model_id,expected",
        [
            ("claude-opus-5-5", ("opus", (5, 5))),
            ("claude-opus-5", ("opus", (5,))),
            ("claude-5-opus", ("opus", (5,))),
            ("claude-5-sonnet", ("sonnet", (5,))),
            ("claude-sonnet-5-5", ("sonnet", (5, 5))),
            ("claude-haiku-5-5", ("haiku", (5, 5))),
            ("claude-sonnet-4-5-20250929", ("sonnet", (4, 5))),
            ("claude-opus-4-20250514", ("opus", (4,))),
            ("claude-3-7-sonnet-20250219", ("sonnet", (3, 7))),
            ("claude-3-7-sonnet-latest", ("sonnet", (3, 7))),
            ("CLAUDE-OPUS-4-5", ("opus", (4, 5))),
        ],
    )
    def test_recognised_aliases(self, model_id, expected):
        assert parse_claude_alias(model_id) == expected

    @pytest.mark.parametrize(
        "model_id",
        [
            "",
            "claude",
            "gpt-5.4",
            "claude-opus",
            "claude-opus-sonnet-4",
            "claude-fable-4",
            "claude-opus-4-turbo",
            "claude-opus-latest",
        ],
    )
    def test_unrecognised_ids_are_none(self, model_id):
        assert parse_claude_alias(model_id) is None

    def test_non_string_never_raises(self):
        assert parse_claude_alias(None) is None  # type: ignore[arg-type]


class TestInferFamilyOutputCap:
    @pytest.mark.parametrize(
        "name",
        ["claude-opus-5-5", "claude-opus-5", "claude-5-opus", "claude-opus-4-6"],
    )
    def test_opus_borrows_newest_known_sibling(self, name):
        assert infer_family_output_cap(name, "custom_anthropic", SNAPSHOT) == 64000

    @pytest.mark.parametrize(
        "name", ["claude-5-sonnet", "claude-sonnet-5-5", "claude-haiku-5-5"]
    )
    def test_other_families(self, name):
        assert infer_family_output_cap(name, "anthropic", SNAPSHOT) == 64000

    def test_never_borrows_from_a_newer_sibling(self):
        assert (
            infer_family_output_cap("claude-opus-4-1", "anthropic", SNAPSHOT) == 32000
        )
        assert (
            infer_family_output_cap("claude-opus-4-3", "anthropic", SNAPSHOT) == 32000
        )

    def test_older_than_every_known_sibling_is_none(self):
        assert infer_family_output_cap("claude-opus-3", "anthropic", SNAPSHOT) is None

    def test_numeric_not_lexical_version_ordering(self):
        models = [_model("claude-opus-4-9", 32000), _model("claude-opus-4-10", 64000)]
        assert infer_family_output_cap("claude-opus-5", "anthropic", models) == 64000

    @pytest.mark.parametrize("catalog_type", ["custom_openai", "codex", "", "gemini"])
    def test_non_anthropic_catalog_type_is_none(self, catalog_type):
        assert (
            infer_family_output_cap("claude-opus-5-5", catalog_type, SNAPSHOT) is None
        )

    def test_other_providers_are_ignored(self):
        models = [_model("claude-opus-4-9", 99999, provider="github-copilot")]
        assert infer_family_output_cap("claude-opus-5", "anthropic", models) is None

    def test_unknown_family_is_none(self):
        assert infer_family_output_cap("claude-fable-5", "anthropic", SNAPSHOT) is None

    def test_disagreeing_siblings_at_top_version_is_none(self):
        models = [
            _model("claude-opus-4-5", 64000),
            _model("claude-opus-4-5-20251101", 32000),
        ]
        assert infer_family_output_cap("claude-opus-5", "anthropic", models) is None

    def test_agreeing_duplicates_are_fine(self):
        models = [
            _model("claude-opus-4-5", 64000),
            _model("claude-opus-4-5-20251101", 64000),
        ]
        assert infer_family_output_cap("claude-opus-5", "anthropic", models) == 64000

    def test_no_positive_cap_is_none(self):
        assert (
            infer_family_output_cap(
                "claude-opus-5", "anthropic", [_model("claude-opus-4-5", 0)]
            )
            is None
        )

    def test_empty_snapshot_is_none(self):
        assert infer_family_output_cap("claude-opus-5", "anthropic", []) is None
