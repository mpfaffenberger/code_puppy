"""Adversarial lifecycle and validation contracts for plugin catalogs."""

from __future__ import annotations

import asyncio
import contextvars
import json
import os
import subprocess
import sys
import threading
import types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from code_puppy import callbacks, i18n, plugins
from code_puppy.callbacks import clear_loading_context, get_loading_context
from code_puppy.i18n import catalog, plugin_catalog
from code_puppy.i18n.plugin_catalog import canonical_plugin_namespace
from code_puppy.plugins import _plugin_loading_context


def _catalog_dir(root: Path, owner: str, value: object = "message") -> Path:
    directory = root / "locales"
    directory.mkdir(parents=True)
    namespace = canonical_plugin_namespace(owner)
    (directory / "en-US.json").write_text(
        json.dumps({f"{namespace}message": value}), encoding="utf-8"
    )
    return directory


def _register(owner: str, resource: object) -> bool:
    with _plugin_loading_context(owner):
        return i18n.register_plugin_catalog(resource)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _clean_plugin_modules():
    before = set(sys.modules)
    before_path = list(sys.path)
    yield
    sys.path[:] = before_path
    clear_loading_context()
    for name in set(sys.modules) - before:
        if name == "project_plugins" or name.startswith(
            ("project_plugins.", "same-name.", "same_name.")
        ):
            sys.modules.pop(name, None)


def test_nested_same_owner_does_not_commit_failed_outer_transaction(tmp_path):
    inner = _catalog_dir(tmp_path / "inner", "nested", "must not leak")

    with pytest.raises(RuntimeError, match="outer failed"):
        with _plugin_loading_context("nested"):
            with _plugin_loading_context("nested"):
                assert i18n.register_plugin_catalog(inner)
            raise RuntimeError("outer failed")

    assert i18n.t("plugin.nested.message") == "plugin.nested.message"


def test_nested_same_owner_failure_restores_successful_outer_transaction(tmp_path):
    outer = _catalog_dir(tmp_path / "outer", "nested_success", "committed")
    inner = _catalog_dir(tmp_path / "inner", "nested_success", "discarded")

    with _plugin_loading_context("nested_success"):
        assert i18n.register_plugin_catalog(outer)
        with pytest.raises(RuntimeError, match="inner failed"):
            with _plugin_loading_context("nested_success"):
                assert not i18n.register_plugin_catalog(inner)
                raise RuntimeError("inner failed")
        assert get_loading_context() == "nested_success"

    assert i18n.t("plugin.nested-success.message") == "committed"


def test_nested_different_owner_restores_outer_transaction(tmp_path):
    outer = _catalog_dir(tmp_path / "outer", "outer", "outer")
    inner = _catalog_dir(tmp_path / "inner", "inner", "inner")

    with _plugin_loading_context("outer"):
        assert i18n.register_plugin_catalog(outer)
        with _plugin_loading_context("inner"):
            assert i18n.register_plugin_catalog(inner)
        assert get_loading_context() == "outer"
        assert i18n.register_plugin_catalog(outer)

    assert i18n.t("plugin.outer.message") == "outer"
    assert i18n.t("plugin.inner.message") == "inner"


def test_nested_different_owner_failed_outer_discards_both_transactions(tmp_path):
    inner = _catalog_dir(tmp_path / "inner", "separate", "must not leak")

    with pytest.raises(RuntimeError, match="outer failed"):
        with _plugin_loading_context("enclosing"):
            with _plugin_loading_context("separate"):
                assert i18n.register_plugin_catalog(inner)
            raise RuntimeError("outer failed")

    assert i18n.t("plugin.separate.message") == "plugin.separate.message"


def test_thread_with_explicit_empty_context_cannot_register(tmp_path):
    locale_dir = _catalog_dir(tmp_path, "raw_thread", "must not register")
    accepted: list[bool] = []
    empty_context = contextvars.Context()

    def register_without_context() -> None:
        empty_context.run(
            lambda: accepted.append(i18n.register_plugin_catalog(locale_dir))
        )

    with _plugin_loading_context("raw_thread"):
        worker = threading.Thread(target=register_without_context)
        worker.start()
        worker.join(timeout=5)

    assert not worker.is_alive()
    assert accepted == [False]
    assert i18n.t("plugin.raw-thread.message") == "plugin.raw-thread.message"


