"""Coverage tests for add_model_menu.py - exercises all uncovered code paths."""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

from code_puppy.command_line.add_model_menu import (
    AddModelMenu,
    interactive_model_picker,
)
from code_puppy.models_dev_parser import ModelInfo, ProviderInfo


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
    p.env = env or ["OPENAI_API_KEY"]
    p.api = api
    p.model_count = model_count
    p.doc = doc
    return p


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


def _make_menu_with_providers(providers=None, models=None):
    """Create an AddModelMenu with mocked registry."""
    with patch("code_puppy.command_line.add_model_menu.ModelsDevRegistry") as mock_cls:
        mock_reg = MagicMock()
        mock_reg.get_providers.return_value = providers or [_make_provider()]
        mock_reg.get_models.return_value = models or []
        mock_cls.return_value = mock_reg
        menu = AddModelMenu()
    return menu


# --------------- _get_current_provider / _get_current_model ---------------


class TestGetCurrentProviderModel:
    def test_get_current_provider_valid(self):
        menu = _make_menu_with_providers(
            [_make_provider(), _make_provider(pid="anthropic", name="Anthropic")]
        )
        menu.selected_provider_idx = 1
        assert menu._get_current_provider().id == "anthropic"

    def test_get_current_provider_out_of_range(self):
        menu = _make_menu_with_providers([_make_provider()])
        menu.selected_provider_idx = 99
        assert menu._get_current_provider() is None

    def test_get_current_model_no_provider(self):
        menu = _make_menu_with_providers()
        menu.view_mode = "models"
        menu.current_provider = None
        assert menu._get_current_model() is None

    def test_get_current_model_valid(self):
        m = _make_model()
        menu = _make_menu_with_providers()
        menu.view_mode = "models"
        menu.current_provider = _make_provider()
        menu.current_models = [m]
        menu.selected_model_idx = 0
        assert menu._get_current_model() == m

    def test_get_current_model_custom_selected(self):
        m = _make_model()
        menu = _make_menu_with_providers()
        menu.view_mode = "models"
        menu.current_provider = _make_provider()
        menu.current_models = [m]
        menu.selected_model_idx = 1  # custom model index
        assert menu._get_current_model() is None

    def test_is_custom_model_selected(self):
        menu = _make_menu_with_providers()
        menu.view_mode = "models"
        menu.current_provider = _make_provider()
        menu.current_models = [_make_model()]
        menu.selected_model_idx = 1
        assert menu._is_custom_model_selected() is True
        menu.selected_model_idx = 0
        assert menu._is_custom_model_selected() is False

    def test_is_custom_model_selected_providers_view(self):
        menu = _make_menu_with_providers()
        menu.view_mode = "providers"
        assert menu._is_custom_model_selected() is False


# --------------- Render provider list ---------------


class TestRenderProviderList:
    def test_render_no_providers(self):
        menu = _make_menu_with_providers([])
        menu.providers = []
        lines = menu._render_provider_list()
        text = "".join(t for _, t in lines)
        assert "No providers" in text

    def test_render_with_providers(self):
        p1 = _make_provider(pid="openai", name="OpenAI")
        p2 = _make_provider(pid="amazon-bedrock", name="Bedrock")
        menu = _make_menu_with_providers([p1, p2])
        menu.selected_provider_idx = 0
        lines = menu._render_provider_list()
        text = "".join(t for _, t in lines)
        assert "OpenAI" in text
        assert "Bedrock" in text
        assert "Page" in text

    def test_render_unsupported_provider_dimmed(self):
        p = _make_provider(pid="amazon-bedrock", name="Bedrock")
        menu = _make_menu_with_providers([p])
        lines = menu._render_provider_list()
        styles = [s for s, _ in lines]
        assert any("dim" in s for s in styles)


# --------------- Render model list ---------------


