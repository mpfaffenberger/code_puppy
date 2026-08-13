"""Coverage tests for add_model_menu.py - exercises all uncovered code paths."""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from code_puppy.command_line.add_model_menu import (
    AddModelMenu,
    derive_provider_identity,
    interactive_model_picker,
)
from code_puppy.models_dev_parser import ModelInfo, ProviderInfo


def _make_menu_with_providers(providers=None, models=None):
    """Create an AddModelMenu with mocked registry."""
    with patch("code_puppy.command_line.add_model_menu.ModelsDevRegistry") as mock_cls:
        mock_reg = MagicMock()
        mock_reg.get_providers.return_value = providers or [_make_provider()]
        mock_reg.get_models.return_value = models or []
        mock_cls.return_value = mock_reg
        menu = AddModelMenu()
    return menu


def _make_model(
    provider_id="openai",
    model_id="gpt-4",
    name="GPT-4",
    tool_call=True,
    reasoning=False,
    temperature=True,
    structured_output=False,
    attachment=False,
    cost_input=0.00003,
    cost_output=0.00006,
    cost_cache_read=None,
    context_length=128000,
    max_output=4096,
    input_modalities=None,
    output_modalities=None,
    knowledge=None,
    release_date=None,
    open_weights=False,
):
    return ModelInfo(
        provider_id=provider_id,
        model_id=model_id,
        name=name,
        tool_call=tool_call,
        temperature=temperature,
        structured_output=structured_output,
        attachment=attachment,
        reasoning=reasoning,
        cost_input=cost_input,
        cost_output=cost_output,
        cost_cache_read=cost_cache_read,
        context_length=context_length,
        max_output=max_output,
        input_modalities=input_modalities or ["text"],
        output_modalities=output_modalities or ["text"],
        knowledge=knowledge,
        release_date=release_date,
        open_weights=open_weights,
    )


def _make_provider(
    pid="openai",
    name="OpenAI",
    env=None,
    api="https://api.openai.com/v1",
    model_count=2,
    doc=None,
):
    p = MagicMock(spec=ProviderInfo)
    p.id = pid
    p.name = name
    p.env = env if env is not None else ["OPENAI_API_KEY"]
    p.api = api
    p.model_count = model_count
    p.doc = doc
    return p


class TestAddCurrentModel:
    def test_regular_model(self):
        p = _make_provider()
        m = _make_model()
        menu = _make_menu_with_providers()
        menu.view_mode = "models"
        menu.current_provider = p
        menu.current_models = [m]
        menu.selected_model_idx = 0
        menu._add_current_model()
        assert menu.result == "pending_credentials"
        assert menu.pending_model == m

    def test_unsupported_provider(self):
        p = _make_provider(pid="amazon-bedrock")
        menu = _make_menu_with_providers()
        menu.current_provider = p
        menu._add_current_model()
        assert menu.result == "unsupported"


class TestAddModelToExtraConfig:
    def test_add_model_duplicate(self):
        menu = _make_menu_with_providers()
        m = _make_model()
        p = _make_provider()
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "extra_models.json")
            with open(path, "w") as f:
                json.dump({"openai-gpt-4": {}}, f)
            with patch(
                "code_puppy.command_line.add_model_menu.EXTRA_MODELS_FILE", path
            ):
                result = menu._add_model_to_extra_config(m, p)
            assert result is True

    def test_add_model_invalid_json(self):
        menu = _make_menu_with_providers()
        m = _make_model()
        p = _make_provider()
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "extra_models.json")
            with open(path, "w") as f:
                f.write("not json")
            with patch(
                "code_puppy.command_line.add_model_menu.EXTRA_MODELS_FILE", path
            ):
                result = menu._add_model_to_extra_config(m, p)
            assert result is False

    def test_add_model_list_instead_of_dict(self):
        menu = _make_menu_with_providers()
        m = _make_model()
        p = _make_provider()
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "extra_models.json")
            with open(path, "w") as f:
                json.dump(["not", "a", "dict"], f)
            with patch(
                "code_puppy.command_line.add_model_menu.EXTRA_MODELS_FILE", path
            ):
                result = menu._add_model_to_extra_config(m, p)
            assert result is False

    def test_add_model_success(self):
        menu = _make_menu_with_providers()
        m = _make_model()
        p = _make_provider()
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "extra_models.json")
            with patch(
                "code_puppy.command_line.add_model_menu.EXTRA_MODELS_FILE", path
            ):
                result = menu._add_model_to_extra_config(m, p)
            assert result is True
            with open(path) as f:
                data = json.load(f)
            assert "openai-gpt-4" in data

    def test_add_model_write_error(self):
        menu = _make_menu_with_providers()
        m = _make_model()
        p = _make_provider()
        with patch(
            "code_puppy.command_line.add_model_menu.EXTRA_MODELS_FILE",
            "/nonexistent/path/extra.json",
        ):
            result = menu._add_model_to_extra_config(m, p)
        assert result is False


