"""Focused contracts for optional plugin-owned i18n catalogs."""

from __future__ import annotations

import importlib
import json
import sys
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from code_puppy import i18n
from code_puppy.i18n import catalog, translate
from code_puppy.i18n.plugin_catalog import canonical_plugin_namespace
from code_puppy.plugins import _plugin_loading_context


def _write_catalogs(root: Path, owner: str, **catalogs: dict[str, object]) -> Path:
    locale_dir = root / "locales"
    locale_dir.mkdir(parents=True)
    namespace = canonical_plugin_namespace(owner)
    for locale, messages in catalogs.items():
        qualified = {f"{namespace}{key}": value for key, value in messages.items()}
        (locale_dir / f"{locale}.json").write_text(
            json.dumps(qualified), encoding="utf-8"
        )
    return locale_dir


def _register(owner: str, resource: Path) -> bool:
    with _plugin_loading_context(owner):
        return i18n.register_plugin_catalog(resource)


def _make_zip_plugin(
    tmp_path: Path,
    *,
    owner: str = "weather_tools",
    catalogs: dict[str, dict[str, object]] | None = None,
    include_locales: bool = True,
) -> tuple[Path, str]:
    package = f"fixture_{owner.replace('-', '_')}"
    wheel = tmp_path / f"{package}-1-py3-none-any.whl"
    namespace = canonical_plugin_namespace(owner)
    register_source = (
        "from importlib.resources import files\n"
        "from code_puppy.i18n import register_plugin_catalog\n"
        f"register_plugin_catalog(files({package!r}).joinpath('locales'))\n"
    )
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(f"{package}/__init__.py", "")
        archive.writestr(f"{package}/register_callbacks.py", register_source)
        if include_locales:
            for locale, messages in (catalogs or {}).items():
                qualified = {
                    f"{namespace}{key}": value for key, value in messages.items()
                }
                archive.writestr(
                    f"{package}/locales/{locale}.json", json.dumps(qualified)
                )
    return wheel, package


class _EntryPoint:
    def __init__(self, name: str, module: str):
        self.name = name
        self._module = module

    def load(self):
        return importlib.import_module(self._module)


def _load_zip_plugin(wheel: Path, owner: str, package: str) -> list[str]:
    from code_puppy import plugins

    sys.path.insert(0, str(wheel))
    importlib.invalidate_caches()
    entry_point = _EntryPoint(owner, f"{package}.register_callbacks")
    with patch.object(plugins, "entry_points", return_value=[entry_point]):
        return plugins._load_installed_plugins()


@pytest.fixture(autouse=True)
def _cleanup_zip_modules():
    before = set(sys.modules)
    before_path = list(sys.path)
    yield
    sys.path[:] = before_path
    for name in set(sys.modules) - before:
        if name.startswith(("fixture_", "project_plugins.")):
            sys.modules.pop(name, None)
    importlib.invalidate_caches()


def test_public_api_is_detectable_and_plugin_without_i18n_is_unchanged(tmp_path):
    from code_puppy import plugins

    plugin_dir = tmp_path / "plain_plugin"
    plugin_dir.mkdir()
    (plugin_dir / "register_callbacks.py").write_text("LOADED = True\n")

    assert callable(i18n.register_plugin_catalog)
    assert plugins._load_user_plugins(tmp_path) == ["plain_plugin"]
    assert i18n.t("plugin.plain-plugin.unregistered") == (
        "plugin.plain-plugin.unregistered"
    )


def test_registration_requires_loader_derived_ownership(tmp_path, caplog):
    locale_dir = _write_catalogs(
        tmp_path, "ownerless", **{"en-US": {"message": "not accepted"}}
    )

    assert not i18n.register_plugin_catalog(locale_dir)
    assert i18n.t("plugin.ownerless.message") == "plugin.ownerless.message"
    assert "must run during normal plugin loading" in caplog.text