class TestRenderModelList:
    def test_render_no_provider(self):
        menu = _make_menu_with_providers()
        menu.view_mode = "models"
        menu.current_provider = None
        lines = menu._render_model_list()
        text = "".join(t for _, t in lines)
        assert "No provider selected" in text

    def test_render_with_models(self):
        m = _make_model(name="GPT-4", tool_call=True, reasoning=True)
        # Create model with vision
        m2 = ModelInfo(
            provider_id="openai",
            model_id="gpt-4v",
            name="GPT-4V",
            tool_call=True,
            temperature=True,
            context_length=128000,
            max_output=4096,
            input_modalities=["text", "image"],
            output_modalities=["text"],
        )
        menu = _make_menu_with_providers()
        menu.view_mode = "models"
        menu.current_provider = _make_provider()
        menu.current_models = [m, m2]
        menu.selected_model_idx = 0
        lines = menu._render_model_list()
        text = "".join(t for _, t in lines)
        assert "GPT-4" in text
        assert "Custom model" in text

    def test_render_custom_model_selected(self):
        m = _make_model()
        menu = _make_menu_with_providers()
        menu.view_mode = "models"
        menu.current_provider = _make_provider()
        menu.current_models = [m]
        menu.selected_model_idx = 1  # custom
        lines = menu._render_model_list()
        text = "".join(t for _, t in lines)
        assert "Custom model" in text


# --------------- Render model details ---------------


class TestRenderModelDetails:
    def test_provider_view_no_provider(self):
        menu = _make_menu_with_providers([])
        menu.providers = []
        menu.view_mode = "providers"
        lines = menu._render_model_details()
        text = "".join(t for _, t in lines)
        assert "No provider selected" in text

    def test_provider_view_with_provider(self):
        p = _make_provider(doc="https://docs.openai.com")
        menu = _make_menu_with_providers([p])
        menu.view_mode = "providers"
        menu.selected_provider_idx = 0
        lines = menu._render_model_details()
        text = "".join(t for _, t in lines)
        assert "OpenAI" in text
        assert "OPENAI_API_KEY" in text
        assert "docs.openai.com" in text

    def test_provider_view_unsupported(self):
        p = _make_provider(pid="amazon-bedrock", name="Bedrock")
        menu = _make_menu_with_providers([p])
        menu.view_mode = "providers"
        lines = menu._render_model_details()
        text = "".join(t for _, t in lines)
        assert "UNSUPPORTED" in text

    def test_models_view_no_provider(self):
        menu = _make_menu_with_providers()
        menu.view_mode = "models"
        menu.current_provider = None
        lines = menu._render_model_details()
        text = "".join(t for _, t in lines)
        assert "No model selected" in text

    def test_models_view_custom_model(self):
        p = _make_provider()
        menu = _make_menu_with_providers()
        menu.view_mode = "models"
        menu.current_provider = p
        menu.current_models = [_make_model()]
        menu.selected_model_idx = 1  # custom
        lines = menu._render_model_details()
        text = "".join(t for _, t in lines)
        assert "Custom Model" in text
        assert "How it works" in text

    def test_models_view_custom_model_with_env(self):
        p = _make_provider(env=["MY_KEY"])
        menu = _make_menu_with_providers()
        menu.view_mode = "models"
        menu.current_provider = p
        menu.current_models = []
        menu.selected_model_idx = 0  # custom (only option)
        lines = menu._render_model_details()
        text = "".join(t for _, t in lines)
        assert "MY_KEY" in text

    def test_models_view_with_model(self):
        m = _make_model(
            cost_input=0.00003,
            cost_output=0.00006,
            cost_cache_read=0.00001,
            context_length=128000,
            max_output=4096,
            input_modalities=["text", "image"],
            output_modalities=["text"],
            knowledge="2024-04",
            release_date="2024-04-01",
            open_weights=True,
        )
        menu = _make_menu_with_providers()
        menu.view_mode = "models"
        menu.current_provider = _make_provider()
        menu.current_models = [m]
        menu.selected_model_idx = 0
        lines = menu._render_model_details()
        text = "".join(t for _, t in lines)
        assert "GPT-4" in text
        assert "Vision" in text
        assert "Capabilities" in text
        assert "Pricing" in text
        assert "Context" in text
        assert "Modalities" in text
        assert "Metadata" in text
        assert "Knowledge" in text
        assert "Released" in text
        assert "Open Weights" in text

    def test_models_view_no_tool_call_warning(self):
        m = _make_model(tool_call=False)
        menu = _make_menu_with_providers()
        menu.view_mode = "models"
        menu.current_provider = _make_provider()
        menu.current_models = [m]
        menu.selected_model_idx = 0
        lines = menu._render_model_details()
        text = "".join(t for _, t in lines)
        assert "NO TOOL CALLING" in text

    def test_models_view_no_pricing(self):
        m = _make_model(cost_input=None, cost_output=None)
        menu = _make_menu_with_providers()
        menu.view_mode = "models"
        menu.current_provider = _make_provider()
        menu.current_models = [m]
        menu.selected_model_idx = 0
        lines = menu._render_model_details()
        text = "".join(t for _, t in lines)
        assert "not available" in text

    def test_models_view_no_model_selected(self):
        """When selected_model_idx is out of range and not custom."""
        menu = _make_menu_with_providers()
        menu.view_mode = "models"
        menu.current_provider = _make_provider()
        menu.current_models = [_make_model()]
        menu.selected_model_idx = 5  # out of range, not == len(models)
        lines = menu._render_model_details()
        text = "".join(t for _, t in lines)
        assert "No model selected" in text


