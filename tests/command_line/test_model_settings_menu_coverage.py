"""Coverage tests for model_settings_menu.py - exercises all uncovered code paths."""

from unittest.mock import MagicMock, patch

from code_puppy.command_line.model_settings_menu import (
    MODELS_PER_PAGE,
    SETTING_DEFINITIONS,
    ModelSettingsMenu,
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


# --------------- _load_all_model_names ---------------


class TestLoadAllModelNames:
    @patch("code_puppy.command_line.model_settings_menu.ModelFactory")
    def test_load_model_names(self, mock_factory):
        mock_factory.load_config.return_value = {"m1": {}, "m2": {}}
        result = _load_all_model_names()
        assert result == ["m1", "m2"]


# --------------- _get_setting_choices ---------------


class TestGetSettingChoices:
    @patch("code_puppy.command_line.model_settings_menu.ModelFactory")
    def test_reasoning_effort_without_xhigh(self, mock_factory):
        mock_factory.load_config.return_value = {
            "gpt-5": {"supports_xhigh_reasoning": False}
        }
        choices = _get_setting_choices("reasoning_effort", "gpt-5")
        assert "xhigh" not in choices
        assert "high" in choices

    @patch("code_puppy.command_line.model_settings_menu.ModelFactory")
    def test_reasoning_effort_with_xhigh(self, mock_factory):
        mock_factory.load_config.return_value = {
            "codex": {"supports_xhigh_reasoning": True}
        }
        choices = _get_setting_choices("reasoning_effort", "codex")
        assert "xhigh" in choices

    def test_non_choice_setting(self):
        choices = _get_setting_choices("temperature")
        assert choices == []

    @patch("code_puppy.command_line.model_settings_menu.ModelFactory")
    def test_reasoning_effort_no_model_name(self, mock_factory):
        choices = _get_setting_choices("reasoning_effort")
        assert "xhigh" in choices  # no filtering without model


# --------------- ModelSettingsMenu properties ---------------


class TestMenuProperties:
    def test_total_pages_empty(self):
        menu = _make_menu(models=[])
        assert menu.total_pages == 1

    def test_total_pages_one_page(self):
        menu = _make_menu(models=["m1", "m2"])
        assert menu.total_pages == 1

    def test_total_pages_multiple(self):
        models = [f"m{i}" for i in range(MODELS_PER_PAGE + 1)]
        menu = _make_menu(models=models)
        assert menu.total_pages == 2

    def test_page_start_end(self):
        models = [f"m{i}" for i in range(20)]
        menu = _make_menu(models=models)
        menu.page = 1
        assert menu.page_start == MODELS_PER_PAGE
        assert menu.page_end == 20

    def test_models_on_page(self):
        models = [f"m{i}" for i in range(20)]
        menu = _make_menu(models=models)
        menu.page = 0
        assert len(menu.models_on_page) == MODELS_PER_PAGE

    def test_ensure_selection_visible_before(self):
        models = [f"m{i}" for i in range(30)]
        menu = _make_menu(models=models)
        menu.page = 1
        menu.model_index = 2
        menu._ensure_selection_visible()
        assert menu.page == 0

    def test_ensure_selection_visible_after(self):
        models = [f"m{i}" for i in range(30)]
        menu = _make_menu(models=models)
        menu.page = 0
        menu.model_index = 20
        menu._ensure_selection_visible()
        assert menu.page == 1

    def test_current_model_preselected(self):
        menu = _make_menu(models=["a", "gpt-5", "z"], current="gpt-5")
        assert menu.model_index == 1


# --------------- _get_supported_settings / _load_model_settings ---------------


class TestModelSettings:
    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    def test_get_supported_settings(self, mock_supports):
        mock_supports.side_effect = lambda m, s: s in ("temperature", "seed")
        menu = _make_menu()
        supported = menu._get_supported_settings("gpt-5")
        assert "temperature" in supported
        assert "seed" in supported

    @patch(
        "code_puppy.command_line.model_settings_menu.get_openai_verbosity",
        return_value="high",
    )
    @patch(
        "code_puppy.command_line.model_settings_menu.get_openai_reasoning_effort",
        return_value="medium",
    )
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    def test_load_model_settings_with_openai(
        self, mock_supports, mock_get_all, mock_effort, mock_verb
    ):
        mock_supports.side_effect = lambda m, s: s in (
            "temperature",
            "reasoning_effort",
            "verbosity",
        )
        menu = _make_menu()
        menu._load_model_settings("gpt-5")
        assert menu.selected_model == "gpt-5"
        assert menu.current_settings["reasoning_effort"] == "medium"
        assert menu.current_settings["verbosity"] == "high"


# --------------- _format_value ---------------


class TestFormatValue:
    def test_format_none_with_default(self):
        menu = _make_menu()
        result = menu._format_value("reasoning_effort", None)
        assert "default" in result

    def test_format_none_no_default(self):
        menu = _make_menu()
        result = menu._format_value("temperature", None)
        assert "model default" in result

    def test_format_choice_value(self):
        menu = _make_menu()
        assert menu._format_value("reasoning_effort", "high") == "high"

    def test_format_boolean_enabled(self):
        menu = _make_menu()
        assert menu._format_value("interleaved_thinking", True) == "Enabled"

    def test_format_boolean_disabled(self):
        menu = _make_menu()
        assert menu._format_value("interleaved_thinking", False) == "Disabled"

    def test_format_numeric_value(self):
        menu = _make_menu()
        result = menu._format_value("temperature", 0.7)
        assert result == "0.70"

    def test_format_seed_value(self):
        menu = _make_menu()
        result = menu._format_value("seed", 42)
        assert result == "42"

    def test_format_unknown_setting(self):
        menu = _make_menu()
        assert menu._format_value("bogus", "val") == "val"
        assert menu._format_value("bogus", None) == "(unknown)"


# --------------- Render methods ---------------


class TestRenderMainList:
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_render_models_view(self, mock_settings):
        menu = _make_menu(models=["m1", "m2"])
        menu.view_mode = "models"
        lines = menu._render_main_list()
        text = "".join(t for _, t in lines)
        assert "Select a Model" in text

    @patch("code_puppy.command_line.model_settings_menu.get_all_model_settings")
    def test_render_models_with_settings(self, mock_settings):
        mock_settings.return_value = {"temperature": 0.5}
        menu = _make_menu(models=["m1"])
        menu.current_model_name = "m1"
        lines = menu._render_main_list()
        text = "".join(t for _, t in lines)
        assert "m1" in text
        assert "active" in text

    def test_render_models_empty(self):
        menu = _make_menu(models=[])
        lines = menu._render_main_list()
        text = "".join(t for _, t in lines)
        assert "No models" in text

    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_render_models_pagination(self, mock_settings):
        models = [f"m{i}" for i in range(MODELS_PER_PAGE + 5)]
        menu = _make_menu(models=models)
        lines = menu._render_main_list()
        text = "".join(t for _, t in lines)
        assert "Page" in text

    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_render_settings_view(self, mock_settings, mock_supports):
        mock_supports.side_effect = lambda m, s: s == "temperature"
        menu = _make_menu()
        menu._load_model_settings("gpt-5")
        menu.view_mode = "settings"
        lines = menu._render_main_list()
        text = "".join(t for _, t in lines)
        assert "Settings for" in text
        assert "Temperature" in text

    @patch(
        "code_puppy.command_line.model_settings_menu.model_supports_setting",
        return_value=False,
    )
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_render_settings_view_no_settings(self, mock_settings, mock_supports):
        menu = _make_menu()
        menu._load_model_settings("gpt-5")
        menu.view_mode = "settings"
        lines = menu._render_main_list()
        text = "".join(t for _, t in lines)
        assert "No configurable settings" in text

    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={"temperature": 0.5},
    )
    def test_render_settings_editing_mode(self, mock_settings, mock_supports):
        mock_supports.side_effect = lambda m, s: s == "temperature"
        menu = _make_menu()
        menu._load_model_settings("gpt-5")
        menu.view_mode = "settings"
        menu.editing_mode = True
        menu.edit_value = 0.8
        lines = menu._render_main_list()
        text = "".join(t for _, t in lines)
        assert "0.80" in text


