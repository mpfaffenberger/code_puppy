"""Coverage tests for model_settings_menu.py - exercises all uncovered code paths."""

from unittest.mock import MagicMock, patch

import pytest

from code_puppy.command_line.model_settings_menu import (
    MODELS_PER_PAGE,
    SETTING_DEFINITIONS,
    ModelSettingsMenu,
    _get_model_display_settings,
    _get_setting_choices,
    _load_all_model_names,
    interactive_model_settings,
    show_model_settings_summary,
)


def _make_menu(models=None, current="gpt-5", supported_settings=None):
    """Create a ModelSettingsMenu with mocked dependencies."""
    models = models if models is not None else ["gpt-5", "claude-opus", "grok"]
    with (
        patch(
            "code_puppy.command_line.model_settings_menu._load_all_model_names",
            return_value=models,
        ),
        patch(
            "code_puppy.command_line.model_settings_menu.get_global_model_name",
            return_value=current,
        ),
    ):
        menu = ModelSettingsMenu()
    return menu


class TestAdjustValue:
    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_adjust_boolean(self, mock_settings, mock_supports):
        mock_supports.side_effect = lambda m, s: s == "interleaved_thinking"
        menu = _make_menu()
        menu._load_model_settings("gpt-5")
        menu.editing_mode = True
        menu.edit_value = False
        menu._adjust_value(1)
        assert menu.edit_value is True

    def test_adjust_not_editing(self):
        menu = _make_menu()
        menu.editing_mode = False
        menu._adjust_value(1)

    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_adjust_numeric(self, mock_settings, mock_supports):
        mock_supports.side_effect = lambda m, s: s == "temperature"
        menu = _make_menu()
        menu._load_model_settings("gpt-5")
        menu.editing_mode = True
        menu.edit_value = 0.5
        menu._adjust_value(1)
        assert abs(menu.edit_value - 0.55) < 0.001


class TestEditing:
    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_start_editing_boolean_default(self, mock_settings, mock_supports):
        mock_supports.side_effect = lambda m, s: s == "interleaved_thinking"
        menu = _make_menu()
        menu._load_model_settings("gpt-5")
        menu._start_editing()
        assert menu.edit_value is False

    @pytest.mark.parametrize(
        "setting,expected",
        [
            ("budget_tokens", 10000),
            ("seed", 42),
            ("temperature", 0.7),
            ("top_p", 0.9),
        ],
        ids=["budget_tokens", "seed", "temperature", "top_p"],
    )
    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_start_editing_numeric_default(
        self, mock_settings, mock_supports, setting, expected
    ):
        mock_supports.side_effect = lambda m, s: s == setting
        menu = _make_menu()
        menu._load_model_settings("gpt-5")
        menu._start_editing()
        assert menu.edit_value == expected

    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={"temperature": 0.5},
    )
    def test_start_editing_existing_value(self, mock_settings, mock_supports):
        mock_supports.side_effect = lambda m, s: s == "temperature"
        menu = _make_menu()
        menu._load_model_settings("gpt-5")
        menu._start_editing()
        assert menu.editing_mode is True
        assert menu.edit_value == 0.5

    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    @patch.dict(
        "code_puppy.command_line.model_settings_menu._RETRY_MENU_KEYS", {}, clear=True
    )
    def test_start_editing_generic_numeric_default(self, mock_settings, mock_supports):
        """Test fallback for unknown numeric setting."""
        mock_supports.side_effect = lambda m, s: s == "effort"
        menu = _make_menu()
        menu._load_model_settings("gpt-5")
        # effort is a choice type, so hit the numeric-default else branch by
        # temporarily registering a custom numeric setting below.
        SETTING_DEFINITIONS["_test_numeric"] = {
            "name": "Test",
            "type": "numeric",
            "min": 0,
            "max": 10,
            "step": 1,
            "default": None,
            "format": "{:.0f}",
        }
        try:
            mock_supports.side_effect = lambda m, s: s == "_test_numeric"
            menu2 = _make_menu()
            menu2._load_model_settings("gpt-5")
            # Custom Params is always offered too, so index 0 isn't
            # guaranteed to be our test setting — select it explicitly.
            menu2.setting_index = menu2.supported_settings.index("_test_numeric")
            menu2._start_editing()
            assert menu2.edit_value == 5.0  # (0+10)/2
        finally:
            del SETTING_DEFINITIONS["_test_numeric"]

    def test_start_editing_no_settings(self):
        menu = _make_menu()
        menu.supported_settings = []
        menu._start_editing()
        assert menu.editing_mode is False


