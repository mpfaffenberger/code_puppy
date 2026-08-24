"""Catalog installer i18n coverage."""
import re
import pytest
from code_puppy.i18n import catalog, pseudo, translate

@pytest.fixture(autouse=True)
def reset_locale():
    translate.set_locale("en-US"); catalog.reset(); yield
    translate.set_locale("en-US"); catalog.reset()

def keys():
    return [k for k in catalog.load_catalog("en-US") if k.startswith("mcp.catalog.")]

def test_namespace_is_populated():
    assert len(keys()) == 12

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
            assert set(pattern.findall(source[key])) == set(pattern.findall(translated[key]))
