"""Tests for deterministic callback ordering across hot-loaded plugins."""

from __future__ import annotations

import logging
import threading

import pytest

from code_puppy import callbacks

_PHASE = "notification"


class _UnhashableCallable:
    __hash__ = None

    def __call__(self, *args, **kwargs):
        _ = args, kwargs
        return "unhashable"


class _HashableCallable:
    def __call__(self, *args, **kwargs):
        _ = args, kwargs
        return "hashable"


def _remove(*functions) -> None:
    for function in functions:
        callbacks.unregister_callback(_PHASE, function)


def test_higher_priority_runs_later_even_when_normal_callback_loads_late():
    def normal_first(*args, **kwargs):
        return None

    def finalizer(*args, **kwargs):
        return None

    def hot_loaded_normal(*args, **kwargs):
        return None

    try:
        callbacks.register_callback(_PHASE, normal_first)
        callbacks.register_callback(
            _PHASE,
            finalizer,
            priority=callbacks.FINALIZER_CALLBACK_PRIORITY,
        )
        callbacks.register_callback(_PHASE, hot_loaded_normal)

        registered = callbacks.get_callbacks(_PHASE, include_disabled=True)

        assert registered.index(normal_first) < registered.index(finalizer)
        assert registered.index(hot_loaded_normal) < registered.index(finalizer)
    finally:
        _remove(normal_first, finalizer, hot_loaded_normal)


def test_equal_priorities_preserve_registration_order():
    def first(*args, **kwargs):
        return None

    def second(*args, **kwargs):
        return None

    try:
        callbacks.register_callback(_PHASE, first, priority=7)
        callbacks.register_callback(_PHASE, second, priority=7)

        registered = callbacks.get_callbacks(_PHASE, include_disabled=True)

        assert registered.index(first) < registered.index(second)
    finally:
        _remove(first, second)


def test_duplicate_registration_updates_priority_without_duplication():
    def callback(*args, **kwargs):
        return None

    def peer(*args, **kwargs):
        return None

    try:
        callbacks.register_callback(_PHASE, callback)
        callbacks.register_callback(_PHASE, peer, priority=10)
        callbacks.register_callback(_PHASE, callback, priority=20)

        registered = callbacks.get_callbacks(_PHASE, include_disabled=True)

        assert registered.count(callback) == 1
        assert registered.index(peer) < registered.index(callback)
    finally:
        _remove(callback, peer)


def test_unregister_discards_priority_before_reregistration():
    def callback(*args, **kwargs):
        return None

    def peer(*args, **kwargs):
        return None

    try:
        callbacks.register_callback(_PHASE, callback, priority=20)
        assert callbacks.unregister_callback(_PHASE, callback)
        callbacks.register_callback(_PHASE, callback)
        callbacks.register_callback(_PHASE, peer, priority=10)

        registered = callbacks.get_callbacks(_PHASE, include_disabled=True)

        assert registered.index(callback) < registered.index(peer)
    finally:
        _remove(callback, peer)


@pytest.mark.parametrize("method_name", ["append", "__len__"])
def test_builtin_bound_method_deduplicates_and_unregisters_by_fresh_access(
    method_name,
):
    sink = []

    try:
        callbacks.register_callback(_PHASE, getattr(sink, method_name))
        callbacks.register_callback(_PHASE, getattr(sink, method_name))

        registered = callbacks.get_callbacks(_PHASE, include_disabled=True)

        assert (
            sum(callback == getattr(sink, method_name) for callback in registered) == 1
        )
        assert callbacks.unregister_callback(_PHASE, getattr(sink, method_name))
        assert getattr(sink, method_name) not in callbacks.get_callbacks(
            _PHASE, include_disabled=True
        )
    finally:
        _remove(getattr(sink, method_name))


def test_class_bound_builtin_deduplicates_and_unregisters():
    try:
        callbacks.register_callback(_PHASE, dict.fromkeys)
        callbacks.register_callback(_PHASE, dict.fromkeys)

        registered = callbacks.get_callbacks(_PHASE, include_disabled=True)

        assert sum(callback == dict.fromkeys for callback in registered) == 1
        assert callbacks.unregister_callback(_PHASE, dict.fromkeys)
    finally:
        _remove(dict.fromkeys)