# --------------- Render details panel ---------------


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
        assert "Custom Settings" in text

    @patch(
        "code_puppy.command_line.model_settings_menu.model_supports_setting",
        return_value=False,
    )
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_models_view_no_custom_settings(self, mock_settings, mock_supports):
        menu = _make_menu(models=["m1"], current="other")
        lines = menu._render_details_panel()
        text = "".join(t for _, t in lines)
        assert "default settings" in text

    @patch(
        "code_puppy.command_line.model_settings_menu.model_supports_setting",
        return_value=False,
    )
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_models_view_no_supported_settings(self, mock_settings, mock_supports):
        menu = _make_menu(models=["m1"])
        lines = menu._render_details_panel()
        text = "".join(t for _, t in lines)
        assert "None" in text

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

    @patch("code_puppy.command_line.model_settings_menu.ModelFactory")
    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_settings_view_choice_type(
        self, mock_settings, mock_supports, mock_factory
    ):
        mock_supports.side_effect = lambda m, s: s == "reasoning_effort"
        mock_factory.load_config.return_value = {"gpt-5": {}}
        menu = _make_menu()
        menu._load_model_settings("gpt-5")
        menu.view_mode = "settings"
        lines = menu._render_details_panel()
        text = "".join(t for _, t in lines)
        assert "Setting Details" in text
        assert "Options" in text
        assert "Global setting" in text

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
    def test_settings_view_numeric_type(self, mock_settings, mock_supports):
        mock_supports.side_effect = lambda m, s: s == "temperature"
        menu = _make_menu()
        menu._load_model_settings("gpt-5")
        menu.view_mode = "settings"
        lines = menu._render_details_panel()
        text = "".join(t for _, t in lines)
        assert "Range" in text
        assert "Min" in text

    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={"temperature": 0.5},
    )
    def test_settings_view_with_value(self, mock_settings, mock_supports):
        mock_supports.side_effect = lambda m, s: s == "temperature"
        menu = _make_menu()
        menu._load_model_settings("gpt-5")
        menu.view_mode = "settings"
        lines = menu._render_details_panel()
        text = "".join(t for _, t in lines)
        assert "0.50" in text

    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_settings_view_no_settings(self, mock_settings, mock_supports):
        mock_supports.return_value = False
        menu = _make_menu()
        menu._load_model_settings("gpt-5")
        menu.view_mode = "settings"
        lines = menu._render_details_panel()
        text = "".join(t for _, t in lines)
        assert "doesn't expose" in text

    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_settings_view_editing_mode(self, mock_settings, mock_supports):
        mock_supports.side_effect = lambda m, s: s == "temperature"
        menu = _make_menu()
        menu._load_model_settings("gpt-5")
        menu.view_mode = "settings"
        menu.editing_mode = True
        menu.edit_value = 0.8
        lines = menu._render_details_panel()
        text = "".join(t for _, t in lines)
        assert "EDITING MODE" in text
        assert "0.80" in text

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

    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_settings_view_verbosity_global_warning(self, mock_settings, mock_supports):
        mock_supports.side_effect = lambda m, s: s == "verbosity"
        menu = _make_menu()
        menu._load_model_settings("gpt-5")
        menu.view_mode = "settings"
        lines = menu._render_details_panel()
        text = "".join(t for _, t in lines)
        assert "Global setting" in text