def test_legacy_catalog_dir_still_overrides_builtin_and_plugins(tmp_path):
    plugin_dir = _write_catalogs(
        tmp_path / "plugin", "legacy_target", **{"en-US": {"message": "plugin"}}
    )
    assert _register("legacy_target", plugin_dir)

    legacy_dir = tmp_path / "legacy"
    legacy_dir.mkdir()
    (legacy_dir / "en-US.json").write_text(
        json.dumps(
            {
                "startup.ready": "legacy core override",
                "plugin.legacy-target.message": "legacy plugin override",
            }
        ),
        encoding="utf-8",
    )
    catalog.add_catalog_dir(str(legacy_dir))

    assert i18n.t("startup.ready") == "legacy core override"
    assert i18n.t("plugin.legacy-target.message") == "legacy plugin override"


def test_packaged_traversable_catalog_supports_locales_and_source_fallback(tmp_path):
    wheel, package = _make_zip_plugin(
        tmp_path,
        catalogs={
            "en-US": {"details": "Bring an umbrella", "forecast": "Forecast"},
            "es": {"forecast": "Pronóstico"},
            "de": {"forecast": "Vorhersage"},
        },
    )

    assert _load_zip_plugin(wheel, "weather_tools", package) == ["weather_tools"]
    wheel.unlink()  # registered messages no longer depend on package/source paths

    translate.set_locale("es")
    assert i18n.t("plugin.weather-tools.forecast") == "Pronóstico"
    assert i18n.t("plugin.weather-tools.details") == "Bring an umbrella"
    translate.set_locale("de")
    assert i18n.t("plugin.weather-tools.forecast") == "Vorhersage"
    translate.set_locale("fr-CA")
    assert i18n.t("plugin.weather-tools.forecast") == "Forecast"
    assert "de" in i18n.available_locales()


def test_multiple_providers_are_deterministic_and_isolated(tmp_path):
    alpha = _write_catalogs(tmp_path / "alpha", "alpha", **{"en-US": {"message": "A"}})
    beta = _write_catalogs(tmp_path / "beta", "beta", **{"en-US": {"message": "B"}})

    assert _register("beta", beta)
    assert _register("alpha", alpha)
    assert i18n.t("plugin.alpha.message") == "A"
    assert i18n.t("plugin.beta.message") == "B"


def test_registration_is_idempotent_but_conflicting_owner_is_rejected(tmp_path, caplog):
    first = _write_catalogs(
        tmp_path / "first", "repeatable", **{"en-US": {"message": "first"}}
    )
    second = _write_catalogs(
        tmp_path / "second", "repeatable", **{"en-US": {"message": "second"}}
    )

    assert _register("repeatable", first)
    assert _register("repeatable", first)
    assert not _register("repeatable", second)
    assert i18n.t("plugin.repeatable.message") == "first"
    assert "already registered a different catalog provider" in caplog.text


def test_canonical_namespace_collision_is_rejected_without_replacing_first(
    tmp_path, caplog
):
    first = _write_catalogs(
        tmp_path / "first", "same_name", **{"en-US": {"message": "first"}}
    )
    second = _write_catalogs(
        tmp_path / "second", "same-name", **{"en-US": {"message": "second"}}
    )

    assert _register("same_name", first)
    assert not _register("same-name", second)
    assert i18n.t("plugin.same-name.message") == "first"
    assert "collides with plugin 'same_name'" in caplog.text


@pytest.mark.parametrize(
    ("filename", "content", "diagnostic"),
    [
        ("en-US.json", "{oops", "invalid catalog"),
        ("en-US.json", "[]", "root must be a JSON object"),
        (
            "en-US.json",
            '{"plugin.broken.message": 4}',
            "invalid value",
        ),
        (
            "en-US.json",
            '{"plugin.broken.message": {"one": "One"}}',
            "plural object with a string 'other' value",
        ),
        (
            "en-US.json",
            '{"plugin.broken.message": "one", "plugin.broken.message": "two"}',
            "duplicate JSON key",
        ),
        ("en-US.json", '{"core.key": "nope"}', "outside required namespace"),
    ],
)
def test_malformed_provider_is_rejected_atomically(
    tmp_path, caplog, filename, content, diagnostic
):
    locale_dir = tmp_path / "bad-locales"
    locale_dir.mkdir()
    (locale_dir / filename).write_text(content, encoding="utf-8")

    assert not _register("broken", locale_dir)
    assert i18n.t("plugin.broken.message") == "plugin.broken.message"
    assert "plugin 'broken'" in caplog.text
    assert str(locale_dir) in caplog.text
    assert diagnostic in caplog.text


