"""Adversarial / security regression tests for code_puppy.i18n.

Each test pins a fix for a finding from the adversarial review of PR #617.
Catalogs are UNTRUSTED input (add_catalog_dir is the plugin/community seam),
so these guard the interpolation engine, the locale precedence, and the
filesystem boundary against hostile or careless catalog content.
"""

import pytest

from code_puppy import i18n
from code_puppy.i18n import catalog, locale, translate


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    for var in ("CODE_PUPPY_LOCALE", "LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        monkeypatch.delenv(var, raising=False)
    catalog.reset()
    translate.get_translator().set_locale("en-US")
    yield
    catalog.reset()
    translate.get_translator().set_locale("en-US")


def _catalog(tmp_path, name, data):
    import json

    (tmp_path / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
    catalog.add_catalog_dir(str(tmp_path))


# --- B1: no str.format attribute-injection via catalog values -------------
def test_attribute_access_in_template_is_inert(tmp_path):
    _catalog(tmp_path, "en-US", {"evil": "Hi {name.__class__.__mro__}"})
    out = i18n.t("evil", name="x")
    # The dotted field is NOT a bare identifier -> left as a literal. No object
    # internals are ever reached.
    assert out == "Hi {name.__class__.__mro__}"
    assert "class" not in out.replace("__class__", "")  # no resolved <class ...>


def test_globals_gadget_is_inert(tmp_path):
    _catalog(tmp_path, "en-US", {"evil": "{x.__class__.__init__.__globals__}"})
    out = i18n.t("evil", x="y")
    assert out == "{x.__class__.__init__.__globals__}"


def test_index_access_in_template_is_inert(tmp_path):
    _catalog(tmp_path, "en-US", {"evil": "{seq[0]}"})
    assert i18n.t("evil", seq=[1, 2, 3]) == "{seq[0]}"


# --- B2: rendering never raises ------------------------------------------
def test_bad_attribute_chain_does_not_raise(tmp_path):
    _catalog(tmp_path, "en-US", {"evil": "{n.__class__.nope.also_nope}"})
    # Would AttributeError under str.format; must be inert here.
    assert i18n.t("evil", n=5) == "{n.__class__.nope.also_nope}"


# --- M1: format-spec width DoS is impossible ------------------------------
def test_width_spec_is_not_expanded(tmp_path):
    _catalog(
        tmp_path,
        "en-US",
        {"files.deleted": {"other": "Deleted {count:99999999} files"}},
    )
    out = i18n.ngettext("files.deleted", 5)
    # No megabyte-long padded string; the spec is left literal.
    assert out == "Deleted {count:99999999} files"
    assert len(out) < 100


# --- interpolation grammar correctness ------------------------------------
def test_brace_escapes(tmp_path):
    _catalog(tmp_path, "en-US", {"esc": "{{literal}} {name}"})
    assert i18n.t("esc", name="v") == "{literal} v"


def test_known_field_substituted_unknown_preserved(tmp_path):
    _catalog(tmp_path, "en-US", {"m": "{a} and {b}"})
    assert i18n.t("m", a="X") == "X and {b}"


def test_value_containing_braces_is_not_reinterpreted(tmp_path):
    _catalog(tmp_path, "en-US", {"m": "{a}"})
    # The substituted value is inserted verbatim, not re-scanned for fields.
    assert i18n.t("m", a="{b}") == "{b}"


# --- M3: path traversal via crafted locale --------------------------------
@pytest.mark.parametrize(
    "bad",
    ["../secret", "../../etc/passwd", "a/b", "a\\b", "..", "", "foo/../bar"],
)
def test_load_catalog_rejects_unsafe_locale(bad):
    assert catalog.load_catalog(bad) == {}


@pytest.mark.parametrize(
    "reserved", ["con", "CON", "nul", "prn", "aux", "com1", "lpt9"]
)
def test_load_catalog_rejects_windows_device_names(reserved):
    # open("con.json") resolves to the console device on Windows -> soft DoS.
    assert catalog.load_catalog(reserved) == {}
    assert not catalog._is_safe_locale(reserved)


@pytest.mark.parametrize(
    "good", ["en-US", "es-419", "fr-CA", "zh-Hans-CN", "sr-Latn-RS", "con-US"]
)
def test_safe_locale_accepts_legit_tags(good):
    # The guard must not reject a single legitimate locale (would be a silent
    # catalog miss). "con-US" is fine -- only the bare reserved stem is unsafe.
    assert catalog._is_safe_locale(good)


def test_cache_not_poisoned_when_dirs_change_mid_load(tmp_path, monkeypatch):
    # Reproduces the N1 residual race: a dir registration lands while a loader
    # is mid-file-I/O. The in-flight (now stale) result must NOT be cached.
    import json

    (tmp_path / "en-US.json").write_text(
        json.dumps({"confirm.yes": "OVERRIDE"}), encoding="utf-8"
    )
    orig_load = catalog._load_file
    state = {"tripped": False}

    def racing_load(path):
        if not state["tripped"]:
            state["tripped"] = True
            catalog.add_catalog_dir(str(tmp_path))  # invalidate mid-flight
        return orig_load(path)

    monkeypatch.setattr(catalog, "_load_file", racing_load)
    catalog.load_catalog("en-US")  # stale result -> must not poison the cache
    monkeypatch.setattr(catalog, "_load_file", orig_load)

    # Next load recomputes against the new dir set and sees the override.
    assert catalog.load_catalog("en-US")["confirm.yes"] == "OVERRIDE"


def test_lookup_with_unsafe_locale_only_uses_safe_fallback(caplog):
    # An unsafe locale name is refused at the filesystem boundary (no traversal
    # read); resolution still falls back safely to the en-US default catalog.
    import logging

    with caplog.at_level(logging.WARNING, logger="code_puppy.i18n.catalog"):
        # Known key resolves via the en-US fallback, not via any traversed file.
        assert catalog.lookup("confirm.yes", "../../etc/passwd") == "Yes"
        # A key that exists in NO catalog stays unresolved (nothing injected it).
        assert catalog.lookup("totally.bogus.key", "../../etc/passwd") is None
    assert any("unsafe locale" in r.message for r in caplog.records)


# --- M2: explicit config beats ambient OS locale --------------------------
def test_config_locale_beats_lang(monkeypatch):
    monkeypatch.setenv("LANG", "de_DE.UTF-8")
    assert locale.detect_locale(config_value="es-ES") == "es-ES"


# --- m1: ensure_detected is idempotent and respects runtime override ------
def test_ensure_detected_seeds_once_then_respects_override(monkeypatch):
    monkeypatch.setenv("LANG", "de_DE.UTF-8")
    tr = translate.Translator()  # fresh, un-seeded
    assert tr.ensure_detected(config_value="es-ES") == "es-ES"  # config wins
    tr.set_locale("fr-CA")  # runtime override
    # Subsequent ensure_detected must NOT re-derive from env/config.
    assert tr.ensure_detected(config_value="es-ES") == "fr-CA"