# --------------- State transitions ---------------


class TestStateTransitions:
    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_enter_settings_view(self, mock_settings, mock_supports):
        mock_supports.return_value = True
        menu = _make_menu()
        menu._enter_settings_view()
        assert menu.view_mode == "settings"

    def test_enter_settings_view_no_models(self):
        menu = _make_menu(models=[])
        menu._enter_settings_view()
        assert menu.view_mode == "models"  # no change

    def test_back_to_models(self):
        menu = _make_menu()
        menu.view_mode = "settings"
        menu.editing_mode = True
        menu._back_to_models()
        assert menu.view_mode == "models"
        assert menu.editing_mode is False


# --------------- Editing ---------------


class TestEditing:
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
    def test_start_editing_temperature_default(self, mock_settings, mock_supports):
        mock_supports.side_effect = lambda m, s: s == "temperature"
        menu = _make_menu()
        menu._load_model_settings("gpt-5")
        menu._start_editing()
        assert menu.edit_value == 0.7

    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_start_editing_seed_default(self, mock_settings, mock_supports):
        mock_supports.side_effect = lambda m, s: s == "seed"
        menu = _make_menu()
        menu._load_model_settings("gpt-5")
        menu._start_editing()
        assert menu.edit_value == 42

    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_start_editing_top_p_default(self, mock_settings, mock_supports):
        mock_supports.side_effect = lambda m, s: s == "top_p"
        menu = _make_menu()
        menu._load_model_settings("gpt-5")
        menu._start_editing()
        assert menu.edit_value == 0.9

    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_start_editing_budget_tokens_default(self, mock_settings, mock_supports):
        mock_supports.side_effect = lambda m, s: s == "budget_tokens"
        menu = _make_menu()
        menu._load_model_settings("gpt-5")
        menu._start_editing()
        assert menu.edit_value == 10000

    @patch(
        "code_puppy.command_line.model_settings_menu.get_openai_reasoning_effort",
        return_value="medium",
    )
    @patch("code_puppy.command_line.model_settings_menu.ModelFactory")
    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_start_editing_choice_default(
        self, mock_settings, mock_supports, mock_factory, mock_effort
    ):
        mock_supports.side_effect = lambda m, s: s == "reasoning_effort"
        mock_factory.load_config.return_value = {"gpt-5": {}}
        menu = _make_menu()
        menu._load_model_settings("gpt-5")
        menu._start_editing()
        assert menu.edit_value == "medium"

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

    def test_start_editing_no_settings(self):
        menu = _make_menu()
        menu.supported_settings = []
        menu._start_editing()
        assert menu.editing_mode is False

    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_start_editing_generic_numeric_default(self, mock_settings, mock_supports):
        """Test fallback for unknown numeric setting."""
        mock_supports.side_effect = lambda m, s: s == "effort"
        menu = _make_menu()
        menu._load_model_settings("gpt-5")
        # effort is a choice, let's test a truly numeric unknown by manipulating
        # Actually effort is a choice type. Let's test with a hacky approach:
        # We want the else branch for numeric defaults. Use a custom setting.
        # Just verify budget_tokens which has a known default path
        # Test the else branch for numeric default by temporarily adding a custom setting
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
            menu2._start_editing()
            assert menu2.edit_value == 5.0  # (0+10)/2
        finally:
            del SETTING_DEFINITIONS["_test_numeric"]


