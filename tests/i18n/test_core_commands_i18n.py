"""i18n coverage for the core-commands extraction.

Locks in the ``cmd.*`` catalog namespace that core_commands.py depends on.
Command handlers own the terminal and require the full CLI stack, so we
test the catalog keys directly rather than invoking handlers end-to-end.
"""

import re

import pytest

from code_puppy.i18n import catalog, pseudo, translate

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


@pytest.fixture(autouse=True)
def _reset_locale():
    translate.get_translator().set_locale("en-US")
    catalog.reset()
    yield
    translate.get_translator().set_locale("en-US")
    catalog.reset()


def _cmd_keys():
    src = catalog.load_catalog("en-US")
    return [k for k in src if k.startswith("cmd.")]


def test_cmd_namespace_is_populated():
    assert len(_cmd_keys()) >= 25


def test_every_cmd_key_resolves_to_real_text():
    translate.set_locale("en-US")
    offenders = [k for k in _cmd_keys() if not translate.t(k) or translate.t(k) == k]
    assert not offenders, f"cmd.* keys not resolving: {offenders}"


def test_every_cmd_key_pseudolocalizes():
    translate.set_locale(pseudo.PSEUDO_LOCALE)
    offenders = [k for k in _cmd_keys() if not translate.t(k).startswith("\u27e6")]
    assert not offenders, f"cmd.* keys not pseudolocalized: {offenders}"


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


def test_model_settings_keys_interpolate():
    translate.set_locale("en-US")
    assert "boom" in translate.t("cmd.model_settings.reload_failed", error="boom")
    assert "boom" in translate.t("cmd.model_settings.failed", error="boom")


def test_no_leftover_placeholder_for_supplied_params():
    translate.set_locale("en-US")
    src = catalog.load_catalog("en-US")
    for key in _cmd_keys():
        entry = src[key]
        text = entry if isinstance(entry, str) else entry.get("other", "")
        if "{{" in text:
            continue
        params = {name: "X" for name in _PLACEHOLDER.findall(text)}
        rendered = translate.t(key, **params)
        assert "{" not in rendered.replace("{{", "").replace("}}", ""), (
            f"{key} left an un-substituted placeholder: {rendered!r}"
        )


def test_core_commands_imports_cleanly():
    import code_puppy.command_line.core_commands as mod

    assert hasattr(mod, "handle_cd_command")