def test_context_copied_task_cannot_register_after_loader_exit(tmp_path):
    locale_dir = _catalog_dir(tmp_path, "late_task", "must not leak")

    async def scenario():
        gate = asyncio.Event()

        async def late_registration():
            await gate.wait()

            def late_callback():
                return None

            accepted = i18n.register_plugin_catalog(locale_dir)
            callbacks.register_callback("startup", late_callback)
            return accepted, late_callback

        with _plugin_loading_context("late_task"):
            task = asyncio.create_task(late_registration())
        gate.set()
        return await task

    before = callbacks.get_callbacks("startup", include_disabled=True)
    accepted, late_callback = asyncio.run(scenario())

    assert not accepted
    assert callbacks.get_callback_owner(late_callback) is None
    assert callbacks.get_callbacks("startup", include_disabled=True) == before
    assert not catalog._pending_plugin_catalogs
    assert i18n.t("plugin.late-task.message") == "plugin.late-task.message"


def test_concurrent_same_owner_transactions_are_isolated(tmp_path):
    failing = _catalog_dir(tmp_path / "failing", "concurrent", "failed")
    successful = _catalog_dir(tmp_path / "successful", "concurrent", "successful")
    outer_registered = threading.Event()
    successful_finished = threading.Event()

    def fail_load() -> None:
        with pytest.raises(RuntimeError, match="boom"):
            with _plugin_loading_context("concurrent"):
                assert i18n.register_plugin_catalog(failing)
                outer_registered.set()
                assert successful_finished.wait(timeout=5)
                raise RuntimeError("boom")

    def successful_load() -> bool:
        assert outer_registered.wait(timeout=5)
        with _plugin_loading_context("concurrent"):
            accepted = i18n.register_plugin_catalog(successful)
        successful_finished.set()
        return accepted

    with ThreadPoolExecutor(max_workers=2) as executor:
        failed_future = executor.submit(fail_load)
        success_future = executor.submit(successful_load)
        assert success_future.result(timeout=10)
        failed_future.result(timeout=10)

    assert i18n.t("plugin.concurrent.message") == "successful"


def test_loading_context_is_restored_even_if_catalog_finalizer_raises(monkeypatch):
    def fail_finalizer(*_args, **_kwargs):
        raise RuntimeError("finalizer failed")

    monkeypatch.setattr(catalog, "_finish_plugin_catalog_load", fail_finalizer)
    try:
        with pytest.raises(RuntimeError, match="finalizer failed"):
            with _plugin_loading_context("finalizer"):
                pass
        assert get_loading_context() is None
    finally:
        clear_loading_context()


def test_project_package_init_and_eager_sibling_share_transaction(tmp_path):
    plugin_dir = tmp_path / "init_catalog"
    locales = _catalog_dir(plugin_dir, "init_catalog", "from sibling")
    assert locales.is_dir()
    (plugin_dir / "catalog_registration.py").write_text(
        "from pathlib import Path\n"
        "from code_puppy.i18n import register_plugin_catalog\n"
        "ACCEPTED = register_plugin_catalog(Path(__file__).parent / 'locales')\n",
        encoding="utf-8",
    )
    (plugin_dir / "__init__.py").write_text(
        "from . import catalog_registration\n", encoding="utf-8"
    )
    (plugin_dir / "register_callbacks.py").write_text("LOADED = True\n")

    plugins._ensure_project_ns()
    assert plugins._load_one_project_plugin(plugin_dir, "init_catalog")
    assert i18n.t("plugin.init-catalog.message") == "from sibling"


def test_failed_project_package_init_discards_staged_catalog(tmp_path):
    plugin_dir = tmp_path / "failed_init"
    locales = _catalog_dir(plugin_dir, "failed_init", "must not leak")
    assert locales.is_dir()
    (plugin_dir / "__init__.py").write_text(
        "from pathlib import Path\n"
        "from code_puppy.i18n import register_plugin_catalog\n"
        "register_plugin_catalog(Path(__file__).parent / 'locales')\n"
        "raise RuntimeError('init failed')\n",
        encoding="utf-8",
    )
    (plugin_dir / "register_callbacks.py").write_text("LOADED = True\n")

    plugins._ensure_project_ns()
    assert not plugins._load_one_project_plugin(plugin_dir, "failed_init")
    assert i18n.t("plugin.failed-init.message") == "plugin.failed-init.message"