def test_forged_method_attributes_do_not_collapse_distinct_callables():
    shared_self = object()

    def forged_function():
        return None

    class ForgedCallable:
        __self__ = shared_self
        __func__ = forged_function

        def __call__(self):
            return None

    first = ForgedCallable()
    second = ForgedCallable()
    try:
        callbacks.register_callback(_PHASE, first)
        callbacks.register_callback(_PHASE, second)

        registered = callbacks.get_callbacks(_PHASE, include_disabled=True)

        assert first in registered
        assert second in registered
    finally:
        _remove(first, second)


def test_hostile_callable_attributes_are_not_used_for_identity():
    class HostileCallable:
        def __getattribute__(self, name):
            if name in {"__self__", "__func__", "__name__"}:
                raise AssertionError(
                    "identity must not inspect forged method attributes"
                )
            return super().__getattribute__(name)

        def __call__(self):
            return None

    callback = HostileCallable()
    try:
        callbacks.register_callback(_PHASE, callback)
        assert callback in callbacks.get_callbacks(_PHASE, include_disabled=True)
    finally:
        _remove(callback)


def test_unregister_reregister_preserves_disabled_plugin_owner(monkeypatch):
    snapshot = callbacks.snapshot_callback_registry()

    def owned(*args, **kwargs):
        _ = args, kwargs

    try:
        callbacks.set_loading_context("disabled-plugin")
        callbacks.register_callback(_PHASE, owned)
        callbacks.clear_loading_context()
        monkeypatch.setattr(
            callbacks, "_get_disabled_plugins", lambda: {"disabled-plugin"}
        )
        assert owned not in callbacks.get_callbacks(_PHASE)

        assert callbacks.unregister_callback(_PHASE, owned)
        callbacks.register_callback(_PHASE, owned)

        assert callbacks.get_callback_owner(owned) == "disabled-plugin"
        assert owned not in callbacks.get_callbacks(_PHASE)
    finally:
        callbacks.restore_callback_registry(snapshot)


def test_nested_loading_context_restores_outer_owner():
    snapshot = callbacks.snapshot_callback_registry()

    def outer():
        return None

    def inner():
        return None

    try:
        callbacks.set_loading_context("outer-plugin")
        callbacks.set_loading_context("inner-plugin")
        callbacks.register_callback(_PHASE, inner)
        callbacks.clear_loading_context()
        callbacks.register_callback(_PHASE, outer)
        callbacks.clear_loading_context()

        assert callbacks.get_callback_owner(inner) == "inner-plugin"
        assert callbacks.get_callback_owner(outer) == "outer-plugin"
        assert callbacks.get_loading_context() is None
    finally:
        callbacks.restore_callback_registry(snapshot)


