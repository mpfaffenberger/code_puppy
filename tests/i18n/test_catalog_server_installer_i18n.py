"""Protects catalog installer translations and localized confirmation tokens."""

import re

from code_puppy.i18n import catalog, pseudo, translate


def keys():
    return [k for k in catalog.load_catalog("en-US") if k.startswith("mcp.catalog.")]


def test_namespace_is_populated():
    assert len(keys()) == 13


def test_keys_resolve_and_pseudolocalize():
    assert all(translate.t(k) != k for k in keys())
    translate.set_locale(pseudo.PSEUDO_LOCALE)
    assert all(translate.t(k).startswith("⟦") for k in keys())


def test_placeholders_are_consistent():
    pattern = re.compile(r"\{(\w+)\}")
    source = catalog.load_catalog("en-US")
    for locale in ("es", "fr-CA"):
        translated = catalog.load_catalog(locale)
        for key in keys():
            assert set(pattern.findall(source[key])) == set(
                pattern.findall(translated[key])
            )


def test_localized_affirmative_tokens_match_catalogs():
    assert translate.t("mcp.catalog.confirm_affirmative") == "y"
    translate.set_locale("es")
    assert translate.t("mcp.catalog.confirm_affirmative") == "s"
    translate.set_locale("fr-CA")
    assert translate.t("mcp.catalog.confirm_affirmative") == "o"
