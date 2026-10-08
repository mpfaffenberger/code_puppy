"""Ensure shipped locale catalogs stay structurally synchronized."""

import json
import re
from pathlib import Path

import pytest

_PLACEHOLDER = re.compile(r"\{[^{}]+\}")
_CATALOG_DIR = Path(__file__).parents[2] / "code_puppy" / "i18n" / "locales"
_LOCALES = tuple(
    path.stem for path in _CATALOG_DIR.glob("*.json") if path.stem != "en-US"
)


def _catalog(locale: str) -> dict:
    return json.loads((_CATALOG_DIR / f"{locale}.json").read_text(encoding="utf-8"))


def test_locales_have_exactly_the_source_keys():
    source = _catalog("en-US")
    for locale in _LOCALES:
        assert set(_catalog(locale)) == set(source)


def _placeholders(value: str) -> set[str]:
    # Translators may reorder or repeat fields; names, not order, are the contract.
    return set(_PLACEHOLDER.findall(value))


@pytest.mark.parametrize("locale", _LOCALES)
def test_locales_preserve_source_placeholders(locale):
    source = _catalog("en-US")
    translated = _catalog(locale)
    for key, value in source.items():
        target = translated[key]
        assert isinstance(target, type(value)), (locale, key)
        if isinstance(value, str):
            assert _placeholders(target) == _placeholders(value), (locale, key)
        else:
            assert "other" in target, (locale, key)
            for form in target.values():
                assert isinstance(form, str), (locale, key)
                assert _placeholders(form) == _placeholders(value["other"]), (
                    locale,
                    key,
                )