def test_failed_project_init_can_retry_and_restore_catalog(tmp_path):
    plugin_dir = tmp_path / "retry_init"
    _catalog_dir(plugin_dir, "retry_init", "recovered init")
    registration = (
        "from pathlib import Path\n"
        "from code_puppy.i18n import register_plugin_catalog\n"
        "register_plugin_catalog(Path(__file__).parent / 'locales')\n"
    )
    (plugin_dir / "__init__.py").write_text(
        registration + "raise RuntimeError('broken init')\n", encoding="utf-8"
    )
    (plugin_dir / "register_callbacks.py").write_text("LOADED = True\n")
    plugins._ensure_project_ns()

    assert not plugins._load_one_project_plugin(plugin_dir, "retry_init")
    assert not any(
        name.startswith("project_plugins.retry_init") for name in sys.modules
    )

    (plugin_dir / "__init__.py").write_text(registration, encoding="utf-8")

    assert plugins._load_one_project_plugin(plugin_dir, "retry_init")
    assert i18n.t("plugin.retry-init.message") == "recovered init"


def test_failed_project_callbacks_can_retry_and_restore_catalog(tmp_path):
    plugin_dir = tmp_path / "retry_callbacks"
    _catalog_dir(plugin_dir, "retry_callbacks", "recovered callbacks")
    (plugin_dir / "__init__.py").write_text(
        "from pathlib import Path\n"
        "from code_puppy.i18n import register_plugin_catalog\n"
        "register_plugin_catalog(Path(__file__).parent / 'locales')\n",
        encoding="utf-8",
    )
    (plugin_dir / "register_callbacks.py").write_text(
        "raise RuntimeError('broken callbacks')\n", encoding="utf-8"
    )
    plugins._ensure_project_ns()

    assert not plugins._load_one_project_plugin(plugin_dir, "retry_callbacks")
    assert not any(
        name.startswith("project_plugins.retry_callbacks") for name in sys.modules
    )

    (plugin_dir / "register_callbacks.py").write_text("LOADED = True\n")

    assert plugins._load_one_project_plugin(plugin_dir, "retry_callbacks")
    assert i18n.t("plugin.retry-callbacks.message") == "recovered callbacks"


def test_failed_project_load_preserves_preexisting_prefix_modules(tmp_path):
    plugin_dir = tmp_path / "preexisting"
    plugin_dir.mkdir()
    (plugin_dir / "register_callbacks.py").write_text(
        "raise RuntimeError('broken callbacks')\n", encoding="utf-8"
    )
    plugins._ensure_project_ns()
    package_name = "project_plugins.preexisting"
    sibling_name = f"{package_name}.state"
    package = types.ModuleType(package_name)
    package.__path__ = [str(plugin_dir)]
    sibling = types.ModuleType(sibling_name)
    sys.modules[package_name] = package
    sys.modules[sibling_name] = sibling

    assert not plugins._load_one_project_plugin(plugin_dir, "preexisting")
    assert sys.modules[package_name] is package
    assert sys.modules[sibling_name] is sibling
    assert f"{package_name}.register_callbacks" not in sys.modules


def test_core_only_translation_does_not_import_plugin_stack():
    script = """
import sys
from code_puppy.i18n import available_locales, t
t('startup.ready')
available_locales()
assert 'code_puppy.plugins' not in sys.modules
assert 'code_puppy.plugins.config' not in sys.modules
"""
    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr


class _BrokenRoot:
    name = "broken-root"

    def is_dir(self):
        raise RuntimeError("cannot inspect")

    def iterdir(self):
        return iter(())

    def open(self, *_args, **_kwargs):
        raise AssertionError("not reached")


class _BrokenRenderingRoot(_BrokenRoot):
    @property
    def name(self):
        raise RuntimeError("cannot read name")

    def __str__(self):
        raise RuntimeError("cannot render")


class _BrokenEntry:
    name = "en-US.json"

    def is_file(self):
        raise RuntimeError("corrupt archive member")


