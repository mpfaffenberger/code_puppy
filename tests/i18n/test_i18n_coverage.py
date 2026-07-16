"""i18n CI gates: catalog coverage + pseudolocalization coverage (PUP-476/480).

These tests are the automated guardrails the extraction workstreams lean on:

* **Catalog coverage** \u2014 every translated key must exist in the en-US source
  catalog (no orphaned/typo'd keys), and every plural entry must define at
  least ``other``.
* **Pseudolocalization coverage** \u2014 running a migrated module in the
  pseudolocale must produce *only* pseudolocalized (bracketed) user-facing
  text. Any raw f-string that skipped ``t()`` shows up un-bracketed and fails
  the test. This is how we prove a module is fully externalized.
"""

import glob
import json
import os

import pytest

from code_puppy import i18n
from code_puppy.i18n import catalog, pseudo, translate

_LOCALES_DIR = os.path.join(os.path.dirname(catalog.__file__), "locales")
_SOURCE = "en-US"


def _load(name):
    with open(os.path.join(_LOCALES_DIR, f"{name}.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _all_catalog_names():
    return [
        os.path.basename(p)[: -len(".json")]
        for p in glob.glob(os.path.join(_LOCALES_DIR, "*.json"))
    ]


@pytest.fixture(autouse=True)
def _reset_locale():
    translate.get_translator().set_locale("en-US")
    catalog.reset()
    yield
    translate.get_translator().set_locale("en-US")
    catalog.reset()


# --- catalog coverage -----------------------------------------------------
def test_every_translated_key_exists_in_source():
    """No orphaned keys: every key in any catalog must be in en-US.json."""
    source_keys = set(_load(_SOURCE).keys())
    offenders = {}
    for name in _all_catalog_names():
        if name == _SOURCE:
            continue
        extra = set(_load(name).keys()) - source_keys
        if extra:
            offenders[name] = sorted(extra)
    assert not offenders, f"Keys missing from en-US source catalog: {offenders}"


def test_plural_entries_define_other():
    """Every plural dict in every catalog must define the 'other' category."""
    offenders = {}
    for name in _all_catalog_names():
        for key, value in _load(name).items():
            if isinstance(value, dict) and "other" not in value:
                offenders.setdefault(name, []).append(key)
    assert not offenders, f"Plural entries missing 'other': {offenders}"


def test_source_placeholders_preserved_in_translations():
    """A translation must reference the same {placeholders} as the source.

    Reordering is fine; introducing an unknown placeholder or dropping a
    required one is a bug that would render wrong at runtime.
    """
    import re

    ph = re.compile(r"\{([^{}]*)\}")

    def placeholders(entry):
        text = " ".join(entry.values()) if isinstance(entry, dict) else entry
        return set(ph.findall(text))

    source = _load(_SOURCE)
    offenders = {}
    for name in _all_catalog_names():
        if name == _SOURCE:
            continue
        for key, value in _load(name).items():
            if key not in source:
                continue  # covered by the orphan-key test
            extra = placeholders(value) - placeholders(source[key])
            if extra:
                offenders.setdefault(name, {})[key] = sorted(extra)
    assert not offenders, f"Unknown placeholders in translations: {offenders}"


# --- pseudolocalization coverage -----------------------------------------
def test_pseudo_covers_version_checker(monkeypatch):
    """version_checker.py must emit only externalized (pseudolocalized) text.

    Proves the PUP-480 first-batch migration left no raw f-strings behind.
    """
    from code_puppy import version_checker as vc

    captured = []
    monkeypatch.setattr(vc, "emit_info", lambda msg, **kw: captured.append(msg))
    monkeypatch.setattr(vc, "emit_warning", lambda msg, **kw: captured.append(msg))
    monkeypatch.setattr(vc, "emit_success", lambda msg, **kw: captured.append(msg))
    # Avoid network + force the "update available" branch for max coverage.
    monkeypatch.setattr(vc, "fetch_latest_version", lambda pkg: "999.0.0")

    monkeypatch.setattr(vc, "get_message_bus", lambda: _NullBus())
    translate.set_locale(pseudo.PSEUDO_LOCALE)
    vc.default_version_mismatch_behavior("1.0.0")

    assert captured, "version_checker emitted nothing"
    for msg in captured:
        assert pseudo.is_pseudo_locale(translate.get_locale())
        assert str(msg).startswith("\u27e6"), (
            f"Un-externalized (non-pseudolocalized) string leaked: {msg!r}"
        )


class _NullBus:
    def emit(self, *_a, **_k):
        pass


def test_version_keys_resolve_in_shipped_locales():
    for loc, expected_current in [
        ("en-US", "Current version: 1.2.3"),
        ("es", "Versi\u00f3n actual: 1.2.3"),
        ("es-419", "Versi\u00f3n actual: 1.2.3"),  # inherits from es
        ("fr-CA", "Version actuelle : 1.2.3"),
    ]:
        translate.set_locale(loc)
        assert i18n.t("version.current", version="1.2.3") == expected_current
