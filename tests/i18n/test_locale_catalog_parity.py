"""Ensure shipped locale catalogs stay structurally synchronized."""

import json
import re
from pathlib import Path

_PLACEHOLDER = re.compile(r"\{[^{}]+\}")
_LOCALES = ("es", "fr-CA")


def _catalog(locale: str) -> dict:
    root = Path(__file__).parents[2]
    return json.loads(
        (root / "code_puppy" / "i18n" / "locales" / f"{locale}.json").read_text()
    )


def test_locales_have_exactly_the_source_keys():
    source = _catalog("en-US")
    for locale in _LOCALES:
        assert set(_catalog(locale)) == set(source)


def test_locales_preserve_source_placeholders():
    source = _catalog("en-US")
    for locale in _LOCALES:
        translated = _catalog(locale)
        for key, value in source.items():
            if not isinstance(value, str) or not isinstance(translated[key], str):
                continue
            assert _PLACEHOLDER.findall(translated[key]) == _PLACEHOLDER.findall(
                value
            ), key