class _RootWithBrokenEntry:
    name = "broken-entry-root"

    def is_dir(self):
        return True

    def iterdir(self):
        return iter([_BrokenEntry()])

    def open(self, *_args, **_kwargs):
        raise AssertionError("not reached")


class _BrokenPathLike(os.PathLike[str]):
    def __fspath__(self) -> str:
        raise RuntimeError("cannot render path")


@pytest.mark.parametrize(
    "resource",
    [
        _BrokenRoot(),
        _BrokenRenderingRoot(),
        _RootWithBrokenEntry(),
        _BrokenPathLike(),
    ],
)
def test_ordinary_traversable_failures_return_false(resource, caplog):
    assert not _register("broken_resource", resource)
    assert "broken_resource" in caplog.text
    assert "Rejecting i18n catalogs" in caplog.text


def test_resource_validation_does_not_swallow_base_exceptions():
    class InterruptedRoot(_BrokenRoot):
        def is_dir(self):
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        _register("interrupted", InterruptedRoot())


def test_registration_diagnostics_reraise_memory_error():
    class ExhaustedDiagnostic(_BrokenRoot):
        def __str__(self):
            raise MemoryError("synthetic diagnostic exhaustion")

    with pytest.raises(MemoryError, match="synthetic diagnostic exhaustion"):
        i18n.register_plugin_catalog(ExhaustedDiagnostic())


def test_resource_validation_reraises_memory_error(tmp_path, monkeypatch):
    class ExhaustedRoot(_BrokenRoot):
        def is_dir(self):
            raise MemoryError("synthetic resource exhaustion")

    with pytest.raises(MemoryError, match="synthetic resource exhaustion"):
        _register("exhausted", ExhaustedRoot())

    locale_dir = _catalog_dir(tmp_path, "parse_oom", "message")

    def exhausted_parser(*_args, **_kwargs):
        raise MemoryError("synthetic parser exhaustion")

    monkeypatch.setattr(plugin_catalog.json, "load", exhausted_parser)
    with pytest.raises(MemoryError, match="synthetic parser exhaustion"):
        _register("parse_oom", locale_dir)


@pytest.mark.parametrize(
    ("localized", "diagnostic"),
    [
        ({"plugin.validation.message": {"other": "Hola"}}, "entry shape"),
        ({"plugin.validation.message": "Hola {other}"}, "placeholders"),
        (
            {
                "plugin.validation.message": {
                    "other": "Hola",
                    "banana": "Plátanos",
                }
            },
            "unsupported plural category",
        ),
    ],
)
def test_localized_schema_must_match_source(tmp_path, caplog, localized, diagnostic):
    locale_dir = tmp_path / "locales"
    locale_dir.mkdir()
    (locale_dir / "en-US.json").write_text(
        json.dumps({"plugin.validation.message": "Hello {name}"}), encoding="utf-8"
    )
    (locale_dir / "es.json").write_text(json.dumps(localized), encoding="utf-8")

    assert not _register("validation", locale_dir)
    assert i18n.t("plugin.validation.message") == "plugin.validation.message"
    assert diagnostic in caplog.text


def test_plural_placeholders_match_corresponding_source_forms(tmp_path, caplog):
    locale_dir = tmp_path / "locales"
    locale_dir.mkdir()
    (locale_dir / "en-US.json").write_text(
        json.dumps(
            {
                "plugin.plural-shape.message": {
                    "one": "{count} file for {name}",
                    "other": "{count} files for {name}",
                }
            }
        ),
        encoding="utf-8",
    )
    (locale_dir / "es.json").write_text(
        json.dumps(
            {
                "plugin.plural-shape.message": {
                    "one": "{count} archivo para {name}",
                    "other": "{count} archivos para {other}",
                }
            }
        ),
        encoding="utf-8",
    )

    assert not _register("plural_shape", locale_dir)
    assert "placeholders" in caplog.text


def test_locale_filenames_must_be_canonical(tmp_path, caplog):
    locale_dir = _catalog_dir(tmp_path, "canonical", "source")
    (locale_dir / "zh-hans.json").write_text(
        json.dumps({"plugin.canonical.message": "unreachable"}), encoding="utf-8"
    )

    assert not _register("canonical", locale_dir)
    assert "is not canonical" in caplog.text