# --------------- _add_model_to_extra_config ---------------


class TestAddModelToExtraConfig:
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
            assert result is True  # Not an error

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


# --------------- _build_model_config ---------------


class TestBuildModelConfig:
    def test_openai_provider(self):
        menu = _make_menu_with_providers()
        m = _make_model(provider_id="openai", model_id="gpt-4")
        p = _make_provider(pid="openai")
        config = menu._build_model_config(m, p)
        assert config["type"] == "openai"
        assert config["name"] == "gpt-4"
        assert "custom_endpoint" not in config

    def test_anthropic_provider(self):
        menu = _make_menu_with_providers()
        m = _make_model(provider_id="anthropic", model_id="claude-3")
        p = _make_provider(pid="anthropic", name="Anthropic", env=["ANTHROPIC_API_KEY"])
        config = menu._build_model_config(m, p)
        assert config["type"] == "anthropic"
        assert "extended_thinking" in config["supported_settings"]

    def test_google_provider(self):
        menu = _make_menu_with_providers()
        m = _make_model(provider_id="google", model_id="gemini-1.5")
        p = _make_provider(pid="google", name="Google")
        config = menu._build_model_config(m, p)
        assert config["type"] == "gemini"

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
        assert "custom_endpoint" in config
        assert config["custom_endpoint"]["url"] == "https://api.groq.com/openai/v1"

    def test_custom_openai_provider_fallback_endpoint(self):
        menu = _make_menu_with_providers()
        m = _make_model(provider_id="groq", model_id="llama-3")
        p = _make_provider(pid="groq", name="Groq", api="N/A", env=["GROQ_API_KEY"])
        config = menu._build_model_config(m, p)
        assert config["custom_endpoint"]["url"] == "https://api.groq.com/openai/v1"

    def test_custom_openai_no_api_no_fallback(self):
        menu = _make_menu_with_providers()
        m = _make_model(provider_id="unknown_provider", model_id="model-x")
        p = _make_provider(pid="unknown_provider", name="Unknown", api=None, env=[])
        config = menu._build_model_config(m, p)
        assert config["type"] == "custom_openai"
        assert "custom_endpoint" not in config

    def test_gpt5_model_settings(self):
        menu = _make_menu_with_providers()
        m = _make_model(provider_id="openai", model_id="gpt-5.2")
        p = _make_provider(pid="openai")
        config = menu._build_model_config(m, p)
        assert "reasoning_effort" in config["supported_settings"]
        assert "verbosity" in config["supported_settings"]

    def test_gpt5_codex_model_settings(self):
        menu = _make_menu_with_providers()
        m = _make_model(provider_id="openai", model_id="codex-gpt-5")
        p = _make_provider(pid="openai")
        config = menu._build_model_config(m, p)
        assert "reasoning_effort" in config["supported_settings"]
        assert "verbosity" not in config["supported_settings"]

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
        assert config["custom_endpoint"]["url"] == "https://api.minimax.io/anthropic"

    def test_kimi_for_coding_provider(self):
        menu = _make_menu_with_providers()
        m = _make_model(provider_id="kimi-for-coding", model_id="kimi-k2-thinking")
        p = _make_provider(pid="kimi-for-coding", name="Kimi")
        config = menu._build_model_config(m, p)
        assert config["name"] == "kimi-for-coding"

    def test_context_length_included(self):
        menu = _make_menu_with_providers()
        m = _make_model(context_length=200000)
        p = _make_provider()
        config = menu._build_model_config(m, p)
        assert config["context_length"] == 200000

    def test_zero_context_length_excluded(self):
        menu = _make_menu_with_providers()
        m = _make_model(context_length=0)
        p = _make_provider()
        config = menu._build_model_config(m, p)
        assert "context_length" not in config