def test_concurrent_loading_contexts_do_not_cross_attribute_ownership():
    snapshot = callbacks.snapshot_callback_registry()
    barrier = threading.Barrier(2)

    def first():
        return None

    def second():
        return None

    def register(owner, callback):
        callbacks.set_loading_context(owner)
        barrier.wait(timeout=1)
        callbacks.register_callback(_PHASE, callback)
        callbacks.clear_loading_context()

    try:
        threads = [
            threading.Thread(target=register, args=("first-plugin", first)),
            threading.Thread(target=register, args=("second-plugin", second)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=1)

        assert callbacks.get_callback_owner(first) == "first-plugin"
        assert callbacks.get_callback_owner(second) == "second-plugin"
    finally:
        callbacks.restore_callback_registry(snapshot)


def test_reserved_terminal_callback_runs_after_every_public_priority():
    def terminal(*args, **kwargs):
        _ = args, kwargs

    def public(*args, **kwargs):
        _ = args, kwargs

    try:
        callbacks._register_terminal_callback(_PHASE, terminal)
        callbacks.register_callback(
            _PHASE,
            public,
            priority=callbacks._TERMINAL_CALLBACK_PRIORITY - 1,
        )

        registered = callbacks.get_callbacks(_PHASE, include_disabled=True)

        assert registered.index(public) < registered.index(terminal)
        with pytest.raises(ValueError, match="reserved"):
            callbacks.register_callback(
                _PHASE,
                public,
                priority=callbacks._TERMINAL_CALLBACK_PRIORITY,
            )
    finally:
        _remove(terminal, public)


def test_registry_snapshot_restores_owner_and_priority_together():
    original = callbacks.snapshot_callback_registry()

    def prioritized():
        return None

    def normal():
        return None

    try:
        callbacks.clear_callbacks(_PHASE)
        callbacks.set_loading_context("owned-plugin")
        callbacks.register_callback(_PHASE, prioritized, priority=20)
        callbacks.clear_loading_context()
        callbacks.register_callback(_PHASE, normal)
        expected = callbacks.snapshot_callback_registry()

        callbacks.clear_callbacks(_PHASE)
        callbacks.restore_callback_registry(expected)

        registered = callbacks.get_callbacks(_PHASE, include_disabled=True)
        assert registered == [normal, prioritized]
        assert callbacks.get_callback_owner(prioritized) == "owned-plugin"
    finally:
        callbacks.restore_callback_registry(original)


def test_registry_logging_occurs_after_releasing_registry_lock():
    snapshot = callbacks.snapshot_callback_registry()
    completed = []

    class ReentrantHandler(logging.Handler):
        def emit(self, record):
            _ = record
            worker = threading.Thread(
                target=lambda: completed.append(callbacks.count_callbacks(_PHASE))
            )
            worker.start()
            worker.join(timeout=0.5)
            assert not worker.is_alive()

    def callback():
        return None

    handler = ReentrantHandler()
    previous_level = callbacks.logger.level
    callbacks.logger.addHandler(handler)
    callbacks.logger.setLevel(logging.DEBUG)
    try:
        callbacks.register_callback(_PHASE, callback)
        callbacks.register_callback(_PHASE, callback, priority=10)
        callbacks.clear_callbacks(_PHASE)
    finally:
        callbacks.logger.removeHandler(handler)
        callbacks.logger.setLevel(previous_level)
        callbacks.restore_callback_registry(snapshot)

    assert completed


def test_registration_and_get_snapshot_are_atomic():
    snapshot = callbacks.snapshot_callback_registry()
    append_started = threading.Event()
    release_append = threading.Event()
    getter_done = threading.Event()
    observed = []

    class BlockingList(list):
        def append(self, item):
            append_started.set()
            assert release_append.wait(timeout=2)
            super().append(item)

    def callback():
        return None

    try:
        callbacks._callbacks[_PHASE] = BlockingList()
        register_thread = threading.Thread(
            target=callbacks.register_callback,
            args=(_PHASE, callback),
            kwargs={"priority": 10},
        )
        register_thread.start()
        assert append_started.wait(timeout=1)

        def get_snapshot():
            observed.extend(callbacks.get_callbacks(_PHASE, include_disabled=True))
            getter_done.set()

        getter_thread = threading.Thread(target=get_snapshot)
        getter_thread.start()
        assert not getter_done.wait(timeout=0.05)
        release_append.set()
        register_thread.join(timeout=1)
        getter_thread.join(timeout=1)

        assert observed == [callback]
    finally:
        release_append.set()
        callbacks.restore_callback_registry(snapshot)


@pytest.mark.parametrize("callback_type", [_UnhashableCallable, _HashableCallable])
def test_callable_objects_support_priority_and_execution(callback_type):
    callback = callback_type()

    try:
        callbacks.register_callback(_PHASE, callback, priority=7)

        assert callback in callbacks.get_callbacks(_PHASE, include_disabled=True)
        assert callbacks._trigger_callbacks_sync(_PHASE, "message")[-1] == callback()
    finally:
        _remove(callback)


@pytest.mark.parametrize("priority", [True, 1.5, "10", None])
def test_priority_must_be_a_real_integer(priority):
    def callback(*args, **kwargs):
        return None

    with pytest.raises(TypeError, match="priority must be an int"):
        callbacks.register_callback(_PHASE, callback, priority=priority)

    assert callback not in callbacks.get_callbacks(_PHASE, include_disabled=True)