class TestBuildModelConfig:
    def test_anthropic_provider(self):
        menu = _make_menu_with_providers()
        m = _make_model(provider_id="anthropic", model_id="claude-3")
        p = _make_provider(pid="anthropic", name="Anthropic", env=["ANTHROPIC_API_KEY"])
        config = menu._build_model_config(m, p)
        assert config["type"] == "anthropic"
        assert config["provider"] == "anthropic"
        assert "extended_thinking" in config["supported_settings"]

    def test_custom_openai_provider_fallback_endpoint(self):
        menu = _make_menu_with_providers()
        m = _make_model(provider_id="groq", model_id="llama-3")
        p = _make_provider(pid="groq", name="Groq", api="N/A", env=["GROQ_API_KEY"])
        config = menu._build_model_config(m, p)
        assert config["custom_endpoint"]["url"] == "https://api.groq.com/openai/v1"

    def test_custom_openai_provider_with_api_url(self):
        menu = _make_menu_with_providers()
        m = _make_model(provider_id="groq", model_id="llama-3")
        p = _make_provider(
            pid="groq",
            name="Groq",
            api="https://api.groq.com/openai/v1",
            env=["GROQ_API_KEY"],
        )
        config = menu._build_model_config(m, p)
        assert config["type"] == "custom_openai"
        assert config["provider"] == "groq"
        assert "custom_endpoint" in config
        assert config["custom_endpoint"]["url"] == "https://api.groq.com/openai/v1"

    def test_gpt5_codex_model_settings(self):
        menu = _make_menu_with_providers()
        m = _make_model(provider_id="openai", model_id="codex-gpt-5")
        p = _make_provider(pid="openai")
        config = menu._build_model_config(m, p)
        assert "reasoning_effort" in config["supported_settings"]
        assert "verbosity" not in config["supported_settings"]

    def test_gpt5_model_settings(self):
        menu = _make_menu_with_providers()
        m = _make_model(provider_id="openai", model_id="gpt-5.2")
        p = _make_provider(pid="openai")
        config = menu._build_model_config(m, p)
        assert "reasoning_effort" in config["supported_settings"]
        assert "verbosity" in config["supported_settings"]

    def test_kimi_for_coding_provider(self):
        menu = _make_menu_with_providers()
        m = _make_model(provider_id="kimi-for-coding", model_id="kimi-k2-thinking")
        p = _make_provider(pid="kimi-for-coding", name="Kimi")
        config = menu._build_model_config(m, p)
        assert config["name"] == "kimi-for-coding"

    def test_minimax_provider(self):
        menu = _make_menu_with_providers()
        m = _make_model(provider_id="minimax", model_id="minimax-01")
        p = _make_provider(
            pid="minimax",
            name="Minimax",
            api="https://api.minimax.io/anthropic/v1",
            env=["MINIMAX_API_KEY"],
        )
        config = menu._build_model_config(m, p)
        assert config["type"] == "custom_anthropic"
        assert config["provider"] == "minimax"
        assert config["custom_endpoint"]["url"] == "https://api.minimax.io/anthropic"


