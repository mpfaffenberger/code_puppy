"""Tests for the code_puppy.i18n foundation package (PUP-475).

Covers the PUP-473 Definition-of-Done items applicable to the foundation:
missing-key fallback, locale switching, per-locale formatting, plurals, and
pseudolocalization.
"""

import json

import pytest

from code_puppy import i18n
from code_puppy.i18n import catalog, formats, locale, plurals, pseudo, translate


@pytest.fixture(autouse=True)
def _isolate_i18n(tmp_path, monkeypatch):
    """Reset catalog state + force a clean en-US translator per test."""
    # Clear any env-based locale so detection tests are deterministic.
    for var in ("CODE_PUPPY_LOCALE", "LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        monkeypatch.delenv(var, raising=False)
    catalog.reset()
    translate.get_translator().set_locale("en-US")
    yield
    catalog.reset()
    translate.get_translator().set_locale("en-US")


def _write_catalog(tmp_path, name, data):
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# --- normalization / detection -------------------------------------------
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("en", "en"),
        ("en_US", "en-US"),
        ("en-us", "en-US"),
        ("en_US.UTF-8", "en-US"),
        ("de_DE@euro", "de-DE"),
        ("zh_Hans_CN", "zh-Hans-CN"),
        ("C", None),
        ("POSIX", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_locale(raw, expected):
    assert locale.normalize_locale(raw) == expected


def test_detect_precedence_env_override(monkeypatch):
    monkeypatch.setenv("CODE_PUPPY_LOCALE", "fr_FR.UTF-8")
    monkeypatch.setenv("LANG", "de_DE")
    assert locale.detect_locale(config_value="es-ES") == "fr-FR"


def test_detect_precedence_config_beats_posix(monkeypatch):
    # An explicit persisted config choice must beat the ambient OS locale.
    monkeypatch.setenv("LANG", "de_DE.UTF-8")
    assert locale.detect_locale(config_value="es-ES") == "es-ES"


def test_detect_precedence_posix_used_when_no_config(monkeypatch):
    monkeypatch.setenv("LANG", "de_DE.UTF-8")
    assert locale.detect_locale(config_value=None) == "de-DE"


def test_detect_falls_back_to_config_then_default(monkeypatch):
    assert locale.detect_locale(config_value="ja-JP") == "ja-JP"
    assert locale.detect_locale(config_value=None) == "en-US"


def test_fallback_chain():
    assert locale.fallback_chain("zh-Hans-CN") == [
        "zh-Hans-CN",
        "zh-Hans",
        "zh",
        "en-US",
    ]
    # Default not duplicated when already present.
    assert locale.fallback_chain("en-US") == ["en-US", "en"]


def test_fallback_chain_latin_american_spanish():
    # es-419 is deprecated (folded into base es), so Latin American Spanish
    # now truncates straight to es -- keeping its own regional override file
    # on top and never probing the removed es-419 catalog.
    assert locale.fallback_chain("es-AR") == ["es-AR", "es", "en-US"]
    assert locale.fallback_chain("es-MX") == ["es-MX", "es", "en-US"]
    # An explicit es-419 request still degrades gracefully to base es.
    assert locale.fallback_chain("es-419") == ["es-419", "es", "en-US"]
    # Iberian Spanish resolves the same way (plain truncation).
    assert locale.fallback_chain("es-ES") == ["es-ES", "es", "en-US"]


# --- catalog + missing-key fallback --------------------------------------
def test_missing_key_returns_key_itself():
    assert i18n.t("nope.not.here") == "nope.not.here"


def test_lookup_walks_fallback_chain(tmp_path):
    _write_catalog(tmp_path, "en-US", {"only.in.default": "base"})
    _write_catalog(tmp_path, "fr", {"greeting": "Bonjour"})
    catalog.add_catalog_dir(str(tmp_path))
    translate.set_locale("fr-FR")

    # Present only in the base language catalog (region -> language fallback).
    assert i18n.t("greeting") == "Bonjour"
    # Missing in fr-FR/fr -> falls through to the default en-US catalog.
    assert i18n.t("only.in.default") == "base"


def test_extra_dir_overrides_builtin(tmp_path):
    _write_catalog(tmp_path, "en-US", {"startup.ready": "Custom ready!"})
    catalog.add_catalog_dir(str(tmp_path))
    assert i18n.t("startup.ready") == "Custom ready!"


def test_malformed_catalog_is_skipped(tmp_path):
    (tmp_path / "en-US.json").write_text("{not valid json", encoding="utf-8")
    catalog.add_catalog_dir(str(tmp_path))
    # Builtin en-US still loads; malformed extra file is ignored.
    assert i18n.t("confirm.yes") == "Yes"


# --- interpolation --------------------------------------------------------
def test_interpolation():
    assert i18n.t("startup.welcome", name="TJ") == "Welcome to Code Puppy, TJ!"


def test_missing_param_leaves_placeholder():
    # A DIFFERENT param present -> the forgiving-missing path is exercised and
    # the unknown {name} placeholder is preserved verbatim.
    assert i18n.t("startup.welcome", unrelated="z") == "Welcome to Code Puppy, {name}!"


def test_no_params_leaves_placeholder():
    assert i18n.t("startup.welcome") == "Welcome to Code Puppy, {name}!"


# --- locale switching -----------------------------------------------------
def test_locale_switching(tmp_path):
    _write_catalog(tmp_path, "es-ES", {"startup.ready": "Listo!"})
    catalog.add_catalog_dir(str(tmp_path))

    assert i18n.t("startup.ready") == "Ready to fetch some code. \U0001f436"
    translate.set_locale("es-ES")
    assert i18n.t("startup.ready") == "Listo!"


def test_lazy_resolves_at_str_time(tmp_path):
    _write_catalog(tmp_path, "es-ES", {"confirm.yes": "S\u00ed"})
    catalog.add_catalog_dir(str(tmp_path))

    deferred = i18n.lazy("confirm.yes")
    assert str(deferred) == "Yes"  # active locale is en-US
    translate.set_locale("es-ES")
    assert str(deferred) == "S\u00ed"  # resolves in the *new* locale


# --- plurals --------------------------------------------------------------
@pytest.mark.parametrize("count,expected", [(1, "one"), (0, "other"), (5, "other")])
def test_plural_category_english(count, expected):
    assert plurals.plural_category("en-US", count) == expected


def test_plural_category_russian():
    assert plurals.plural_category("ru-RU", 1) == "one"
    assert plurals.plural_category("ru-RU", 3) == "few"
    assert plurals.plural_category("ru-RU", 11) == "many"


def test_plural_category_cjk_no_plural():
    assert plurals.plural_category("ja-JP", 1) == "other"
    assert plurals.plural_category("ja-JP", 5) == "other"


def test_ngettext_selects_form_and_injects_count():
    assert i18n.ngettext("files.deleted", 1) == "Deleted 1 file."
    assert i18n.ngettext("files.deleted", 3) == "Deleted 3 files."


# --- formatting -----------------------------------------------------------
def test_format_number_en_us():
    assert formats.format_number(1234567) == "1,234,567"
    assert formats.format_number(1234.5, decimals=2) == "1,234.50"


def test_format_number_de():
    assert formats.format_number(1234567, locale="de-DE") == "1.234.567"
    assert formats.format_number(1234.5, decimals=2, locale="de-DE") == "1.234,50"


def test_format_datetime_iso():
    from datetime import datetime

    dt = datetime(2026, 7, 13, 9, 31)
    assert formats.format_datetime(dt) == "2026-07-13 09:31"
    assert formats.format_datetime(dt, date_only=True) == "2026-07-13"


# --- pseudolocalization ---------------------------------------------------
def test_pseudo_locale_transforms_output():
    translate.set_locale(pseudo.PSEUDO_LOCALE)
    out = i18n.t("confirm.yes")
    assert out.startswith("\u27e6") and out.endswith("\u27e7")
    assert "Y" not in out  # accented away
    assert pseudo.is_pseudo_locale(translate.get_locale())


def test_pseudo_preserves_placeholders():
    result = pseudo.pseudolocalize("Hello {name}!")
    assert "{name}" in result  # interpolation key untouched


def test_pseudo_expands_length():
    plain = "short"
    result = pseudo.pseudolocalize(plain)
    # Actually accented (not a no-op) ...
    assert "\u0161" in result  # 's' -> š
    # ... padded with em-space filler ...
    assert "\u2003" in result
    # ... and strictly longer than the original.
    assert len(result) > len(plain)


# --- shipped locales (es, fr-CA) -----------------------------------------
def test_spanish_catalog_ships_and_resolves():
    translate.set_locale("es")
    assert i18n.t("confirm.yes") == "S\u00ed"
    assert (
        i18n.t("startup.welcome", name="TJ") == "\u00a1Bienvenido(a) a Code Puppy, TJ!"
    )


def test_deprecated_es419_resolves_through_base_es():
    # es-419 has no catalog of its own (deprecated); resolves through base es.
    translate.set_locale("es-419")
    assert i18n.t("startup.ready") == "Listo para ir por el c\u00f3digo. \U0001f436"


def test_spanish_region_falls_back_to_base_language():
    # es-MX has no catalog of its own -> es.json (es-419 deprecated).
    translate.set_locale("es-MX")
    assert i18n.t("confirm.no") == "No"
    assert i18n.t("confirm.yes") == "S\u00ed"


def test_central_south_american_dialect_inherits_base_es(tmp_path):
    # A country dialect that only overrides ONE string still inherits the rest
    # from base es, then en-US (es-419 deprecated; no umbrella tier).
    _write_catalog(tmp_path, "es-AR", {"confirm.yes": "Dale"})
    catalog.add_catalog_dir(str(tmp_path))
    translate.set_locale("es-AR")
    assert i18n.t("confirm.yes") == "Dale"  # from es-AR
    # Inherited from base es (chain skips the missing es-419 catalog).
    assert i18n.t("startup.ready") == "Listo para ir por el c\u00f3digo. \U0001f436"
    # Inherited from en-US default.
    assert i18n.t("confirm.no") == "No"


def test_french_canadian_catalog_ships_and_resolves():
    translate.set_locale("fr-CA")
    assert i18n.t("confirm.yes") == "Oui"
    assert i18n.t("startup.welcome", name="TJ") == "Bienvenue dans Code Puppy, TJ!"


def test_french_canadian_plurals():
    translate.set_locale("fr-CA")
    # French: 0 and 1 are singular.
    assert i18n.ngettext("files.deleted", 0) == "0 fichier supprim\u00e9."
    assert i18n.ngettext("files.deleted", 1) == "1 fichier supprim\u00e9."
    assert i18n.ngettext("files.deleted", 3) == "3 fichiers supprim\u00e9s."


def test_spanish_plurals():
    translate.set_locale("es")
    assert i18n.ngettext("files.written", 1) == "Se escribi\u00f3 1 archivo."
    assert i18n.ngettext("files.written", 5) == "Se escribieron 5 archivos."


# --- shipped catalog integrity -------------------------------------------
def test_all_shipped_catalogs_are_valid_json():
    import glob
    import os

    locales_dir = os.path.join(os.path.dirname(catalog.__file__), "locales")
    files = glob.glob(os.path.join(locales_dir, "*.json"))
    assert files, "no shipped catalogs found"
    for path in files:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)  # raises on malformed JSON
        assert isinstance(data, dict), f"{path} is not a JSON object"


def test_target_locales_are_available():
    available = i18n.available_locales()
    for expected in (
        "en-US",
        "es",
        "fr-CA",
        "es-MX",
        "es-AR",
        "es-CO",
        "es-CL",
    ):
        assert expected in available, f"{expected} catalog is missing"


def test_dialect_stubs_inherit_from_base_es():
    # The empty country stubs must resolve every key via es -> en-US.
    for dialect in ("es-MX", "es-AR", "es-CO", "es-CL"):
        translate.set_locale(dialect)
        assert i18n.t("confirm.yes") == "S\u00ed"
        assert i18n.t("startup.ready") == (
            "Listo para ir por el c\u00f3digo. \U0001f436"
        )
        assert i18n.t("confirm.no") == "No"  # inherited from en-US default


# --- emit choke point wiring ---------------------------------------------
def test_emit_message_resolves_lazy_translation(monkeypatch):
    from code_puppy.messaging import message_queue as mq

    captured = {}

    class _FakeQueue:
        def emit_simple(self, message_type, content, **metadata):
            captured["content"] = content

    monkeypatch.setattr(mq, "get_global_queue", lambda: _FakeQueue())
    mq.emit_message(mq.MessageType.INFO, i18n.lazy("confirm.yes"))
    assert captured["content"] == "Yes"

    # Plain strings pass through untouched.
    mq.emit_message(mq.MessageType.INFO, "raw string")
    assert captured["content"] == "raw string"