# --------------- _adjust_value ---------------


class TestAdjustValue:
    @patch("code_puppy.command_line.model_settings_menu.ModelFactory")
    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_adjust_choice(self, mock_settings, mock_supports, mock_factory):
        mock_supports.side_effect = lambda m, s: s == "reasoning_effort"
        mock_factory.load_config.return_value = {"gpt-5": {}}
        menu = _make_menu()
        menu._load_model_settings("gpt-5")
        menu.editing_mode = True
        menu.edit_value = "medium"
        menu._adjust_value(1)
        assert menu.edit_value == "high"  # next after medium

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

    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_adjust_numeric_clamp_min(self, mock_settings, mock_supports):
        mock_supports.side_effect = lambda m, s: s == "temperature"
        menu = _make_menu()
        menu._load_model_settings("gpt-5")
        menu.editing_mode = True
        menu.edit_value = 0.0
        menu._adjust_value(-1)
        assert menu.edit_value == 0.0

    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_adjust_numeric_clamp_max(self, mock_settings, mock_supports):
        mock_supports.side_effect = lambda m, s: s == "temperature"
        menu = _make_menu()
        menu._load_model_settings("gpt-5")
        menu.editing_mode = True
        menu.edit_value = 1.0
        menu._adjust_value(1)
        assert menu.edit_value == 1.0

    def test_adjust_not_editing(self):
        menu = _make_menu()
        menu.editing_mode = False
        menu._adjust_value(1)  # no crash

    def test_adjust_none_value(self):
        menu = _make_menu()
        menu.editing_mode = True
        menu.edit_value = None
        menu._adjust_value(1)  # no crash


