"""Adversarial transaction races and atomicity for plugin i18n catalogs."""

from __future__ import annotations

import contextvars
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from code_puppy import callbacks, i18n, plugins
from code_puppy.i18n import catalog, plugin_catalog
from code_puppy.i18n.plugin_catalog import canonical_plugin_namespace
from code_puppy.plugins import _plugin_loading_context


class _BlockingDirectory:
    """Traversable adapter that pauses catalog I/O at a deterministic barrier."""

    def __init__(
        self, directory: Path, entered: threading.Event, release: threading.Event
    ) -> None:
        self._directory = directory
        self._entered = entered
        self._release = release
        self.name = directory.name

    def is_dir(self) -> bool:
        self._entered.set()
        assert self._release.wait(timeout=5)
        return self._directory.is_dir()

    def iterdir(self):
        return self._directory.iterdir()

    def open(self, *args, **kwargs):
        return self._directory.open(*args, **kwargs)


def _catalog_dir(root: Path, owner: str, message: str) -> Path:
    directory = root / "locales"
    directory.mkdir(parents=True)
    namespace = canonical_plugin_namespace(owner)
    (directory / "en-US.json").write_text(
        f'{{"{namespace}message": "{message}"}}', encoding="utf-8"
    )
    return directory


def _provider(root: Path, owner: str, message: str):
    return plugin_catalog.read_plugin_catalogs(
        owner, _catalog_dir(root, owner, message)
    )


def test_catalog_finishing_after_loader_exit_is_rejected(tmp_path):
    entered = threading.Event()
    release = threading.Event()
    resource = _BlockingDirectory(
        _catalog_dir(tmp_path, "catalog_race", "must not leak"), entered, release
    )

    with ThreadPoolExecutor(max_workers=1) as executor:
        with _plugin_loading_context("catalog_race"):
            copied_context = contextvars.copy_context()
            future = executor.submit(
                copied_context.run, i18n.register_plugin_catalog, resource
            )
            assert entered.wait(timeout=5)
        release.set()
        assert future.result(timeout=5) is False

    assert not catalog._pending_plugin_catalogs
    assert i18n.t("plugin.catalog-race.message") == "plugin.catalog-race.message"


def test_child_deactivation_and_transfer_are_atomic_with_parent_publish(
    tmp_path, monkeypatch
):
    parent_resource = _catalog_dir(tmp_path / "parent", "ordered_parent", "parent")
    child_resource = _catalog_dir(tmp_path / "child", "ordered_child", "child")
    child_deactivated = threading.Event()
    release_child = threading.Event()
    parent_published = threading.Event()
    original_deactivate = plugins._deactivate_loading_transaction
    original_finish = catalog._finish_plugin_catalog_load
    parent_transaction_id: object | None = None

    def pause_child_after_deactivation(transaction_id):
        result = original_deactivate(transaction_id)
        if threading.current_thread().name.startswith("nested-catalog-child"):
            child_deactivated.set()
            assert release_child.wait(timeout=5)
        return result

    def observe_parent_publish(transaction_id, **kwargs):
        try:
            return original_finish(transaction_id, **kwargs)
        finally:
            if transaction_id is parent_transaction_id:
                parent_published.set()

    monkeypatch.setattr(
        plugins, "_deactivate_loading_transaction", pause_child_after_deactivation
    )
    monkeypatch.setattr(catalog, "_finish_plugin_catalog_load", observe_parent_publish)

    coordinator: threading.Thread | None = None
    with ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="nested-catalog-child"
    ) as executor:
        with _plugin_loading_context("ordered_parent"):
            parent_transaction = callbacks._get_loading_transaction()
            assert parent_transaction is not None
            parent_transaction_id = parent_transaction.transaction_id
            assert i18n.register_plugin_catalog(parent_resource)
            copied_context = contextvars.copy_context()

            def load_child() -> None:
                with _plugin_loading_context("ordered_child"):
                    assert i18n.register_plugin_catalog(child_resource)

            future = executor.submit(copied_context.run, load_child)
            assert child_deactivated.wait(timeout=5)

            # Broken implementations have already released the lineage guard.
            # Deliberately drive the reported parent-first ordering to completion
            # instead of hanging; fixed implementations keep the guard here and
            # therefore must finish the child transfer first.
            parent_can_finalize = parent_transaction.guard.acquire(blocking=False)
            if parent_can_finalize:
                parent_transaction.guard.release()

                def release_after_parent_publish() -> None:
                    assert parent_published.wait(timeout=5)
                    release_child.set()

                coordinator = threading.Thread(target=release_after_parent_publish)
                coordinator.start()
            else:
                release_child.set()

        future.result(timeout=5)

    if coordinator is not None:
        coordinator.join(timeout=5)
        assert not coordinator.is_alive()

    assert not catalog._pending_plugin_catalogs
    assert not parent_can_finalize
    assert i18n.t("plugin.ordered-parent.message") == "parent"
    assert i18n.t("plugin.ordered-child.message") == "child"


