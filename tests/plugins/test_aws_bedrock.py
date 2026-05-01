"""Tests for the AWS Bedrock plugin.

Covers config, utils (model entry building, config round-trip, variant
expansion), register_callbacks (slash commands, custom command dispatch),
and the shared adaptive-thinking helper in model_utils.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def tmp_extra_models(tmp_path):
    """Return a path to a temporary extra_models.json and patch get_extra_models_path."""
    p = tmp_path / "extra_models.json"
    with patch(
        "code_puppy.plugins.aws_bedrock.utils.get_extra_models_path", return_value=p
    ):
        yield p


@pytest.fixture
def extra_models_with_bedrock(tmp_extra_models):
    """Create an extra_models.json that already contains some Bedrock entries."""
    data = {
        "bedrock-opus-4-7": {
            "type": "aws_bedrock",
            "provider": "aws_bedrock",
            "name": "us.anthropic.claude-opus-4-7",
            "context_length": 1000000,
        },
        "bedrock-haiku": {
            "type": "aws_bedrock",
            "provider": "aws_bedrock",
            "name": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
            "context_length": 200000,
        },
        "some-openai-model": {
            "type": "openai",
            "name": "gpt-4o",
            "context_length": 128000,
        },
    }
    tmp_extra_models.write_text(json.dumps(data, indent=2))
    return tmp_extra_models


# ============================================================================
# CONFIG MODULE TESTS
# ============================================================================


class TestConfig:
    """Test config.py constants and helpers."""

    def test_models_list_has_expected_entries(self):
        from code_puppy.plugins.aws_bedrock.config import MODELS

        keys = [m["base_key"] for m in MODELS]
        assert "bedrock-opus-4-7" in keys
        assert "bedrock-opus-4-6" in keys
        assert "bedrock-sonnet-4-6" in keys
        assert "bedrock-haiku" in keys

    def test_models_context_lengths(self):
        from code_puppy.plugins.aws_bedrock.config import MODELS

        by_key = {m["base_key"]: m for m in MODELS}
        assert by_key["bedrock-opus-4-7"]["context_length"] == 1_000_000
        assert by_key["bedrock-opus-4-6"]["context_length"] == 1_000_000
        assert by_key["bedrock-sonnet-4-6"]["context_length"] == 1_000_000
        assert by_key["bedrock-haiku"]["context_length"] == 200_000

    def test_get_bedrock_region_env_override(self):
        from code_puppy.plugins.aws_bedrock.config import get_bedrock_region

        with patch.dict("os.environ", {"BEDROCK_REGION": "eu-west-1"}, clear=False):
            assert get_bedrock_region() == "eu-west-1"

    def test_get_bedrock_region_aws_region_fallback(self):
        from code_puppy.plugins.aws_bedrock.config import get_bedrock_region

        env = {"AWS_REGION": "us-west-2"}
        with (
            patch.dict("os.environ", env, clear=False),
            patch.dict("os.environ", {"BEDROCK_REGION": ""}, clear=False),
        ):
            # Remove BEDROCK_REGION so it falls through
            import os

            os.environ.pop("BEDROCK_REGION", None)
            assert get_bedrock_region() == "us-west-2"

    def test_get_bedrock_region_default(self):
        from code_puppy.plugins.aws_bedrock.config import get_bedrock_region

        with (
            patch.dict(
                "os.environ",
                {"BEDROCK_REGION": "", "AWS_REGION": ""},
                clear=False,
            ),
            patch(
                "code_puppy.plugins.aws_bedrock.config._detect_region",
                return_value=None,
            ),
        ):
            import os

            os.environ.pop("BEDROCK_REGION", None)
            os.environ.pop("AWS_REGION", None)
            assert get_bedrock_region() == "us-east-1"

    def test_get_aws_profile_from_env(self):
        from code_puppy.plugins.aws_bedrock.config import get_aws_profile

        with patch.dict("os.environ", {"AWS_PROFILE": "dev-profile"}, clear=False):
            assert get_aws_profile() == "dev-profile"

    def test_get_aws_profile_none_when_unset(self):
        from code_puppy.plugins.aws_bedrock.config import get_aws_profile

        with patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop("AWS_PROFILE", None)
            assert get_aws_profile() is None


# ============================================================================
# UTILS MODULE TESTS
# ============================================================================


class TestBuildModelEntry:
    """Test _build_model_entry helper."""

    def test_basic_entry(self):
        from code_puppy.plugins.aws_bedrock.utils import _build_model_entry

        entry = _build_model_entry(
            model_id="us.anthropic.claude-opus-4-7",
            context_length=1_000_000,
            has_effort=False,
        )
        assert entry["type"] == "aws_bedrock"
        assert entry["provider"] == "aws_bedrock"
        assert entry["name"] == "us.anthropic.claude-opus-4-7"
        assert entry["context_length"] == 1_000_000
        assert "effort" not in entry.get("supported_settings", [])
        assert "default_effort" not in entry

    def test_entry_with_effort(self):
        from code_puppy.plugins.aws_bedrock.utils import _build_model_entry

        entry = _build_model_entry(
            model_id="us.anthropic.claude-opus-4-7",
            context_length=1_000_000,
            has_effort=True,
            effort="high",
        )
        assert "effort" in entry["supported_settings"]
        assert entry["default_effort"] == "high"

    def test_entry_with_aws_overrides(self):
        from code_puppy.plugins.aws_bedrock.utils import _build_model_entry

        entry = _build_model_entry(
            model_id="us.anthropic.claude-opus-4-7",
            context_length=1_000_000,
            has_effort=False,
            aws_region="eu-west-1",
            aws_profile="prod",
        )
        assert entry["aws_region"] == "eu-west-1"
        assert entry["aws_profile"] == "prod"


class TestAddBedrockModelsToConfig:
    """Test add_bedrock_models_to_config — variant expansion and persistence."""

    def test_adds_all_models_and_variants(self, tmp_extra_models):
        from code_puppy.plugins.aws_bedrock.utils import add_bedrock_models_to_config

        added = add_bedrock_models_to_config(aws_region="us-east-1")
        assert len(added) > 0

        # Check that base keys exist
        assert "bedrock-opus-4-7" in added
        assert "bedrock-haiku" in added

        # Check variant keys
        assert "bedrock-opus-4-7-high" in added
        assert "bedrock-sonnet-4-6-low" in added

        # Verify file was written
        data = json.loads(tmp_extra_models.read_text())
        assert "bedrock-opus-4-7" in data
        assert data["bedrock-opus-4-7"]["type"] == "aws_bedrock"

    def test_preserves_existing_entries(self, tmp_extra_models):
        from code_puppy.plugins.aws_bedrock.utils import add_bedrock_models_to_config

        # Write a pre-existing model
        existing = {"my-openai-model": {"type": "openai", "name": "gpt-4o"}}
        tmp_extra_models.write_text(json.dumps(existing))

        add_bedrock_models_to_config(aws_region="us-east-1")
        data = json.loads(tmp_extra_models.read_text())
        assert "my-openai-model" in data
        assert "bedrock-opus-4-7" in data

    def test_returns_empty_on_save_failure(self, tmp_extra_models):
        from code_puppy.plugins.aws_bedrock.utils import add_bedrock_models_to_config

        with patch(
            "code_puppy.plugins.aws_bedrock.utils.save_extra_models",
            return_value=False,
        ):
            result = add_bedrock_models_to_config()
            assert result == []


class TestRemoveBedrockModelsFromConfig:
    """Test remove_bedrock_models_from_config."""

    def test_removes_only_bedrock_entries(self, extra_models_with_bedrock):
        from code_puppy.plugins.aws_bedrock.utils import (
            remove_bedrock_models_from_config,
        )

        removed = remove_bedrock_models_from_config()
        assert "bedrock-opus-4-7" in removed
        assert "bedrock-haiku" in removed
        assert "some-openai-model" not in removed

        data = json.loads(extra_models_with_bedrock.read_text())
        assert "some-openai-model" in data
        assert "bedrock-opus-4-7" not in data

    def test_returns_empty_when_nothing_to_remove(self, tmp_extra_models):
        from code_puppy.plugins.aws_bedrock.utils import (
            remove_bedrock_models_from_config,
        )

        tmp_extra_models.write_text(json.dumps({"gpt-4o": {"type": "openai"}}))
        removed = remove_bedrock_models_from_config()
        assert removed == []

    def test_returns_empty_on_save_failure(self, extra_models_with_bedrock):
        from code_puppy.plugins.aws_bedrock.utils import (
            remove_bedrock_models_from_config,
        )

        with patch(
            "code_puppy.plugins.aws_bedrock.utils.save_extra_models",
            return_value=False,
        ):
            result = remove_bedrock_models_from_config()
            assert result == []


class TestGetBedrockModelsFromConfig:
    """Test get_bedrock_models_from_config."""

    def test_filters_bedrock_only(self, extra_models_with_bedrock):
        from code_puppy.plugins.aws_bedrock.utils import (
            get_bedrock_models_from_config,
        )

        models = get_bedrock_models_from_config()
        assert "bedrock-opus-4-7" in models
        assert "bedrock-haiku" in models
        assert "some-openai-model" not in models


# ============================================================================
# REGISTER_CALLBACKS TESTS
# ============================================================================


class TestHandleCustomCommand:
    """Test _handle_custom_command dispatch."""

    def test_returns_none_for_unknown_command(self):
        from code_puppy.plugins.aws_bedrock.register_callbacks import (
            _handle_custom_command,
        )

        result = _handle_custom_command("/foo", "foo")
        assert result is None

    def test_returns_true_for_known_command(self):
        from code_puppy.plugins.aws_bedrock.register_callbacks import (
            _handle_custom_command,
        )

        with patch(
            "code_puppy.plugins.aws_bedrock.register_callbacks._handle_bedrock_status"
        ):
            result = _handle_custom_command("/bedrock-status", "bedrock-status")
            assert result is True

    def test_returns_true_on_handler_error(self):
        """Error path should return True (command was handled, just failed)."""
        from code_puppy.plugins.aws_bedrock.register_callbacks import (
            _handle_custom_command,
        )

        with patch(
            "code_puppy.plugins.aws_bedrock.register_callbacks._handle_bedrock_status",
            side_effect=RuntimeError("boom"),
        ):
            result = _handle_custom_command("/bedrock-status", "bedrock-status")
            assert result is True


class TestCustomHelp:
    """Test _custom_help entries."""

    def test_help_entries(self):
        from code_puppy.plugins.aws_bedrock.register_callbacks import _custom_help

        entries = _custom_help()
        names = [e[0] for e in entries]
        assert "bedrock-status" in names
        assert "bedrock-setup" in names
        assert "bedrock-remove" in names

    def test_setup_help_not_interactive(self):
        from code_puppy.plugins.aws_bedrock.register_callbacks import _custom_help

        entries = dict(_custom_help())
        assert "interactive" not in entries["bedrock-setup"].lower()
        assert "wizard" not in entries["bedrock-setup"].lower()


# ============================================================================
# MODEL_UTILS SHARED HELPER TESTS
# ============================================================================


class TestSupportsAdaptiveThinking:
    """Test the shared supports_adaptive_thinking helper."""

    def test_opus_4_7_by_alias(self):
        from code_puppy.model_utils import supports_adaptive_thinking

        assert supports_adaptive_thinking("claude-opus-4-7") is True

    def test_opus_4_6_by_alias(self):
        from code_puppy.model_utils import supports_adaptive_thinking

        assert supports_adaptive_thinking("claude-opus-4-6") is True

    def test_sonnet_4_6_by_alias(self):
        from code_puppy.model_utils import supports_adaptive_thinking

        assert supports_adaptive_thinking("claude-sonnet-4-6") is True

    def test_haiku_not_adaptive(self):
        from code_puppy.model_utils import supports_adaptive_thinking

        assert supports_adaptive_thinking("claude-haiku-4-5") is False

    def test_bedrock_opus_via_actual_model_id(self):
        from code_puppy.model_utils import supports_adaptive_thinking

        # The alias doesn't contain the tag, but the actual_model_id does
        assert (
            supports_adaptive_thinking(
                "bedrock-opus", actual_model_id="us.anthropic.claude-opus-4-7"
            )
            is True
        )

    def test_unknown_model(self):
        from code_puppy.model_utils import supports_adaptive_thinking

        assert supports_adaptive_thinking("gpt-4o") is False


class TestGetDefaultExtendedThinking:
    """Test get_default_extended_thinking uses the shared helper."""

    def test_adaptive_for_opus(self):
        from code_puppy.model_utils import get_default_extended_thinking

        assert get_default_extended_thinking("claude-opus-4-7") == "adaptive"

    def test_enabled_for_haiku(self):
        from code_puppy.model_utils import get_default_extended_thinking

        assert get_default_extended_thinking("claude-haiku-4-5") == "enabled"

    def test_adaptive_via_actual_model_id(self):
        from code_puppy.model_utils import get_default_extended_thinking

        result = get_default_extended_thinking(
            "bedrock-opus", actual_model_id="us.anthropic.claude-opus-4-6-v1:0"
        )
        assert result == "adaptive"


class TestShouldUseThinkingSummary:
    """Test should_use_anthropic_thinking_summary."""

    def test_true_for_opus_4_7(self):
        from code_puppy.model_utils import should_use_anthropic_thinking_summary

        assert should_use_anthropic_thinking_summary("claude-opus-4-7") is True

    def test_false_for_opus_4_6(self):
        from code_puppy.model_utils import should_use_anthropic_thinking_summary

        assert should_use_anthropic_thinking_summary("claude-opus-4-6") is False

    def test_true_via_actual_model_id(self):
        from code_puppy.model_utils import should_use_anthropic_thinking_summary

        assert (
            should_use_anthropic_thinking_summary(
                "bedrock-opus", actual_model_id="us.anthropic.claude-opus-4-7"
            )
            is True
        )