# --------------- _save_edit / _cancel_edit ---------------


class TestSaveCancel:
    @patch("code_puppy.command_line.model_settings_menu.set_model_setting")
    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_save_temperature(self, mock_settings, mock_supports, mock_set):
        mock_supports.side_effect = lambda m, s: s == "temperature"
        menu = _make_menu()
        menu._load_model_settings("gpt-5")
        menu.editing_mode = True
        menu.edit_value = 0.8
        menu._save_edit()
        mock_set.assert_called_with("gpt-5", "temperature", 0.8)
        assert menu.editing_mode is False
        assert menu.result_changed is True

    @patch("code_puppy.command_line.model_settings_menu.set_openai_reasoning_effort")
    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_save_reasoning_effort(self, mock_settings, mock_supports, mock_set):
        mock_supports.side_effect = lambda m, s: s == "reasoning_effort"
        menu = _make_menu()
        menu._load_model_settings("gpt-5")
        menu.editing_mode = True
        menu.edit_value = "high"
        menu._save_edit()
        mock_set.assert_called_with("high")

    @patch("code_puppy.command_line.model_settings_menu.set_openai_verbosity")
    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_save_verbosity(self, mock_settings, mock_supports, mock_set):
        mock_supports.side_effect = lambda m, s: s == "verbosity"
        menu = _make_menu()
        menu._load_model_settings("gpt-5")
        menu.editing_mode = True
        menu.edit_value = "low"
        menu._save_edit()
        mock_set.assert_called_with("low")

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
        menu._save_edit()  # no crash

    def test_cancel_edit(self):
        menu = _make_menu()
        menu.editing_mode = True
        menu.edit_value = 0.5
        menu._cancel_edit()
        assert menu.editing_mode is False
        assert menu.edit_value is None


# --------------- _reset_to_default ---------------


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
        assert menu.edit_value is None  # temperature default is None

    @patch("code_puppy.command_line.model_settings_menu.set_model_setting")
    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_reset_not_editing(self, mock_settings, mock_supports, mock_set):
        mock_supports.side_effect = lambda m, s: s == "temperature"
        menu = _make_menu()
        menu._load_model_settings("gpt-5")
        menu.current_settings["temperature"] = 0.5
        menu._reset_to_default()
        mock_set.assert_called_with("gpt-5", "temperature", None)
        assert menu.result_changed is True

    @patch("code_puppy.command_line.model_settings_menu.set_openai_reasoning_effort")
    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_reset_reasoning_effort(self, mock_settings, mock_supports, mock_set):
        mock_supports.side_effect = lambda m, s: s == "reasoning_effort"
        menu = _make_menu()
        menu._load_model_settings("gpt-5")
        menu._reset_to_default()
        mock_set.assert_called_with("medium")

    @patch("code_puppy.command_line.model_settings_menu.set_openai_verbosity")
    @patch("code_puppy.command_line.model_settings_menu.model_supports_setting")
    @patch(
        "code_puppy.command_line.model_settings_menu.get_all_model_settings",
        return_value={},
    )
    def test_reset_verbosity(self, mock_settings, mock_supports, mock_set):
        mock_supports.side_effect = lambda m, s: s == "verbosity"
        menu = _make_menu()
        menu._load_model_settings("gpt-5")
        menu._reset_to_default()
        mock_set.assert_called_with("medium")

    def test_reset_no_settings(self):
        menu = _make_menu()
        menu.supported_settings = []
        menu._reset_to_default()  # no crash

    def test_reset_no_model(self):
        menu = _make_menu()
        menu.selected_model = None
        menu._reset_to_default()  # no crash


