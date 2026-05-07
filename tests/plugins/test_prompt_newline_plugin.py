"""Tests for the prompt_newline plugin."""

from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest


def _plugin_module():
    sys.modules.setdefault("dbos", MagicMock())
    return importlib.import_module(
        "code_puppy.plugins.prompt_newline.register_callbacks"
    )


def _config_module():
    return importlib.import_module("code_puppy.plugins.prompt_newline.config")


def test_custom_help_lists_command():
    entries = dict(_plugin_module()._custom_help())
    assert "prompt_newline" in entries


def test_handle_custom_command_ignores_unrelated_names():
    assert _plugin_module()._handle_custom_command("/nope", "nope") is None


def test_parse_toggle_arg_defaults_to_none():
    assert _plugin_module()._parse_toggle_arg("/prompt_newline") is None


@pytest.mark.parametrize("arg", ["on", "true", "1", "yes", "ENABLE"])
def test_parse_toggle_arg_truthy(arg):
    assert _plugin_module()._parse_toggle_arg(f"/prompt_newline {arg}") is True


@pytest.mark.parametrize("arg", ["off", "false", "0", "no", "Disable"])
def test_parse_toggle_arg_falsy(arg):
    assert _plugin_module()._parse_toggle_arg(f"/prompt_newline {arg}") is False


def test_parse_toggle_arg_toggle_keyword_returns_none():
    assert _plugin_module()._parse_toggle_arg("/prompt_newline toggle") is None


def test_parse_toggle_arg_rejects_garbage():
    with pytest.raises(ValueError):
        _plugin_module()._parse_toggle_arg("/prompt_newline banana")


def test_append_newline_returns_formatted_text_with_trailing_newline():
    from prompt_toolkit.formatted_text import FormattedText

    original = FormattedText([("class:arrow", ">>> ")])
    result = _plugin_module()._append_newline(original)

    assert isinstance(result, FormattedText)
    assert list(result)[-1] == ("", "\n")
    # original must not be mutated
    assert ("", "\n") not in list(original)


def test_install_prompt_patch_is_idempotent():
    module = _plugin_module()
    from code_puppy.command_line import prompt_toolkit_completion as ptc

    original = ptc.get_prompt_with_active_model
    try:
        module._install_prompt_patch()
        first_patched = ptc.get_prompt_with_active_model
        module._install_prompt_patch()
        second_patched = ptc.get_prompt_with_active_model
        assert first_patched is second_patched
        # Original is preserved on the module for restoration
        assert getattr(ptc, "_prompt_newline_original") is original
    finally:
        ptc.get_prompt_with_active_model = original
        if hasattr(ptc, "_prompt_newline_original"):
            delattr(ptc, "_prompt_newline_original")


def test_patched_prompt_appends_newline_only_when_enabled():
    module = _plugin_module()
    from code_puppy.command_line import prompt_toolkit_completion as ptc

    original = ptc.get_prompt_with_active_model
    try:
        module._install_prompt_patch()

        with patch(
            "code_puppy.plugins.prompt_newline.register_callbacks.is_enabled",
            return_value=False,
        ):
            disabled_result = ptc.get_prompt_with_active_model()

        with patch(
            "code_puppy.plugins.prompt_newline.register_callbacks.is_enabled",
            return_value=True,
        ):
            enabled_result = ptc.get_prompt_with_active_model()

        assert ("", "\n") not in list(disabled_result)
        assert list(enabled_result)[-1] == ("", "\n")
    finally:
        ptc.get_prompt_with_active_model = original
        if hasattr(ptc, "_prompt_newline_original"):
            delattr(ptc, "_prompt_newline_original")


def test_handle_command_persists_explicit_on(tmp_path, monkeypatch):
    # Point the config at a throwaway file so we don't trash real puppy.cfg
    cfg_file = tmp_path / "puppy.cfg"
    monkeypatch.setattr("code_puppy.config.CONFIG_FILE", str(cfg_file))

    module = _plugin_module()
    cfg = _config_module()

    with (
        patch(
            "code_puppy.plugins.prompt_newline.register_callbacks._emit_success"
        ) as mock_success,
        patch("code_puppy.plugins.prompt_newline.register_callbacks._emit_info"),
    ):
        result = module._handle_custom_command("/prompt_newline on", "prompt_newline")

    assert result is True
    assert cfg.is_enabled() is True
    assert "ON" in str(mock_success.call_args)


def test_handle_command_flips_when_no_arg(tmp_path, monkeypatch):
    cfg_file = tmp_path / "puppy.cfg"
    monkeypatch.setattr("code_puppy.config.CONFIG_FILE", str(cfg_file))

    module = _plugin_module()
    cfg = _config_module()

    cfg.set_enabled(False)
    with (
        patch("code_puppy.plugins.prompt_newline.register_callbacks._emit_success"),
        patch("code_puppy.plugins.prompt_newline.register_callbacks._emit_info"),
    ):
        module._handle_custom_command("/prompt_newline", "prompt_newline")
    assert cfg.is_enabled() is True

    with (
        patch("code_puppy.plugins.prompt_newline.register_callbacks._emit_success"),
        patch("code_puppy.plugins.prompt_newline.register_callbacks._emit_info"),
    ):
        module._handle_custom_command("/prompt_newline", "prompt_newline")
    assert cfg.is_enabled() is False


def test_handle_command_rejects_garbage_arg(tmp_path, monkeypatch):
    cfg_file = tmp_path / "puppy.cfg"
    monkeypatch.setattr("code_puppy.config.CONFIG_FILE", str(cfg_file))

    module = _plugin_module()

    with patch(
        "code_puppy.plugins.prompt_newline.register_callbacks._emit_error"
    ) as mock_error:
        result = module._handle_custom_command(
            "/prompt_newline banana", "prompt_newline"
        )

    assert result is True
    mock_error.assert_called_once()
    assert "banana" in str(mock_error.call_args)


def test_is_enabled_defaults_to_false(tmp_path, monkeypatch):
    cfg_file = tmp_path / "puppy.cfg"
    monkeypatch.setattr("code_puppy.config.CONFIG_FILE", str(cfg_file))

    cfg = _config_module()
    assert cfg.is_enabled() is False