class TestFormatValue:
    def test_format_boolean_enabled(self):
        menu = _make_menu()
        assert menu._format_value("interleaved_thinking", True) == "Enabled"

    def test_format_numeric_value(self):
        menu = _make_menu()
        result = menu._format_value("temperature", 0.7)
        assert result == "0.70"


class TestGetSettingChoices:
    def test_non_choice_setting(self):
        choices = _get_setting_choices("temperature")
        assert choices == []

    @patch("code_puppy.command_line.model_settings_menu.ModelFactory")
    def test_reasoning_effort_without_xhigh(self, mock_factory):
        mock_factory.load_config.return_value = {
            "gpt-5": {"supports_xhigh_reasoning": False}
        }
        choices = _get_setting_choices("reasoning_effort", "gpt-5")
        assert "xhigh" not in choices
        assert "high" in choices

    def test_catalog_can_advertise_exact_reasoning_effort_choices(self):
        models_config = {
            "remote-gpt": {
                "setting_choices": {
                    "reasoning_effort": ["low", "medium", "high", "xhigh"]
                }
            }
        }

        assert _get_setting_choices(
            "reasoning_effort", "remote-gpt", models_config
        ) == ["low", "medium", "high", "xhigh"]

    def test_gpt_5_6_offers_max(self):
        # The reported bug: GPT-5.6 (the family that actually documents
        # "max") must offer it, with no catalog flags required.
        choices = _get_setting_choices(
            "reasoning_effort", "gpt-5.6-sol", {"gpt-5.6-sol": {}}
        )
        assert choices == ["none", "low", "medium", "high", "xhigh", "max"]

    def test_plain_gpt_5_excludes_xhigh_and_max(self):
        # Plain GPT-5 only documents minimal/low/medium/high; "none" stands
        # in for "minimal" in Code Puppy's canonical vocabulary.
        choices = _get_setting_choices("reasoning_effort", "gpt-5", {"gpt-5": {}})
        assert choices == ["none", "low", "medium", "high"]

    def test_o_series_gets_reasoning_effort_choices(self):
        # o1/o3/o4-mini previously had no dynamic detection at all.
        choices = _get_setting_choices("reasoning_effort", "o3-mini", {"o3-mini": {}})
        assert choices == ["low", "medium", "high"]

    def test_fixed_effort_model_has_no_choices(self):
        # gpt-5-pro documents a single fixed effort; nothing to pick.
        choices = _get_setting_choices(
            "reasoning_effort", "gpt-5-pro", {"gpt-5-pro": {}}
        )
        assert choices == []

    def test_explicit_flags_can_still_widen_a_recognized_model(self):
        # A custom endpoint fronting a recognized model can still opt in
        # early via the legacy boolean flags.
        choices = _get_setting_choices(
            "reasoning_effort",
            "gpt-5",
            {"gpt-5": {"supports_max_reasoning": True}},
        )
        assert "max" in choices


class TestLoadAllModelNames:
    @patch("code_puppy.command_line.model_settings_menu.ModelFactory")
    def test_load_model_names(self, mock_factory):
        mock_factory.load_config.return_value = {"m1": {}, "m2": {}}
        result = _load_all_model_names()
        assert result == ["m1", "m2"]


class TestModelSettings:
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_gpt_5_6_reasoning_defaults_are_displayed(self, mock_get_all):
        settings = _get_model_display_settings("gpt-5.6-sol")

        assert settings["reasoning_context"] == "all_turns"
        assert settings["reasoning_mode"] == "standard"