def test_user_discovery_sorting_deterministically_resolves_namespace_collision(
    tmp_path, monkeypatch
):
    for owner, value in (("same-name", "hyphen"), ("same_name", "underscore")):
        plugin_dir = tmp_path / owner
        _catalog_dir(plugin_dir, owner, value)
        (plugin_dir / "register_callbacks.py").write_text(
            "from pathlib import Path\n"
            "from code_puppy.i18n import register_plugin_catalog\n"
            "register_plugin_catalog(Path(__file__).parent / 'locales')\n",
            encoding="utf-8",
        )

    original_iterdir = Path.iterdir

    def reverse_root(path: Path):
        entries = list(original_iterdir(path))
        if path == tmp_path:
            entries.sort(key=lambda entry: entry.name, reverse=True)
        return iter(entries)

    monkeypatch.setattr(Path, "iterdir", reverse_root)

    assert plugins._load_user_plugins(tmp_path) == ["same-name", "same_name"]
    assert i18n.t("plugin.same-name.message") == "hyphen"


def test_project_discovery_is_sorted(tmp_path, monkeypatch):
    for name in ("alpha", "zeta"):
        plugin_dir = tmp_path / name
        plugin_dir.mkdir()
        (plugin_dir / "register_callbacks.py").write_text("LOADED = True\n")

    original_iterdir = Path.iterdir

    def reverse_root(path: Path):
        entries = list(original_iterdir(path))
        if path == tmp_path:
            entries.sort(key=lambda entry: entry.name, reverse=True)
        return iter(entries)

    loaded_order: list[str] = []
    monkeypatch.setattr(Path, "iterdir", reverse_root)
    monkeypatch.setattr(plugins, "_project_plugin_status", {})
    monkeypatch.setattr(plugins._trust, "get_trust_status", lambda *_args: "trusted")
    monkeypatch.setattr(
        plugins,
        "_load_one_project_plugin",
        lambda _path, name: loaded_order.append(name) or True,
    )
    monkeypatch.setattr(
        "code_puppy.plugins.config.is_plugin_disabled", lambda _name: False
    )

    assert plugins._load_project_plugins(tmp_path, set(), set()) == ["alpha", "zeta"]
    assert loaded_order == ["alpha", "zeta"]


def test_generation_change_retries_current_catalog_load(tmp_path, monkeypatch):
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "en-US.json").write_text(
        json.dumps({"startup.ready": "current generation"}), encoding="utf-8"
    )
    original_load_file = catalog._load_file
    first_read = True

    def change_generation(path: str):
        nonlocal first_read
        loaded = original_load_file(path)
        if first_read:
            first_read = False
            catalog.add_catalog_dir(str(legacy))
        return loaded

    monkeypatch.setattr(catalog, "_load_file", change_generation)

    assert catalog.load_catalog("en-US")["startup.ready"] == "current generation"


def test_plural_entries_cannot_mutate_retained_provider_snapshot(tmp_path):
    locale_dir = _catalog_dir(
        tmp_path,
        "immutable",
        {"one": "one item", "other": "many items"},
    )
    assert _register("immutable", locale_dir)

    entry = catalog.load_catalog("en-US")["plugin.immutable.message"]
    assert not isinstance(entry, str)
    try:
        entry["other"] = "mutated"  # type: ignore[index]
    except TypeError:
        pass

    catalog._plugin_state_changed()
    refreshed = catalog.load_catalog("en-US")["plugin.immutable.message"]
    assert not isinstance(refreshed, str)
    assert refreshed["other"] == "many items"


def test_reset_preserves_loaded_plugin_providers_but_clears_legacy_dirs(tmp_path):
    locale_dir = _catalog_dir(tmp_path / "plugin", "resettable", "provider")
    assert _register("resettable", locale_dir)

    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "en-US.json").write_text(
        json.dumps({"plugin.resettable.message": "legacy"}), encoding="utf-8"
    )
    catalog.add_catalog_dir(str(legacy))
    assert i18n.t("plugin.resettable.message") == "legacy"

    catalog.reset()

    assert i18n.t("plugin.resettable.message") == "provider"