# --------------- Page navigation ---------------


class TestPageNavigation:
    def test_page_up(self):
        models = [f"m{i}" for i in range(30)]
        menu = _make_menu(models=models)
        menu.page = 1
        menu._page_up()
        assert menu.page == 0

    def test_page_up_at_zero(self):
        menu = _make_menu()
        menu.page = 0
        menu._page_up()
        assert menu.page == 0

    def test_page_down(self):
        models = [f"m{i}" for i in range(30)]
        menu = _make_menu(models=models)
        menu.page = 0
        menu._page_down()
        assert menu.page == 1

    def test_page_down_at_last(self):
        menu = _make_menu(models=["m1"])
        menu.page = 0
        menu._page_down()
        assert menu.page == 0


# --------------- Navigation hints ---------------


class TestNavigationHints:
    def test_model_nav_hints_with_pagination(self):
        models = [f"m{i}" for i in range(30)]
        menu = _make_menu(models=models)
        lines = []
        menu._add_model_nav_hints(lines)
        text = "".join(t for _, t in lines)
        assert "PgUp" in text

    def test_model_nav_hints_no_pagination(self):
        menu = _make_menu(models=["m1"])
        lines = []
        menu._add_model_nav_hints(lines)
        text = "".join(t for _, t in lines)
        assert "PgUp" not in text

    def test_settings_nav_hints_editing(self):
        menu = _make_menu()
        menu.editing_mode = True
        lines = []
        menu._add_settings_nav_hints(lines)
        text = "".join(t for _, t in lines)
        assert "Adjust" in text
        assert "Save" in text

    def test_settings_nav_hints_not_editing(self):
        menu = _make_menu()
        menu.editing_mode = False
        lines = []
        menu._add_settings_nav_hints(lines)
        text = "".join(t for _, t in lines)
        assert "Edit setting" in text
        assert "Back to models" in text


# --------------- run() and interactive_model_settings ---------------


class TestRunAndInteractive:
    @patch("code_puppy.command_line.model_settings_menu.set_awaiting_user_input")
    @patch("code_puppy.command_line.model_settings_menu.Application")
    @patch("sys.stdout")
    @patch("time.sleep")
    @patch(
        "code_puppy.command_line.model_settings_menu._load_all_model_names",
        return_value=["m1"],
    )
    @patch(
        "code_puppy.command_line.model_settings_menu.get_global_model_name",
        return_value="m1",
    )
    def test_run_returns_changed(
        self, mock_gn, mock_ln, mock_sleep, mock_stdout, mock_app_cls, mock_await
    ):
        mock_app = MagicMock()
        mock_app_cls.return_value = mock_app
        menu = ModelSettingsMenu()
        menu.result_changed = True
        result = menu.run()
        assert result is True

    @patch("code_puppy.command_line.model_settings_menu.ModelSettingsMenu")
    def test_interactive_model_settings(self, mock_cls):
        mock_menu = MagicMock()
        mock_menu.run.return_value = False
        mock_cls.return_value = mock_menu
        result = interactive_model_settings()
        assert result is False


# --------------- show_model_settings_summary ---------------


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

    @patch("code_puppy.command_line.model_settings_menu.emit_info")
    @patch("code_puppy.command_line.model_settings_menu.get_all_model_settings")
    def test_with_model_name(self, mock_settings, mock_emit):
        mock_settings.return_value = {"temperature": 0.5}
        show_model_settings_summary("claude")
        mock_settings.assert_called_with("claude")