# --------------- Navigation methods ---------------


class TestNavigationMethods:
    def test_enter_provider(self):
        p = _make_provider()
        models = [_make_model()]
        with patch(
            "code_puppy.command_line.add_model_menu.ModelsDevRegistry"
        ) as mock_cls:
            mock_reg = MagicMock()
            mock_reg.get_providers.return_value = [p]
            mock_reg.get_models.return_value = models
            mock_cls.return_value = mock_reg
            menu = AddModelMenu()
        menu.menu_control = MagicMock()
        menu.preview_control = MagicMock()
        menu._enter_provider()
        assert menu.view_mode == "models"
        assert menu.current_provider == p

    def test_enter_provider_no_provider(self):
        menu = _make_menu_with_providers([])
        menu.providers = []
        menu.menu_control = MagicMock()
        menu.preview_control = MagicMock()
        menu._enter_provider()  # should not crash
        assert menu.view_mode == "providers"

    def test_go_back_to_providers(self):
        menu = _make_menu_with_providers()
        menu.view_mode = "models"
        menu.current_provider = _make_provider()
        menu.menu_control = MagicMock()
        menu.preview_control = MagicMock()
        menu._go_back_to_providers()
        assert menu.view_mode == "providers"
        assert menu.current_provider is None


# --------------- _add_current_model ---------------


class TestAddCurrentModel:
    def test_no_provider(self):
        menu = _make_menu_with_providers()
        menu.current_provider = None
        menu._add_current_model()
        assert menu.result is None

    def test_unsupported_provider(self):
        p = _make_provider(pid="amazon-bedrock")
        menu = _make_menu_with_providers()
        menu.current_provider = p
        menu._add_current_model()
        assert menu.result == "unsupported"

    def test_custom_model(self):
        p = _make_provider()
        menu = _make_menu_with_providers()
        menu.view_mode = "models"
        menu.current_provider = p
        menu.current_models = [_make_model()]
        menu.selected_model_idx = 1  # custom
        menu._add_current_model()
        assert menu.result == "pending_custom_model"

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


# --------------- Credential handling ---------------


class TestCredentialHandling:
    def test_get_missing_env_vars(self):
        menu = _make_menu_with_providers()
        p = _make_provider(env=["MY_KEY", "EXISTING_KEY"])
        with patch.dict(os.environ, {"EXISTING_KEY": "value"}, clear=False):
            missing = menu._get_missing_env_vars(p)
        assert "MY_KEY" in missing
        assert "EXISTING_KEY" not in missing

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

    @patch("code_puppy.command_line.add_model_menu.safe_input")
    def test_prompt_for_credentials_cancelled(self, mock_input):
        mock_input.side_effect = KeyboardInterrupt
        menu = _make_menu_with_providers()
        p = _make_provider(env=["MY_API_KEY"])
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MY_API_KEY", None)
            result = menu._prompt_for_credentials(p)
        assert result is False


# --------------- Custom model ---------------


