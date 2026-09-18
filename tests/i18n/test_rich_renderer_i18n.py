"""Contracts for rich renderer localization."""

import re

from code_puppy.i18n import catalog, pseudo, translate

_PREFIX = "renderer."
_PLACEHOLDER = re.compile(r"\{(\w+)")


def _keys():
    return [key for key in catalog.load_catalog("en-US") if key.startswith(_PREFIX)]


def test_renderer_catalog_is_populated_and_translated():
    keys = _keys()
    assert len(keys) >= 20

    translate.set_locale("en-US")
    assert all(translate.t(key) != key for key in keys)

    for locale in ("es", "fr-CA"):
        data = catalog.load_catalog(locale)
        assert set(keys) <= set(data)
        assert data["renderer.directory_listing"] != catalog.load_catalog("en-US")[
            "renderer.directory_listing"
        ]


def test_renderer_catalog_supports_interpolation_and_pseudolocale():
    translate.set_locale("en-US")
    for key in _keys():
        source = catalog.load_catalog("en-US")[key]
        params = {name: "value" for name in _PLACEHOLDER.findall(source)}
        rendered = translate.t(key, **params)
        assert "{error}" not in rendered
        assert "{cwd}" not in rendered

    translate.set_locale(pseudo.PSEUDO_LOCALE)
    assert all(translate.t(key).startswith("⟦") for key in _keys())
