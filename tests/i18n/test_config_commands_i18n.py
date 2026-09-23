"""Focused contracts for the already-landed config command localization."""

from code_puppy.i18n import translate


def test_parametrized_cfg_keys_interpolate():
    translate.set_locale("en-US")
    assert "theme" in translate.t("cfg.set.success", key="theme", value="dark")
    assert "gpt-5" in translate.t("cfg.pin_model.success", model="gpt-5", agent="coder")
    assert "coder" in translate.t("cfg.agent.not_found", agent="coder")
    assert "boom" in translate.t("cfg.unpin.failed", agent="coder", error="boom")


def test_config_commands_imports_cleanly():
    import importlib

    import code_puppy.command_line.config_commands as module

    importlib.reload(module)
    assert hasattr(module, "handle_unpin_command")