class TestCustomModel:
    def test_create_custom_model_info(self):
        menu = _make_menu_with_providers()
        menu.pending_provider = _make_provider()
        info = menu._create_custom_model_info("my-model", 200000)
        assert info.model_id == "my-model"
        assert info.context_length == 200000
        assert info.tool_call is True

    @patch("code_puppy.command_line.add_model_menu.safe_input")
    def test_prompt_for_custom_model_success(self, mock_input):
        mock_input.side_effect = ["my-model", "128k"]
        menu = _make_menu_with_providers()
        menu.pending_provider = _make_provider()
        result = menu._prompt_for_custom_model()
        assert result == ("my-model", 128000)

    @patch("code_puppy.command_line.add_model_menu.safe_input")
    def test_prompt_for_custom_model_m_suffix(self, mock_input):
        mock_input.side_effect = ["my-model", "1m"]
        menu = _make_menu_with_providers()
        menu.pending_provider = _make_provider()
        result = menu._prompt_for_custom_model()
        assert result == ("my-model", 1000000)

    @patch("code_puppy.command_line.add_model_menu.safe_input")
    def test_prompt_for_custom_model_plain_number(self, mock_input):
        mock_input.side_effect = ["my-model", "200000"]
        menu = _make_menu_with_providers()
        menu.pending_provider = _make_provider()
        result = menu._prompt_for_custom_model()
        assert result == ("my-model", 200000)

    @patch("code_puppy.command_line.add_model_menu.safe_input")
    def test_prompt_for_custom_model_default_context(self, mock_input):
        mock_input.side_effect = ["my-model", ""]
        menu = _make_menu_with_providers()
        menu.pending_provider = _make_provider()
        result = menu._prompt_for_custom_model()
        assert result == ("my-model", 128000)

    @patch("code_puppy.command_line.add_model_menu.safe_input")
    def test_prompt_for_custom_model_invalid_k(self, mock_input):
        mock_input.side_effect = ["my-model", "abck"]
        menu = _make_menu_with_providers()
        menu.pending_provider = _make_provider()
        result = menu._prompt_for_custom_model()
        assert result == ("my-model", 128000)

    @patch("code_puppy.command_line.add_model_menu.safe_input")
    def test_prompt_for_custom_model_invalid_m(self, mock_input):
        mock_input.side_effect = ["my-model", "abcm"]
        menu = _make_menu_with_providers()
        menu.pending_provider = _make_provider()
        result = menu._prompt_for_custom_model()
        assert result == ("my-model", 128000)

    @patch("code_puppy.command_line.add_model_menu.safe_input")
    def test_prompt_for_custom_model_invalid_number(self, mock_input):
        mock_input.side_effect = ["my-model", "abc"]
        menu = _make_menu_with_providers()
        menu.pending_provider = _make_provider()
        result = menu._prompt_for_custom_model()
        assert result == ("my-model", 128000)

    @patch("code_puppy.command_line.add_model_menu.safe_input")
    def test_prompt_for_custom_model_empty_name(self, mock_input):
        mock_input.return_value = ""
        menu = _make_menu_with_providers()
        menu.pending_provider = _make_provider()
        result = menu._prompt_for_custom_model()
        assert result is None

    @patch("code_puppy.command_line.add_model_menu.safe_input")
    def test_prompt_for_custom_model_cancelled(self, mock_input):
        mock_input.side_effect = KeyboardInterrupt
        menu = _make_menu_with_providers()
        menu.pending_provider = _make_provider()
        result = menu._prompt_for_custom_model()
        assert result is None

    def test_prompt_for_custom_model_no_provider(self):
        menu = _make_menu_with_providers()
        menu.pending_provider = None
        result = menu._prompt_for_custom_model()
        assert result is None


# --------------- _get_env_var_hint ---------------


class TestGetEnvVarHint:
    def test_known_vars(self):
        menu = _make_menu_with_providers()
        assert "openai.com" in menu._get_env_var_hint("OPENAI_API_KEY")
        assert "anthropic" in menu._get_env_var_hint("ANTHROPIC_API_KEY").lower()

    def test_unknown_var(self):
        menu = _make_menu_with_providers()
        assert menu._get_env_var_hint("UNKNOWN_VAR") == ""


# --------------- run() method ---------------


