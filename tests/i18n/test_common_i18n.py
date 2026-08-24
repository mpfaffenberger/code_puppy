"""Catalog coverage for user-facing approval messages in tools.common."""

import re

import pytest

from code_puppy.i18n import catalog, pseudo, translate

_NAMESPACE = "tools.common.approval."
_PLACEHOLDER = re.compile(r"\{(\w+)\}")


@pytest.fixture(autouse=True)
def _reset_locale():
    translate.set_locale("en-US")
    catalog.reset()
    yield
    translate.set_locale("en-US")
    catalog.reset()


def _keys():
    return [key for key in catalog.load_catalog("en-US") if key.startswith(_NAMESPACE)]


def test_common_approval_namespace_is_complete_in_all_catalogs():
    expected = set(_keys())
    assert len(expected) == 12
    for locale in ("en-US", "es", "fr-CA"):
        assert expected <= set(catalog.load_catalog(locale))


def test_common_messages_resolve_and_pseudolocalize():
    for key in _keys():
        assert translate.t(key) != key
    translate.set_locale(pseudo.PSEUDO_LOCALE)
    assert all(translate.t(key).startswith("⟦") for key in _keys())


def test_common_placeholders_are_preserved():
    source = catalog.load_catalog("en-US")
    expected = {
        key: set(_PLACEHOLDER.findall(value))
        for key, value in source.items()
        if key.startswith(_NAMESPACE)
    }
    for locale in ("es", "fr-CA"):
        translated = catalog.load_catalog(locale)
        assert {
            key: set(_PLACEHOLDER.findall(translated[key])) for key in expected
        } == expected


def test_common_interpolates_user_values():
    translate.set_locale("es")
    assert "Puppy" in translate.t("tools.common.approval.tell", puppy_name="Puppy")
    assert "feedback" in translate.t(
        "tools.common.approval.telling_feedback",
        puppy_name="Puppy",
        feedback="feedback",
    )
