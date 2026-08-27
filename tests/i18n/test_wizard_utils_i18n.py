"""Protects wizard catalog parity and real call-site interpolation."""

import re

import pytest

from code_puppy.i18n import catalog, translate

_PLACEHOLDER = re.compile(r"\{(\w+)\}")
_LOCALES = ["en-US", "es", "fr-CA"]

# The actual kwargs each parameterized key is called with in
# wizard_utils.py, keyed by param name -> a representative value. Used to
# catch a locale translation that typo'd a placeholder name (e.g.
# {server_names} instead of {server_name}): supplying the *real* call-site
# param name and asserting it lands in the rendered string, rather than
# deriving the params from the string being tested (which can never detect
# a name that diverges from what callers actually pass).
_REAL_PARAMS = {
    "mcp.install_wizard.env_var_prompt": {"var": "API_KEY"},
    "mcp.install_wizard.prompt_suffix": {
        "prompt": "Port",
        "default": " [8080]",
        "optional": " (optional)",
    },
    "mcp.install_wizard.wizard_error": {"error": "boom"},
    "mcp.install_wizard.server_list_item": {
        "index": " 1",
        "name": "GitHub",
        "indicators": "\u2713",
    },
    "mcp.install_wizard.server_description": {"description": "A server"},
    "mcp.install_wizard.select_prompt": {"count": 10},
    "mcp.install_wizard.name_prompt": {"default_name": "github"},
    "mcp.install_wizard.override_prompt": {"server_name": "my-srv"},
    "mcp.install_wizard.installing": {"name": "GitHub Server"},
    "mcp.install_wizard.name_label": {"server_name": "my-srv"},
    "mcp.install_wizard.env_var_masked": {"var": "TOKEN"},
    "mcp.install_wizard.cmd_arg_line": {"arg": "path", "value": "/tmp"},
    "mcp.install_wizard.config_error": {"error": "boom"},
    "mcp.install_wizard.install_success": {"server_name": "my-srv"},
    "mcp.install_wizard.start_hint": {"server_name": "my-srv"},
    "mcp.install_wizard.install_failed": {"error": "boom"},
}


def _install_wizard_keys():
    src = catalog.load_catalog("en-US")
    return [k for k in src if k.startswith("mcp.install_wizard.")]


def test_install_wizard_namespace_is_populated():
    assert len(_install_wizard_keys()) >= 31


def test_env_var_prompt_interpolates():
    translate.set_locale("en-US")
    assert "API_KEY" in translate.t("mcp.install_wizard.env_var_prompt", var="API_KEY")


def test_server_list_item_interpolates():
    translate.set_locale("en-US")
    rendered = translate.t(
        "mcp.install_wizard.server_list_item",
        index=" 1",
        name="GitHub",
        indicators=" \u2713",
    )
    assert "GitHub" in rendered
    assert "\u2713" in rendered


def test_select_prompt_interpolates():
    translate.set_locale("en-US")
    assert "10" in translate.t("mcp.install_wizard.select_prompt", count=10)


def test_name_and_override_prompts_interpolate():
    translate.set_locale("en-US")
    assert "github" in translate.t(
        "mcp.install_wizard.name_prompt", default_name="github"
    )
    assert "my-srv" in translate.t(
        "mcp.install_wizard.override_prompt", server_name="my-srv"
    )


def test_error_messages_interpolate():
    translate.set_locale("en-US")
    for key in (
        "mcp.install_wizard.wizard_error",
        "mcp.install_wizard.config_error",
        "mcp.install_wizard.install_failed",
    ):
        assert "boom" in translate.t(key, error="boom")


def test_install_success_and_start_hint_interpolate():
    translate.set_locale("en-US")
    assert "my-srv" in translate.t(
        "mcp.install_wizard.install_success", server_name="my-srv"
    )
    assert "my-srv" in translate.t(
        "mcp.install_wizard.start_hint", server_name="my-srv"
    )


@pytest.mark.parametrize("locale", _LOCALES, ids=_LOCALES)
def test_every_key_has_its_own_translation_per_locale(locale):
    """Every locale defines its own entry -- none silently fall through to
    the default-locale value (which ``t()`` would mask, since a missing
    key falls back to en-US and still "resolves").
    """
    src = catalog.load_catalog(locale)
    keys = [k for k in src if k.startswith("mcp.install_wizard.")]
    en_keys = {k for k in _install_wizard_keys()}
    missing = en_keys - set(keys)
    assert not missing, f"{locale} is missing keys: {missing}"


@pytest.mark.parametrize("locale", _LOCALES, ids=_LOCALES)
def test_no_leftover_placeholder_for_supplied_params_per_locale(locale):
    """Every placeholder in each locale's own text can be substituted."""
    translate.set_locale(locale)
    src = catalog.load_catalog(locale)
    for key in _install_wizard_keys():
        entry = src[key]
        text = entry if isinstance(entry, str) else entry.get("other", "")
        if "{{" in text:
            continue
        params = {name: "X" for name in _PLACEHOLDER.findall(text)}
        rendered = translate.t(key, **params)
        assert "{" not in rendered.replace("{{", "").replace("}}", ""), (
            f"{locale}:{key} left an un-substituted placeholder: {rendered!r}"
        )


@pytest.mark.parametrize("locale", _LOCALES, ids=_LOCALES)
def test_real_call_site_params_interpolate_per_locale(locale):
    """Supply each key's *actual* wizard_utils.py call-site param name(s)
    (not names derived from the template itself) and confirm the value
    lands in the rendered text with no placeholder left behind, in every
    locale. Catches a locale whose translation typo'd a placeholder name
    (e.g. {server_names} instead of {server_name}), which self-referential
    interpolation checks structurally cannot detect.
    """
    translate.set_locale(locale)
    for key, params in _REAL_PARAMS.items():
        rendered = translate.t(key, **params)
        assert "{" not in rendered, (
            f"{locale}:{key} left an un-substituted placeholder: {rendered!r}"
        )
        for value in params.values():
            assert str(value) in rendered, (
                f"{locale}:{key} did not interpolate {value!r}: {rendered!r}"
            )
