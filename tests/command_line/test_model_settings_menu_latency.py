"""Regression coverage for network-backed model catalogs in /model_settings."""

from unittest.mock import patch

from code_puppy.command_line.model_settings_menu import ModelSettingsMenu


def test_model_picker_repaints_do_not_reload_model_catalog():
    catalog = {
        "vizio-gpt-5.6-sol": {
            "supported_settings": ["reasoning_effort", "summary", "verbosity"]
        },
        "vizio-claude-opus-5": {"supported_settings": ["extended_thinking", "effort"]},
    }

    with patch(
        "code_puppy.command_line.model_settings_menu.ModelFactory.load_config",
        return_value=catalog,
    ) as load_config:
        menu = ModelSettingsMenu()
        loads_after_open = load_config.call_count

        # Every arrow/Enter/Esc repaint calls both renderers. A load_model_config
        # callback may perform HTTP discovery, so neither renderer may reload it.
        for _ in range(3):
            menu._render_main_list()
            menu._render_details_panel()

        assert load_config.call_count == loads_after_open


def test_capability_type_error_is_not_retried_without_snapshot():
    catalog = {"vizio-model": {"supported_settings": ["effort"]}}

    def broken(model_name, setting, models_config=None):
        raise TypeError("implementation bug")

    with patch(
        "code_puppy.command_line.model_settings_menu.model_supports_setting",
        side_effect=broken,
    ) as supports:
        from code_puppy.command_line.model_settings_menu import _supports_setting

        try:
            _supports_setting("vizio-model", "effort", catalog)
        except TypeError as error:
            assert str(error) == "implementation bug"
        else:
            raise AssertionError("internal TypeError must propagate")

        assert supports.call_count == 1


def test_model_picker_capability_checks_use_catalog_snapshot():
    catalog = {
        "vizio-claude-opus-5": {"supported_settings": ["extended_thinking", "effort"]}
    }

    with patch(
        "code_puppy.command_line.model_settings_menu.ModelFactory.load_config",
        return_value=catalog,
    ) as load_config:
        menu = ModelSettingsMenu()
        loads_after_open = load_config.call_count
        supported = menu._get_supported_settings("vizio-claude-opus-5")

        assert "effort" in supported
        assert load_config.call_count == loads_after_open
