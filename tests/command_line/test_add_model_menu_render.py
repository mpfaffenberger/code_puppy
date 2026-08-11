"""Rendering/run tests for add_model_menu.py (split from the coverage suite)."""

import os
import tempfile
from unittest.mock import MagicMock, patch


from code_puppy.command_line.add_model_menu import (
    AddModelMenu,
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


class TestRenderModelDetails:
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

    def test_models_view_no_provider(self):
        menu = _make_menu_with_providers()
        menu.view_mode = "models"
        menu.current_provider = None
        lines = menu._render_model_details()
        text = "".join(t for _, t in lines)
        assert "No model selected" in text

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

    def test_provider_view_no_provider(self):
        menu = _make_menu_with_providers([])
        menu.providers = []
        menu.view_mode = "providers"
        lines = menu._render_model_details()
        text = "".join(t for _, t in lines)
        assert "No provider selected" in text

    def test_provider_view_unsupported(self):
        p = _make_provider(pid="amazon-bedrock", name="Bedrock")
        menu = _make_menu_with_providers([p])
        menu.view_mode = "providers"
        lines = menu._render_model_details()
        text = "".join(t for _, t in lines)
        assert "UNSUPPORTED" in text

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


class TestRenderModelList:
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

    def test_render_no_provider(self):
        menu = _make_menu_with_providers()
        menu.view_mode = "models"
        menu.current_provider = None
        lines = menu._render_model_list()
        text = "".join(t for _, t in lines)
        assert "No provider selected" in text


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
