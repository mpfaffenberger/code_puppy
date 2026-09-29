"""GPT generation parsing and the capability gates built on it.

These replaced scattered ``"gpt-5.6" in name`` string checks so that GPT-6
(``gpt-6-astra``) and later inherit the Responses-API reasoning controls
without another round of find-and-replace.
"""

from unittest.mock import patch

import pytest

from code_puppy.config import model_supports_setting
from code_puppy.model_factory import ModelFactory, make_model_settings
from code_puppy.model_utils import (
    get_gpt_version,
    is_gpt_reasoning_model,
    supports_gpt_responses_controls,
)


class TestGetGptVersion:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("gpt-6-astra", (6, 0)),
            ("codex-gpt-6-astra", (6, 0)),
            ("gpt-5.6-sol", (5, 6)),
            ("boodleton-gpt-5.4-mini", (5, 4)),
            ("GPT-5.10-preview", (5, 10)),
            ("gpt-4o", (4, 0)),
            ("gpt-4.1", (4, 1)),
        ],
    )
    def test_parses_generation(self, name, expected):
        assert get_gpt_version(name) == expected

    @pytest.mark.parametrize("name", ["claude-opus-5", "gpt-oss-120b", "o3", ""])
    def test_non_gpt_is_none(self, name):
        assert get_gpt_version(name) is None

    def test_tuple_ordering_beats_float_ordering(self):
        # As floats 5.10 < 5.6; as generations 5.10 > 5.6.
        assert get_gpt_version("gpt-5.10") > get_gpt_version("gpt-5.6")


class TestGates:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("gpt-6-astra", True),
            ("gpt-5.6-luna", True),
            ("gpt-5.10", True),
            ("gpt-5.5", False),
            ("gpt-5.4-mini", False),
            ("gpt-4o", False),
            ("claude-opus-5", False),
        ],
    )
    def test_responses_controls(self, name, expected):
        assert supports_gpt_responses_controls(name) is expected

    def test_responses_controls_accepts_alias_plus_underlying(self):
        assert supports_gpt_responses_controls("luna-responses", "gpt-5.6-luna")
        assert not supports_gpt_responses_controls("luna-responses", None, "")

    @pytest.mark.parametrize(
        "name,expected",
        [("gpt-6-astra", True), ("gpt-5", True), ("gpt-4.1", False), ("o3", False)],
    )
    def test_reasoning_model(self, name, expected):
        assert is_gpt_reasoning_model(name) is expected

    def test_config_gate_for_reasoning_context_on_gpt6(self):
        assert model_supports_setting("codex-gpt-6-astra", "reasoning_context", {})
        assert model_supports_setting("codex-gpt-6-astra", "reasoning_mode", {})
        assert not model_supports_setting("codex-gpt-5.5", "reasoning_mode", {})


def test_gpt6_astra_oauth_gets_full_responses_reasoning_settings():
    """The exact entry the chatgpt_oauth plugin writes must light everything up."""
    config = {
        "codex-gpt-6-astra": {
            "type": "chatgpt_oauth",
            "name": "gpt-6-astra",
            "context_length": 258_400,
            "supported_settings": [
                "reasoning_effort",
                "summary",
                "verbosity",
                "reasoning_context",
                "reasoning_mode",
            ],
            "supports_xhigh_reasoning": True,
            "supports_max_reasoning": True,
        }
    }
    with (
        patch.object(ModelFactory, "load_config", return_value=config),
        patch("code_puppy.config.get_custom_model_settings", return_value={}),
    ):
        settings = make_model_settings("codex-gpt-6-astra", max_tokens=4096)

    assert settings["openai_reasoning_effort"] == "medium"
    assert settings["openai_reasoning_summary"] == "auto"
    assert settings["openai_reasoning_context"] == "all_turns"
    assert settings["openai_reasoning_mode"] == "standard"