def test_partial_translation_with_unknown_source_key_is_rejected(tmp_path, caplog):
    locale_dir = tmp_path / "locales"
    locale_dir.mkdir()
    (locale_dir / "en-US.json").write_text(
        '{"plugin.partial.known": "Known"}', encoding="utf-8"
    )
    (locale_dir / "es.json").write_text(
        '{"plugin.partial.unknown": "Desconocido"}', encoding="utf-8"
    )

    assert not _register("partial", locale_dir)
    assert i18n.t("plugin.partial.known") == "plugin.partial.known"
    assert "missing from en-US.json" in caplog.text


def test_missing_source_catalog_and_package_data_are_diagnostic(tmp_path, caplog):
    only_translation = tmp_path / "only-translation"
    only_translation.mkdir()
    (only_translation / "es.json").write_text(
        '{"plugin.no-source.message": "Hola"}', encoding="utf-8"
    )
    assert not _register("no_source", only_translation)
    assert "must include en-US.json" in caplog.text

    wheel, package = _make_zip_plugin(
        tmp_path, owner="missing_data", include_locales=False
    )
    assert _load_zip_plugin(wheel, "missing_data", package) == ["missing_data"]
    assert "plugin 'missing_data'" in caplog.text
    assert "include the JSON files as package data" in caplog.text


def test_successful_load_invalidates_a_preexisting_catalog_cache(tmp_path):
    key = "plugin.cache-test.message"
    assert i18n.t(key) == key

    locale_dir = _write_catalogs(
        tmp_path, "cache_test", **{"en-US": {"message": "fresh"}}
    )
    assert _register("cache_test", locale_dir)
    assert i18n.t(key) == "fresh"


def test_failed_plugin_import_discards_its_staged_catalog(tmp_path):
    plugin_dir = tmp_path / "crashy"
    locale_dir = _write_catalogs(
        plugin_dir, "crashy", **{"en-US": {"message": "must not leak"}}
    )
    (plugin_dir / "register_callbacks.py").write_text(
        "from pathlib import Path\n"
        "from code_puppy.i18n import register_plugin_catalog\n"
        "register_plugin_catalog(Path(__file__).parent / 'locales')\n"
        "raise RuntimeError('boom')\n",
        encoding="utf-8",
    )

    from code_puppy import plugins

    assert locale_dir.is_dir()
    assert plugins._load_user_plugins(tmp_path) == []
    assert i18n.t("plugin.crashy.message") == "plugin.crashy.message"


def test_project_hot_load_and_dynamic_enable_disable_refresh_catalogs(
    tmp_path, monkeypatch
):
    from code_puppy import plugins
    from code_puppy.plugins import config

    plugins_dir = tmp_path / ".code_puppy" / "plugins"
    plugin_dir = plugins_dir / "hot_locale"
    _write_catalogs(plugin_dir, "hot_locale", **{"en-US": {"message": "hot and fresh"}})
    (plugin_dir / "register_callbacks.py").write_text(
        "from pathlib import Path\n"
        "from code_puppy.i18n import register_plugin_catalog\n"
        "register_plugin_catalog(Path(__file__).parent / 'locales')\n",
        encoding="utf-8",
    )
    key = "plugin.hot-locale.message"
    assert i18n.t(key) == key

    monkeypatch.setattr(plugins, "get_project_plugins_directory", lambda: plugins_dir)
    monkeypatch.setattr(plugins._trust, "is_plugin_trusted", lambda *args: True)
    monkeypatch.setattr(
        plugins,
        "_loaded_plugin_names",
        {"builtin": [], "user": [], "project": []},
    )
    monkeypatch.setattr(plugins, "_project_plugin_status", {})

    assert plugins.load_project_plugin_now("hot_locale")
    assert i18n.t(key) == "hot and fresh"
    assert plugins.load_project_plugin_now("hot_locale")  # no duplicate reload

    assert config.set_plugin_disabled("hot_locale", True)
    assert i18n.t(key) == key
    assert config.set_plugin_disabled("hot_locale", False)
    assert i18n.t(key) == "hot and fresh"
