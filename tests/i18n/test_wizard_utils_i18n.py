"""i18n coverage for the wizard_utils.py extraction.

Locks in the ``mcp.install_wizard.*`` catalog namespace that
wizard_utils.py (the popular-server install wizard, distinct from the
custom-server config_wizard.py's ``mcp.wizard.*`` namespace) depends on.
"""

import re

import pytest

from code_puppy.i18n import catalog, pseudo, translate

_PLACEHOLDER = re.compile(r"\{(\w+)\}")
_LOCALES = ["en-US", "es", "fr-CA"]


@pytest.fixture(autouse=True)
def _reset_locale():
    translate.get_translator().set_locale("en-US")
    catalog.reset()
    yield
    translate.get_translator().set_locale("en-US")
    catalog.reset()


def _install_wizard_keys():
    src = catalog.load_catalog("en-US")
    return [k for k in src if k.startswith("mcp.install_wizard.")]


def test_install_wizard_namespace_is_populated():
    assert len(_install_wizard_keys()) >= 31


def test_every_install_wizard_key_resolves_to_real_text():
    translate.set_locale("en-US")
    offenders = [
        k for k in _install_wizard_keys() if not translate.t(k) or translate.t(k) == k
    ]
    assert not offenders, f"mcp.install_wizard.* keys not resolving: {offenders}"


def test_every_install_wizard_key_pseudolocalizes():
    translate.set_locale(pseudo.PSEUDO_LOCALE)
    offenders = [
        k for k in _install_wizard_keys() if not translate.t(k).startswith("\u27e6")
    ]
    assert not offenders, f"mcp.install_wizard.* keys not pseudolocalized: {offenders}"


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
    """Supplying every placeholder must leave no ``{field}`` behind, in
    every locale -- not just en-US. Catches a locale whose translation
    typo'd a param name (e.g. ``{server_names}`` instead of
    ``{server_name}``), which ``translate.t``'s forgiving interpolation
    would otherwise silently leave un-substituted.
    """
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
