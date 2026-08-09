"""i18n coverage for the core-commands extraction.

Locks in the concrete ``cmd.*`` key contracts that core_commands.py
depends on. Command handlers own the terminal and require the full CLI
stack, so we test the catalog keys directly rather than invoking handlers
end-to-end. The generic namespace sweep (every key resolves /
pseudolocalizes / no leftover placeholders) lives in
``test_catalog_namespaces.py``.
"""

import pytest

from code_puppy.i18n import catalog, translate


@pytest.fixture(autouse=True)
def _reset_locale():
    translate.get_translator().set_locale("en-US")
    catalog.reset()
    yield
    translate.get_translator().set_locale("en-US")
    catalog.reset()


def test_cd_keys_interpolate():
    translate.set_locale("en-US")
    assert "/tmp" in translate.t("cmd.cd.success", path="/tmp")
    assert "boom" in translate.t("cmd.cd.list_error", error="boom")
    assert "boom" in translate.t("cmd.cd.reload_error", error="boom")
    assert "/nope" in translate.t("cmd.cd.not_a_dir", path="/nope")


def test_paste_keys_interpolate():
    translate.set_locale("en-US")
    assert "3" in translate.t("cmd.paste.count", count=3)


def test_agent_keys_interpolate():
    translate.set_locale("en-US")
    assert "coder" in translate.t("cmd.agent.already_using", agent="coder")
    assert "coder" in translate.t("cmd.agent.switched", agent="coder")
    assert "boom" in translate.t("cmd.agent.picker_failed", error="boom")


def test_model_keys_interpolate():
    translate.set_locale("en-US")
    assert "gpt-5" in translate.t("cmd.model.success", model="gpt-5")
    assert "gpt-5" in translate.t("cmd.model.available", models="gpt-5, claude-3")
    assert "boom" in translate.t("cmd.model.picker_failed", error="boom")


def test_add_model_failed_interpolates_error_param():
    # Guards against a param-name typo in the catalog entry for
    # cmd.add_model.failed (e.g. ``{err}`` vs ``{error}``). The generic
    # sweep test would still pass if the placeholder name drifted, so
    # assert the concrete substitution here.
    translate.set_locale("en-US")
    rendered = translate.t("cmd.add_model.failed", error="XYZ")
    assert "XYZ" in rendered
    assert "{error}" not in rendered


def test_model_settings_keys_interpolate():
    translate.set_locale("en-US")
    assert "boom" in translate.t("cmd.model_settings.reload_failed", error="boom")
    assert "boom" in translate.t("cmd.model_settings.failed", error="boom")


def test_core_commands_imports_cleanly():
    import code_puppy.command_line.core_commands as mod

    assert hasattr(mod, "handle_cd_command")