class TestRun:
    @patch("code_puppy.command_line.add_model_menu.set_awaiting_user_input")
    @patch("code_puppy.command_line.add_model_menu.Application")
    def test_run_no_registry(self, mock_app, mock_set_await):
        menu = _make_menu_with_providers([])
        menu.providers = []
        menu.registry = None
        result = menu.run()
        assert result is False

    @patch("code_puppy.command_line.add_model_menu.set_awaiting_user_input")
    @patch("code_puppy.command_line.add_model_menu.Application")
    @patch("sys.stdout")
    @patch("time.sleep")
    def test_run_exit_no_result(
        self, mock_sleep, mock_stdout, mock_app_cls, mock_set_await
    ):
        menu = _make_menu_with_providers([_make_provider()])
        mock_app = MagicMock()
        mock_app_cls.return_value = mock_app
        menu.result = None
        result = menu.run()
        assert result is False

    @patch("code_puppy.command_line.add_model_menu.set_awaiting_user_input")
    @patch("code_puppy.command_line.add_model_menu.Application")
    @patch("sys.stdout")
    @patch("time.sleep")
    def test_run_unsupported_result(
        self, mock_sleep, mock_stdout, mock_app_cls, mock_set_await
    ):
        menu = _make_menu_with_providers(
            [_make_provider(pid="amazon-bedrock", name="Bedrock")]
        )
        mock_app = MagicMock()
        mock_app_cls.return_value = mock_app

        # Simulate selecting unsupported provider
        def run_side_effect(**kwargs):
            menu.result = "unsupported"
            menu.current_provider = menu.providers[0]

        mock_app.run.side_effect = run_side_effect
        result = menu.run()
        assert result is False

    @patch("code_puppy.command_line.add_model_menu.set_awaiting_user_input")
    @patch("code_puppy.command_line.add_model_menu.Application")
    @patch("code_puppy.command_line.add_model_menu.safe_input")
    @patch("sys.stdout")
    @patch("time.sleep")
    def test_run_pending_credentials_success(
        self, mock_sleep, mock_stdout, mock_input, mock_app_cls, mock_set_await
    ):
        m = _make_model()
        p = _make_provider(env=[])
        menu = _make_menu_with_providers([p])
        mock_app = MagicMock()
        mock_app_cls.return_value = mock_app

        def run_side_effect(**kwargs):
            menu.result = "pending_credentials"
            menu.pending_model = m
            menu.pending_provider = p

        mock_app.run.side_effect = run_side_effect

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "extra_models.json")
            with patch(
                "code_puppy.command_line.add_model_menu.EXTRA_MODELS_FILE", path
            ):
                result = menu.run()
        assert result is True

    @patch("code_puppy.command_line.add_model_menu.set_awaiting_user_input")
    @patch("code_puppy.command_line.add_model_menu.Application")
    @patch("code_puppy.command_line.add_model_menu.safe_input")
    @patch("sys.stdout")
    @patch("time.sleep")
    def test_run_pending_credentials_no_tool_call_confirm(
        self, mock_sleep, mock_stdout, mock_input, mock_app_cls, mock_set_await
    ):
        m = _make_model(tool_call=False)
        p = _make_provider(env=[])
        menu = _make_menu_with_providers([p])
        mock_app = MagicMock()
        mock_app_cls.return_value = mock_app
        mock_input.return_value = "y"

        def run_side_effect(**kwargs):
            menu.result = "pending_credentials"
            menu.pending_model = m
            menu.pending_provider = p

        mock_app.run.side_effect = run_side_effect

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "extra_models.json")
            with patch(
                "code_puppy.command_line.add_model_menu.EXTRA_MODELS_FILE", path
            ):
                result = menu.run()
        assert result is True

    @patch("code_puppy.command_line.add_model_menu.set_awaiting_user_input")
    @patch("code_puppy.command_line.add_model_menu.Application")
    @patch("code_puppy.command_line.add_model_menu.safe_input")
    @patch("sys.stdout")
    @patch("time.sleep")
    def test_run_pending_credentials_no_tool_call_decline(
        self, mock_sleep, mock_stdout, mock_input, mock_app_cls, mock_set_await
    ):
        m = _make_model(tool_call=False)
        p = _make_provider(env=[])
        menu = _make_menu_with_providers([p])
        mock_app = MagicMock()
        mock_app_cls.return_value = mock_app
        mock_input.return_value = "n"

        def run_side_effect(**kwargs):
            menu.result = "pending_credentials"
            menu.pending_model = m
            menu.pending_provider = p

        mock_app.run.side_effect = run_side_effect
        result = menu.run()
        assert result is False

    @patch("code_puppy.command_line.add_model_menu.set_awaiting_user_input")
    @patch("code_puppy.command_line.add_model_menu.Application")
    @patch("code_puppy.command_line.add_model_menu.safe_input")
    @patch("sys.stdout")
    @patch("time.sleep")
    def test_run_pending_credentials_no_tool_call_interrupt(
        self, mock_sleep, mock_stdout, mock_input, mock_app_cls, mock_set_await
    ):
        m = _make_model(tool_call=False)
        p = _make_provider(env=[])
        menu = _make_menu_with_providers([p])
        mock_app = MagicMock()
        mock_app_cls.return_value = mock_app
        mock_input.side_effect = KeyboardInterrupt

        def run_side_effect(**kwargs):
            menu.result = "pending_credentials"
            menu.pending_model = m
            menu.pending_provider = p

        mock_app.run.side_effect = run_side_effect
        result = menu.run()
        assert result is False

    @patch("code_puppy.command_line.add_model_menu.set_awaiting_user_input")
    @patch("code_puppy.command_line.add_model_menu.Application")
    @patch("code_puppy.command_line.add_model_menu.safe_input")
    @patch("sys.stdout")
    @patch("time.sleep")
    def test_run_pending_custom_model_success(
        self, mock_sleep, mock_stdout, mock_input, mock_app_cls, mock_set_await
    ):
        p = _make_provider(env=[])
        menu = _make_menu_with_providers([p])
        mock_app = MagicMock()
        mock_app_cls.return_value = mock_app
        mock_input.side_effect = ["my-model", "128000"]

        def run_side_effect(**kwargs):
            menu.result = "pending_custom_model"
            menu.pending_provider = p

        mock_app.run.side_effect = run_side_effect

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "extra_models.json")
            with patch(
                "code_puppy.command_line.add_model_menu.EXTRA_MODELS_FILE", path
            ):
                result = menu.run()
        assert result is True

    @patch("code_puppy.command_line.add_model_menu.set_awaiting_user_input")
    @patch("code_puppy.command_line.add_model_menu.Application")
    @patch("code_puppy.command_line.add_model_menu.safe_input")
    @patch("sys.stdout")
    @patch("time.sleep")
    def test_run_pending_custom_model_cancelled(
        self, mock_sleep, mock_stdout, mock_input, mock_app_cls, mock_set_await
    ):
        p = _make_provider(env=[])
        menu = _make_menu_with_providers([p])
        mock_app = MagicMock()
        mock_app_cls.return_value = mock_app
        mock_input.return_value = ""  # empty name cancels

        def run_side_effect(**kwargs):
            menu.result = "pending_custom_model"
            menu.pending_provider = p

        mock_app.run.side_effect = run_side_effect
        result = menu.run()
        assert result is False