class TestPageNavigation:
    def test_page_down(self):
        models = [f"m{i}" for i in range(30)]
        menu = _make_menu(models=models)
        menu.page = 0
        menu._page_down()
        assert menu.page == 1

    def test_page_up(self):
        models = [f"m{i}" for i in range(30)]
        menu = _make_menu(models=models)
        menu.page = 1
        menu._page_up()
        assert menu.page == 0


class TestRenderDetailsPanel:
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_models_view_no_models(self, mock_settings):
        menu = _make_menu(models=[])
        lines = menu._render_details_panel()
        text = "".join(t for _, t in lines)
        assert "No models" in text

    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_models_view_pagination_info(self, mock_settings, mock_supports):
        mock_supports.return_value = False
        models = [f"m{i}" for i in range(MODELS_PER_PAGE + 5)]
        menu = _make_menu(models=models)
        lines = menu._render_details_panel()
        text = "".join(t for _, t in lines)
        assert "Model 1 of" in text

    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    @patch("code_puppy.command_line.model_settings_menu.get_all_model_settings")
    def test_models_view_with_settings(self, mock_settings, mock_supports):
        mock_settings.return_value = {"temperature": 0.5}
        mock_supports.side_effect = lambda m, s: s == "temperature"
        menu = _make_menu(models=["gpt-5"], current="gpt-5")
        lines = menu._render_details_panel()
        text = "".join(t for _, t in lines)
        assert "Model Info" in text
        assert "gpt-5" in text
        assert "Currently active" in text
        assert "Effective Settings" in text

    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_settings_view_boolean_type(self, mock_settings, mock_supports):
        mock_supports.side_effect = lambda m, s: s == "interleaved_thinking"
        menu = _make_menu()
        menu._load_model_settings("gpt-5")
        menu.view_mode = "settings"
        lines = menu._render_details_panel()
        text = "".join(t for _, t in lines)
        assert "Enabled | Disabled" in text

    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_settings_view_editing_none_value(self, mock_settings, mock_supports):
        mock_supports.side_effect = lambda m, s: s == "temperature"
        menu = _make_menu()
        menu._load_model_settings("gpt-5")
        menu.view_mode = "settings"
        menu.editing_mode = True
        menu.edit_value = None
        lines = menu._render_details_panel()
        text = "".join(t for _, t in lines)
        assert "model default" in text

    def test_settings_view_empty_list_defensive(self):
        # Defensive branch: unreachable via _load_model_settings today, but
        # the panel must still degrade gracefully with no settings at all.
        menu = _make_menu()
        menu.selected_model = "gpt-5"
        menu.supported_settings = []
        menu.current_settings = {}
        menu.view_mode = "settings"
        lines = menu._render_details_panel()
        text = "".join(t for _, t in lines)
        assert "doesn't expose" in text

    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    @patch.dict(
        "code_puppy.command_line.model_settings_menu._RETRY_MENU_KEYS", {}, clear=True
    )
    def test_settings_view_no_settings(self, mock_settings, mock_supports):
        # Even a model with zero capability-gated settings gets the universal
        # Custom Params entry, so the details panel shows its description.
        mock_supports.return_value = False
        menu = _make_menu()
        menu._load_model_settings("gpt-5")
        menu.view_mode = "settings"
        lines = menu._render_details_panel()
        text = "".join(t for _, t in lines)
        assert "Custom Params" in text
        assert "doesn't expose" not in text