class TestCredentialHandling:
    def test_get_missing_env_vars(self):
        menu = _make_menu_with_providers()
        p = _make_provider(env=["MY_KEY", "EXISTING_KEY"])
        with patch.dict(os.environ, {"EXISTING_KEY": "value"}, clear=False):
            missing = menu._get_missing_env_vars(p)
        assert "MY_KEY" in missing
        assert "EXISTING_KEY" not in missing

    @patch("code_puppy.command_line.add_model_menu.safe_input")
    def test_prompt_for_credentials_cancelled(self, mock_input):
        mock_input.side_effect = KeyboardInterrupt
        menu = _make_menu_with_providers()
        p = _make_provider(env=["MY_API_KEY"])
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MY_API_KEY", None)
            result = menu._prompt_for_credentials(p)
        assert result is False

    def test_prompt_for_credentials_none_missing(self):
        menu = _make_menu_with_providers()
        p = _make_provider(env=["EXISTING"])
        with patch.dict(os.environ, {"EXISTING": "val"}):
            result = menu._prompt_for_credentials(p)
        assert result is True

    @patch("code_puppy.command_line.add_model_menu.safe_input")
    @patch("code_puppy.command_line.add_model_menu.set_config_value")
    def test_prompt_for_credentials_provides_key(self, mock_set, mock_input):
        mock_input.return_value = "sk-test"
        menu = _make_menu_with_providers()
        p = _make_provider(env=["MY_API_KEY"])
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MY_API_KEY", None)
            result = menu._prompt_for_credentials(p)
        assert result is True
        mock_set.assert_called()

    @patch("code_puppy.command_line.add_model_menu.safe_input")
    def test_prompt_for_credentials_skipped(self, mock_input):
        mock_input.return_value = ""
        menu = _make_menu_with_providers()
        p = _make_provider(env=["MY_API_KEY"])
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MY_API_KEY", None)
            result = menu._prompt_for_credentials(p)
        assert result is True


class TestCustomModel:
    def test_create_custom_model_info(self):
        menu = _make_menu_with_providers()
        menu.pending_provider = _make_provider()
        info = menu._create_custom_model_info("my-model", 200000)
        assert info.model_id == "my-model"
        assert info.context_length == 200000
        assert info.tool_call is True

    @pytest.mark.parametrize(
        "side_effect, expected",
        [
            # Each row reproduces one distinct input-parsing branch.
            (KeyboardInterrupt, None),
            (["my-model", ""], ("my-model", 128000)),
            ("", None),
            (["my-model", "abck"], ("my-model", 128000)),
            (["my-model", "abcm"], ("my-model", 128000)),
            (["my-model", "abc"], ("my-model", 128000)),
            (["my-model", "1m"], ("my-model", 1000000)),
            (["my-model", "200000"], ("my-model", 200000)),
            (["my-model", "128k"], ("my-model", 128000)),
        ],
    )
    @patch("code_puppy.command_line.add_model_menu.safe_input")
    def test_prompt_for_custom_model_var(self, mock_input, side_effect, expected):
        if isinstance(side_effect, type) and issubclass(side_effect, BaseException):
            mock_input.side_effect = side_effect
        elif side_effect == "":
            mock_input.return_value = ""
        else:
            mock_input.side_effect = side_effect
        menu = _make_menu_with_providers()
        menu.pending_provider = _make_provider()
        result = menu._prompt_for_custom_model()
        assert result == expected

    def test_prompt_for_custom_model_no_provider(self):
        menu = _make_menu_with_providers()
        menu.pending_provider = None
        result = menu._prompt_for_custom_model()
        assert result is None


class TestGetCurrentProviderModel:
    def test_get_current_model_no_provider(self):
        menu = _make_menu_with_providers()
        menu.view_mode = "models"
        menu.current_provider = None
        assert menu._get_current_model() is None

    def test_get_current_provider_out_of_range(self):
        menu = _make_menu_with_providers([_make_provider()])
        menu.selected_provider_idx = 99
        assert menu._get_current_provider() is None

    def test_is_custom_model_selected_providers_view(self):
        menu = _make_menu_with_providers()
        menu.view_mode = "providers"
        assert menu._is_custom_model_selected() is False


class TestInteractiveModelPicker:
    @patch("code_puppy.command_line.add_model_menu.AddModelMenu")
    def test_calls_run(self, mock_menu_cls):
        mock_menu = MagicMock()
        mock_menu.run.return_value = True
        mock_menu_cls.return_value = mock_menu
        result = interactive_model_picker()
        assert result is True


class TestNavigationMethods:
    def test_enter_provider_no_provider(self):
        menu = _make_menu_with_providers([])
        menu.providers = []
        menu.menu_control = MagicMock()
        menu.preview_control = MagicMock()
        menu._enter_provider()  # should not crash
        assert menu.view_mode == "providers"


class TestProviderIdentityHelpers:
    def test_derive_provider_identity_empty_provider_id(self):
        provider = _make_provider(pid="", name="Mystery Provider")
        assert derive_provider_identity(provider) == "unknown"