# --------------- interactive_model_picker ---------------


class TestInteractiveModelPicker:
    @patch("code_puppy.command_line.add_model_menu.AddModelMenu")
    def test_calls_run(self, mock_menu_cls):
        mock_menu = MagicMock()
        mock_menu.run.return_value = True
        mock_menu_cls.return_value = mock_menu
        result = interactive_model_picker()
        assert result is True


# --------------- Navigation hints ---------------


class TestRenderNavigationHints:
    def test_providers_view_hints(self):
        menu = _make_menu_with_providers([_make_provider()])
        menu.view_mode = "providers"
        lines = []
        menu._render_navigation_hints(lines)
        text = "".join(t for _, t in lines)
        assert "Navigate" in text
        assert "Select" in text

    def test_models_view_hints(self):
        menu = _make_menu_with_providers()
        menu.view_mode = "models"
        lines = []
        menu._render_navigation_hints(lines)
        text = "".join(t for _, t in lines)
        assert "Add Model" in text
        assert "Back" in text


# --------------- _initialize_registry error paths ---------------


class TestInitializeRegistryErrors:
    @patch("code_puppy.command_line.add_model_menu.ModelsDevRegistry")
    def test_empty_providers(self, mock_cls):
        mock_reg = MagicMock()
        mock_reg.get_providers.return_value = []
        mock_cls.return_value = mock_reg
        menu = AddModelMenu()
        assert menu.providers == []

    @patch(
        "code_puppy.command_line.add_model_menu.ModelsDevRegistry",
        side_effect=FileNotFoundError("missing"),
    )
    def test_file_not_found(self, mock_cls):
        menu = AddModelMenu()
        assert menu.providers == []

    @patch(
        "code_puppy.command_line.add_model_menu.ModelsDevRegistry",
        side_effect=RuntimeError("boom"),
    )
    def test_general_exception(self, mock_cls):
        menu = AddModelMenu()
        assert menu.providers == []


# --------------- Render provider list - unsupported selected ---------------


class TestRenderProviderListUnsupportedSelected:
    def test_unsupported_provider_selected(self):
        p = _make_provider(pid="amazon-bedrock", name="Amazon Bedrock")
        menu = _make_menu_with_providers([p])
        menu.view_mode = "providers"
        menu.selected_provider_idx = 0
        lines = menu._render_provider_list()
        text = "".join(t for _, t in lines)
        assert "Bedrock" in text

    def test_multiple_providers_non_selected(self):
        """Cover the else branch for non-selected, non-unsupported provider."""
        p1 = _make_provider(pid="openai", name="OpenAI")
        p2 = _make_provider(pid="anthropic", name="Anthropic")
        menu = _make_menu_with_providers([p1, p2])
        menu.view_mode = "providers"
        menu.selected_provider_idx = 0  # p1 selected, p2 not
        lines = menu._render_provider_list()
        text = "".join(t for _, t in lines)
        assert "OpenAI" in text
        assert "Anthropic" in text
