"""Coverage for the agent manager's user-facing message extraction."""

import re

import pytest

from code_puppy.i18n import catalog, pseudo, translate

_PLACEHOLDER = re.compile(r"\{(\w+)\}")
_NAMESPACE = "agent_manager."


@pytest.fixture(autouse=True)
def _reset_locale():
    translate.set_locale("en-US")
    catalog.reset()
    yield
    translate.set_locale("en-US")
    catalog.reset()


def _keys(locale="en-US"):
    return [key for key in catalog.load_catalog(locale) if key.startswith(_NAMESPACE)]


def test_agent_manager_namespace_is_complete_in_all_catalogs():
    expected = set(_keys())
    assert len(expected) == 19
    for locale in ("es", "fr-CA"):
        assert set(_keys(locale)) == expected


def test_agent_manager_messages_resolve_and_pseudolocalize():
    translate.set_locale("en-US")
    assert all(translate.t(key) != key for key in _keys())
    translate.set_locale(pseudo.PSEUDO_LOCALE)
    assert all(translate.t(key).startswith("⟦") for key in _keys())


def test_catalog_translations_preserve_placeholders():
    catalogs = {locale: catalog.load_catalog(locale) for locale in ("en-US", "es", "fr-CA")}
    for key in _keys():
        source = set(_PLACEHOLDER.findall(catalogs["en-US"][key]))
        assert source == set(_PLACEHOLDER.findall(catalogs["es"][key]))
        assert source == set(_PLACEHOLDER.findall(catalogs["fr-CA"][key]))


def test_dynamic_values_are_interpolated():
    translate.set_locale("es")
    assert "agent-x" in translate.t("agent_manager.clone.success", agent_name="agent-x", clone_name="agent-y")
    assert "agent-y" in translate.t("agent_manager.clone.success", agent_name="agent-x", clone_name="agent-y")
    assert "boom" in translate.t("agent_manager.discovery.plugin_load_failed", error="boom")