class TestRenderMainList:
    def test_render_models_empty(self):
        menu = _make_menu(models=[])
        lines = menu._render_main_list()
        text = "".join(t for _, t in lines)
        assert "No models" in text

    @patch(
        "code_puppy.command_line.model_settings_menu.ModelFactory.load_config",
        return_value={"m0": {"description": "desc"}},
    )
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_render_models_pagination(self, mock_settings, mock_load_config):
        models = [f"m{i}" for i in range(MODELS_PER_PAGE + 5)]
        menu = _make_menu(models=models)
        lines = menu._render_main_list()
        text = "".join(t for _, t in lines)
        assert "Page" in text

    @patch(
        "code_puppy.command_line.model_settings_menu.ModelFactory.load_config",
        return_value={"m1": {"description": "desc"}},
    )
    @patch("code_puppy.command_line.model_settings_menu.get_all_model_settings")
    def test_render_models_with_settings(self, mock_settings, mock_load_config):
        mock_settings.return_value = {"temperature": 0.5}
        menu = _make_menu(models=["m1"])
        menu.current_model_name = "m1"
        lines = menu._render_main_list()
        text = "".join(t for _, t in lines)
        assert "m1" in text
        assert "active" in text

    def test_render_settings_view_no_settings_empty_state(self):
        # Defensive branch: unreachable today (universal settings guarantee non-empty),
        # but the panel must still degrade gracefully on an empty list.
        menu = _make_menu()
        menu.selected_model = "gpt-5"
        menu.supported_settings = []
        menu.current_settings = {}
        menu.view_mode = "settings"
        lines = menu._render_main_list()
        text = "".join(t for _, t in lines)
        assert "No configurable settings" in text


class TestResetToDefault:
    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_reset_editing_mode(self, mock_settings, mock_supports):
        mock_supports.side_effect = lambda m, s: s == "temperature"
        menu = _make_menu()
        menu._load_model_settings("gpt-5")
        menu.editing_mode = True
        menu.edit_value = 0.8
        menu._reset_to_default()
        assert menu.edit_value is None

    def test_reset_no_settings(self):
        menu = _make_menu()
        menu.supported_settings = []
        menu._reset_to_default()


class TestRunAndInteractive:
    @patch("code_puppy.command_line.model_settings_menu.ModelSettingsMenu")
    def test_interactive_model_settings(self, mock_cls):
        mock_menu = MagicMock()
        mock_menu.run.return_value = False
        mock_cls.return_value = mock_menu
        result = interactive_model_settings()
        assert result is False


class TestSaveCancel:
    @patch("code_puppy.command_line.model_settings_menu.set_model_setting")
    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_save_none_value_deletes(self, mock_settings, mock_supports, mock_set):
        mock_supports.side_effect = lambda m, s: s == "temperature"
        menu = _make_menu()
        menu._load_model_settings("gpt-5")
        menu.current_settings["temperature"] = 0.5
        menu.editing_mode = True
        menu.edit_value = None
        menu._save_edit()
        assert "temperature" not in menu.current_settings

    def test_save_not_editing(self):
        menu = _make_menu()
        menu.editing_mode = False
        menu._save_edit()


class TestShowModelSettingsSummary:
    @patch("code_puppy.command_line.model_settings_menu.emit_info")
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    @patch(
        "code_puppy.command_line.model_settings_menu.get_global_model_name",
        return_value="gpt-5",
    )
    def test_no_settings(self, mock_gn, mock_settings, mock_emit):
        show_model_settings_summary()
        mock_emit.assert_called_once()
        assert "No custom settings" in mock_emit.call_args[0][0]

    @patch("code_puppy.command_line.model_settings_menu.emit_info")
    @patch("code_puppy.command_line.model_settings_menu.get_all_model_settings")
    @patch(
        "code_puppy.command_line.model_settings_menu.get_global_model_name",
        return_value="gpt-5",
    )
    def test_with_settings(self, mock_gn, mock_settings, mock_emit):
        mock_settings.return_value = {
            "temperature": 0.7,
            "reasoning_effort": "high",
            "interleaved_thinking": True,
        }
        show_model_settings_summary()
        calls = [c[0][0] for c in mock_emit.call_args_list]
        assert any("0.70" in c for c in calls)
        assert any("high" in c for c in calls)
        assert any("Enabled" in c for c in calls)


class TestStateTransitions:
    def test_enter_settings_view_no_models(self):
        menu = _make_menu(models=[])
        menu._enter_settings_view()
        assert menu.view_mode == "models"
