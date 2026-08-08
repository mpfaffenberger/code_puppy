"""Tests for the theme-style /model switcher plugin."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from code_puppy.plugins.model_switcher.picker import (
    MODEL_PAGE_SIZE,
    ModelSwitcherMenu,
    _context_label,
    _provider_label,
)

_FAKE_MODELS = {
    "gpt-5": {
        "type": "openai",
        "description": "OpenAI flagship model",
        "context_length": 400000,
        "api_key": "$OPENAI_API_KEY",
    },
    "claude-sonnet-4.7": {
        "type": "anthropic",
        "description": "Anthropic Sonnet",
        "context_length": 1000000,
        "api_key": "$ANTHROPIC_API_KEY",
    },
    "gemini-3-pro": {"type": "gemini", "context_length": 1048576},
    "ollama-gemma4": {"type": "ollama", "name": "gemma4:latest"},
}

_MANY_MODELS = {f"model-{i:02d}": {"type": "openai"} for i in range(40)}


class TestCommandRegistration:
    def test_model_command_is_plugin_override(self):
        from code_puppy.command_line.command_registry import get_command

        cmd = get_command("model")
        assert cmd is not None
        assert (
            cmd.handler.__module__
            == "code_puppy.plugins.model_switcher.register_callbacks"
        )
        assert get_command("m") is cmd

    def test_show_emits_active_model(self):
        from code_puppy.plugins.model_switcher.register_callbacks import _handle_model

        with (
            patch(
                "code_puppy.command_line.model_picker_completion.get_active_model",
                return_value="gpt-5",
            ),
            patch("code_puppy.messaging.emit_info") as emit_info,
        ):
            assert _handle_model("/model show") is True
            emit_info.assert_called_once_with("Active model: gpt-5")

    def test_bare_model_runs_picker_and_applies(self):
        from code_puppy.plugins.model_switcher.register_callbacks import _handle_model

        with (
            patch("concurrent.futures.ThreadPoolExecutor") as pool,
            patch("code_puppy.model_switching.set_model_and_reload_agent") as set_model,
            patch("code_puppy.messaging.emit_success") as emit_success,
        ):
            mock_future = MagicMock()
            mock_future.result.return_value = "claude-sonnet-4.7"
            pool.return_value.__enter__ = MagicMock(return_value=pool.return_value)
            pool.return_value.__exit__ = MagicMock(return_value=False)
            pool.return_value.submit.return_value = mock_future

            assert _handle_model("/model") is True
            set_model.assert_called_once_with("claude-sonnet-4.7")
            emit_success.assert_called_once()

    def test_bare_model_cancelled(self):
        from code_puppy.plugins.model_switcher.register_callbacks import _handle_model

        with (
            patch("concurrent.futures.ThreadPoolExecutor") as pool,
            patch("code_puppy.messaging.emit_warning") as emit_warning,
        ):
            mock_future = MagicMock()
            mock_future.result.return_value = None
            pool.return_value.__enter__ = MagicMock(return_value=pool.return_value)
            pool.return_value.__exit__ = MagicMock(return_value=False)
            pool.return_value.submit.return_value = mock_future

            assert _handle_model("/model") is True
            emit_warning.assert_called_once()

    def test_by_name_sets_model(self):
        from code_puppy.plugins.model_switcher.register_callbacks import _handle_model

        with (
            patch(
                "code_puppy.command_line.model_picker_completion.update_model_in_input",
                return_value="",
            ),
            patch(
                "code_puppy.command_line.model_picker_completion.get_active_model",
                return_value="gpt-5",
            ),
            patch("code_puppy.messaging.emit_success") as emit_success,
        ):
            assert _handle_model("/model gpt-5") is True
            emit_success.assert_called_once()

    def test_unknown_model_lists_available(self):
        from code_puppy.plugins.model_switcher.register_callbacks import _handle_model

        with (
            patch(
                "code_puppy.command_line.model_picker_completion.update_model_in_input",
                return_value=None,
            ),
            patch(
                "code_puppy.command_line.model_picker_completion.load_model_names",
                return_value=["gpt-5", "claude"],
            ),
            patch("code_puppy.messaging.emit_warning") as emit_warning,
        ):
            assert _handle_model("/model nope") is True
            assert emit_warning.call_count >= 2


class TestProviderAndContext:
    def test_provider_label(self):
        assert _provider_label({"type": "openai"}) == "OpenAI"
        assert _provider_label({"type": "custom_openai_responses"}) == (
            "Custom OpenAI (Responses)"
        )
        assert _provider_label({"provider": "fireworks"}) == "fireworks"
        assert _provider_label({"type": "mystery-provider"}) == "mystery-provider"
        assert _provider_label({}) == "unknown"

    def test_context_label(self):
        assert _context_label({"context_length": 400000}) == "400,000 tokens"
        assert _context_label({"context_length": 1000000}) == "1.0M tokens"
        assert _context_label({"context_length": 1048576}) == "1.0M tokens"
        assert _context_label({}) == ""


class TestModelSwitcherMenu:
    def test_selects_current_model(self):
        menu = ModelSwitcherMenu(_FAKE_MODELS)
        assert menu._get_selected_model_name() == "gpt-5"

    def test_filter(self):
        menu = ModelSwitcherMenu(_FAKE_MODELS)
        menu._append_filter_char("gpt")
        assert menu.visible_model_names == ["gpt-5"]
        menu._append_filter_char("x")
        assert menu.visible_model_names == []
        menu._set_filter_text("")
        assert menu.visible_model_names == list(_FAKE_MODELS)

    def test_navigation_and_accept(self):
        menu = ModelSwitcherMenu(_FAKE_MODELS)
        menu._move_down()
        assert menu._get_selected_model_name() == "claude-sonnet-4.7"
        assert menu._accept_selection() is True
        assert menu.result == "claude-sonnet-4.7"

    def test_pagination(self):
        menu = ModelSwitcherMenu(_MANY_MODELS)
        assert menu.total_pages == (40 + MODEL_PAGE_SIZE - 1) // MODEL_PAGE_SIZE
        assert menu._get_selected_model_name() == "model-00"
        menu._page_down()
        assert menu._get_selected_model_name() == f"model-{MODEL_PAGE_SIZE:02d}"
        menu._page_up()
        assert menu._get_selected_model_name() == "model-00"

    def test_render_menu(self):
        menu = ModelSwitcherMenu(_FAKE_MODELS)
        text = menu._render_menu().__pt_formatted_text__()
        joined = "".join(part for _, part in text)
        assert "Select Active Model" in joined
        assert "gpt-5" in joined

    def test_render_preview(self):
        menu = ModelSwitcherMenu(_FAKE_MODELS)
        text = menu._render_preview().__pt_formatted_text__()
        joined = "".join(part for _, part in text)
        assert "gpt-5" in joined
        assert "Provider" in joined
        assert "Credentials" in joined

    def test_empty_catalog(self):
        menu = ModelSwitcherMenu({})
        assert menu._get_selected_model_name() is None
        assert menu._accept_selection() is False
        assert menu._render_menu().__pt_formatted_text__() is not None

    async def test_interactive_picker_empty_catalog(self):
        from code_puppy.plugins.model_switcher.picker import interactive_model_picker

        with patch(
            "code_puppy.plugins.model_switcher.picker.ModelSwitcherMenu.run_async"
        ) as run:
            run.return_value = None
            assert await interactive_model_picker({}) is None
