"""i18n coverage for the config-commands extraction.

Locks in the ``cfg.*`` catalog namespace that config_commands.py depends on:
every key must resolve to real source text, pseudolocalize, and honour its
placeholders.  Command registration side-effects aren't exercised here —
they require the full CLI stack; the namespace guard is the pragmatic proof.
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


def _cfg_keys():
    src = catalog.load_catalog("en-US")
    return [k for k in src if k.startswith("cfg.")]


def test_cfg_namespace_is_populated():
    assert len(_cfg_keys()) >= 20


def test_every_cfg_key_resolves_to_real_text():
    translate.set_locale("en-US")
    offenders = [k for k in _cfg_keys() if not translate.t(k) or translate.t(k) == k]
    assert not offenders, f"cfg.* keys not resolving: {offenders}"


def test_every_cfg_key_pseudolocalizes():
    translate.set_locale(pseudo.PSEUDO_LOCALE)
    offenders = [k for k in _cfg_keys() if not translate.t(k).startswith("\u27e6")]
    assert not offenders, f"cfg.* keys not pseudolocalized: {offenders}"


def test_parametrized_cfg_keys_interpolate():
    translate.set_locale("en-US")
    assert "theme" in translate.t("cfg.set.success", key="theme", value="dark")
    assert "gpt-5" in translate.t("cfg.pin_model.success", model="gpt-5", agent="coder")
    assert "coder" in translate.t("cfg.agent.not_found", agent="coder")
    assert "boom" in translate.t("cfg.unpin.failed", agent="coder", error="boom")


def test_colors_usage_renders_as_literal_placeholder():
    """{{color_type}} must render as the literal text {color_type}, never substituted."""
    translate.set_locale("en-US")
    rendered = translate.t("cfg.colors.usage")
    assert "{color_type}" in rendered, (
        f"Expected literal {{color_type}} in output, got: {rendered!r}"
    )


def test_no_leftover_placeholder_for_supplied_params():
    translate.set_locale("en-US")
    src = catalog.load_catalog("en-US")
    for key in _cfg_keys():
        entry = src[key]
        text = entry if isinstance(entry, str) else entry.get("other", "")
        # Skip entries with intentional double-brace escapes like {{color_type}}.
        # Those render to literal {color_type} in output — correct display text,
        # not an unsubstituted slot — so the brace-presence check is meaningless.
        if "{{" in text:
            continue
        params = {name: "X" for name in _PLACEHOLDER.findall(text)}
        rendered = translate.t(key, **params)
        assert "{" not in rendered.replace("{{", "").replace("}}", ""), (
            f"{key} left an un-substituted placeholder: {rendered!r}"
        )


def test_config_commands_imports_cleanly():
    import importlib

    import code_puppy.command_line.config_commands as mod

    importlib.reload(mod)
    assert hasattr(mod, "handle_unpin_command")
