"""i18n coverage for the add_model_menu.py extraction.

Locks in the ``model_menu.*`` catalog namespace that add_model_menu.py
depends on. The model browser owns a prompt_toolkit full-screen Application
and requires a live terminal to run end-to-end, so we test the catalog keys
directly rather than driving the TUI.
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


def _model_menu_keys():
    src = catalog.load_catalog("en-US")
    return [k for k in src if k.startswith("model_menu.")]


def test_model_menu_namespace_is_populated():
    assert len(_model_menu_keys()) >= 29


def test_every_model_menu_key_resolves_to_real_text():
    translate.set_locale("en-US")
    offenders = [
        k for k in _model_menu_keys() if not translate.t(k) or translate.t(k) == k
    ]
    assert not offenders, f"model_menu.* keys not resolving: {offenders}"


def test_every_model_menu_key_pseudolocalizes():
    translate.set_locale(pseudo.PSEUDO_LOCALE)
    offenders = [
        k for k in _model_menu_keys() if not translate.t(k).startswith("\u27e6")
    ]
    assert not offenders, f"model_menu.* keys not pseudolocalized: {offenders}"


def test_registry_keys_interpolate():
    translate.set_locale("en-US")
    assert "boom" in translate.t("model_menu.registry.unavailable", error="boom")
    assert "boom" in translate.t("model_menu.registry.load_error", error="boom")


def test_extra_models_keys_interpolate():
    translate.set_locale("en-US")
    assert "boom" in translate.t("model_menu.extra_models.parse_error", error="boom")
    assert "gpt-x" in translate.t(
        "model_menu.extra_models.already_exists", model_key="gpt-x"
    )
    assert "gpt-x" in translate.t("model_menu.extra_models.added", model_key="gpt-x")
    assert "boom" in translate.t("model_menu.extra_models.add_error", error="boom")


def test_credentials_keys_interpolate():
    translate.set_locale("en-US")
    assert "OpenAI" in translate.t("model_menu.credentials.all_set", provider="OpenAI")
    assert "OpenAI" in translate.t(
        "model_menu.credentials.required_header", provider="OpenAI"
    )
    assert "API_KEY" in translate.t("model_menu.credentials.skipped", env_var="API_KEY")
    assert "API_KEY" in translate.t(
        "model_menu.credentials.saved_to_config", env_var="API_KEY"
    )
    assert "OpenAI" in translate.t(
        "model_menu.credentials.edit_header", provider="OpenAI"
    )
    assert "API_KEY" in translate.t(
        "model_menu.credentials.edit_status", env_var="API_KEY", status="set"
    )
    assert "API_KEY" in translate.t(
        "model_menu.credentials.edit_saved", env_var="API_KEY"
    )


def test_custom_model_keys_interpolate():
    translate.set_locale("en-US")
    assert "OpenAI" in translate.t("model_menu.custom_model.header", provider="OpenAI")


def test_browser_keys_interpolate():
    translate.set_locale("en-US")
    assert "OpenAI" in translate.t(
        "model_menu.browser.unsupported_provider", provider="OpenAI", reason="nope"
    )
    assert "gpt-x" in translate.t(
        "model_menu.browser.no_tool_call_warning", model="gpt-x"
    )


def test_all_placeholders_well_formed():
    """Every {placeholder} in a model_menu.* value must be a bare identifier
    (catches accidental double-brace or stray-brace typos)."""
    src = catalog.load_catalog("en-US")
    for key in _model_menu_keys():
        value = src[key]
        if isinstance(value, str):
            for placeholder in _PLACEHOLDER.findall(value):
                assert placeholder.isidentifier(), (
                    f"{key} has malformed placeholder: {{{placeholder}}}"
                )