def test_callback_registration_and_ownership_are_guarded_together():
    entered = threading.Event()
    release = threading.Event()
    exit_started = threading.Event()
    loader_finished = threading.Event()
    worker_finished = threading.Event()

    class CollidingCallback:
        __name__ = "colliding_callback"

        def __init__(self, *, blocks: bool = False) -> None:
            self.blocks = blocks

        def __call__(self):
            return None

        def __hash__(self) -> int:
            return 1

        def __eq__(self, other):
            if self.blocks and other is candidate:
                entered.set()
                assert release.wait(timeout=5)
            return self is other

    existing_owner_key = CollidingCallback(blocks=True)
    candidate = CollidingCallback()
    callbacks._callback_owners[existing_owner_key] = "existing"

    def load_plugin() -> None:
        with _plugin_loading_context("callback_race"):
            copied_context = contextvars.copy_context()

            def register_in_copied_context() -> None:
                copied_context.run(callbacks.register_callback, "startup", candidate)
                worker_finished.set()

            worker = threading.Thread(target=register_in_copied_context)
            worker.start()
            assert entered.wait(timeout=5)
            exit_started.set()
        loader_finished.set()
        worker.join(timeout=5)

    loader = threading.Thread(target=load_plugin)
    loader.start()
    try:
        assert exit_started.wait(timeout=5)
        time.sleep(0.05)
        assert not loader_finished.is_set()
        assert candidate not in callbacks.get_callbacks(
            "startup", include_disabled=True
        )
        release.set()
        loader.join(timeout=5)
        assert not loader.is_alive()
        assert worker_finished.is_set()
        assert candidate in callbacks.get_callbacks("startup", include_disabled=True)
        assert callbacks.get_callback_owner(candidate) == "callback_race"
    finally:
        release.set()
        loader.join(timeout=5)
        callbacks.unregister_callback("startup", candidate)
        callbacks._callback_owners.pop(candidate, None)
        callbacks._callback_owners.pop(existing_owner_key, None)


def test_root_publish_memory_error_is_atomic(tmp_path, monkeypatch):
    first = _provider(tmp_path / "first", "atomic_first", "first")
    second = _provider(tmp_path / "second", "atomic_second", "second")
    transaction_id = object()
    catalog._pending_plugin_catalogs[transaction_id] = {
        first.owner: first,
        second.owner: second,
    }
    catalog.load_catalog("en-US")
    registry_before = dict(catalog._plugin_catalogs)
    cache_before = dict(catalog._cache)
    generation_before = catalog._generation
    original_merge = catalog._merge_pending_provider
    calls = 0

    def exhausted_merge(target, provider):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise MemoryError("synthetic root publish exhaustion")
        return original_merge(target, provider)

    monkeypatch.setattr(catalog, "_merge_pending_provider", exhausted_merge)

    with pytest.raises(MemoryError, match="root publish exhaustion"):
        catalog._finish_plugin_catalog_load(
            transaction_id, parent_transaction_id=None, succeeded=True
        )

    assert catalog._plugin_catalogs == registry_before
    assert transaction_id not in catalog._pending_plugin_catalogs
    assert catalog._cache == cache_before
    assert catalog._generation == generation_before


def test_child_transfer_memory_error_is_atomic(tmp_path, monkeypatch):
    parent_provider = _provider(tmp_path / "parent", "atomic_parent", "parent")
    first = _provider(tmp_path / "first", "atomic_child_first", "first")
    second = _provider(tmp_path / "second", "atomic_child_second", "second")
    parent_id = object()
    child_id = object()
    parent_before = {parent_provider.owner: parent_provider}
    catalog._pending_plugin_catalogs[parent_id] = dict(parent_before)
    catalog._pending_plugin_catalogs[child_id] = {
        first.owner: first,
        second.owner: second,
    }
    catalog.load_catalog("en-US")
    registry_before = dict(catalog._plugin_catalogs)
    cache_before = dict(catalog._cache)
    generation_before = catalog._generation
    original_merge = catalog._merge_pending_provider
    calls = 0

    def exhausted_merge(target, provider):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise MemoryError("synthetic child transfer exhaustion")
        return original_merge(target, provider)

    monkeypatch.setattr(catalog, "_merge_pending_provider", exhausted_merge)

    with pytest.raises(MemoryError, match="child transfer exhaustion"):
        catalog._finish_plugin_catalog_load(
            child_id, parent_transaction_id=parent_id, succeeded=True
        )

    assert catalog._plugin_catalogs == registry_before
    assert catalog._pending_plugin_catalogs[parent_id] == parent_before
    assert child_id not in catalog._pending_plugin_catalogs
    assert catalog._cache == cache_before
    assert catalog._generation == generation_before


def test_grandchild_same_owner_conflict_is_rejected_immediately(tmp_path):
    original = _catalog_dir(tmp_path / "original", "lineage", "original")
    conflicting = _catalog_dir(tmp_path / "conflicting", "lineage", "conflicting")

    with _plugin_loading_context("lineage"):
        assert i18n.register_plugin_catalog(original)
        with _plugin_loading_context("middle"):
            with _plugin_loading_context("lineage"):
                assert not i18n.register_plugin_catalog(conflicting)

    assert i18n.t("plugin.lineage.message") == "original"


def test_grandchild_namespace_conflict_is_rejected_immediately(tmp_path):
    original = _catalog_dir(tmp_path / "original", "same-name", "original")
    conflicting = _catalog_dir(tmp_path / "conflicting", "same_name", "conflicting")

    with _plugin_loading_context("same-name"):
        assert i18n.register_plugin_catalog(original)
        with _plugin_loading_context("middle"):
            with _plugin_loading_context("same_name"):
                assert not i18n.register_plugin_catalog(conflicting)

    assert i18n.t("plugin.same-name.message") == "original"
