"""Lazy internal lifecycle bridge for optional plugin i18n catalogs."""

from __future__ import annotations

import subprocess
import sys

from code_puppy import _plugin_i18n_lifecycle as lifecycle


def test_unregistered_i18n_lifecycle_hooks_are_noops(monkeypatch):
    monkeypatch.setattr(lifecycle, "_hooks", None)

    lifecycle.finish_i18n_plugin_load(
        object(), parent_transaction_id=None, succeeded=True
    )
    lifecycle.notify_i18n_plugin_state_changed()


def test_registered_i18n_lifecycle_hooks_receive_events(monkeypatch):
    events: list[tuple[object, ...]] = []
    transaction_id = object()
    parent_transaction_id = object()

    def finish_load(transaction_id, *, parent_transaction_id, succeeded):
        events.append(("finish", transaction_id, parent_transaction_id, succeeded))

    def state_changed():
        events.append(("state",))

    monkeypatch.setattr(lifecycle, "_hooks", None)
    lifecycle.register_i18n_lifecycle_hooks(
        finish_load=finish_load, state_changed=state_changed
    )
    lifecycle.finish_i18n_plugin_load(
        transaction_id,
        parent_transaction_id=parent_transaction_id,
        succeeded=True,
    )
    lifecycle.notify_i18n_plugin_state_changed()

    assert events == [
        ("finish", transaction_id, parent_transaction_id, True),
        ("state",),
    ]


def test_plugin_config_without_i18n_uses_unregistered_noop_hook():
    script = """
import sys
from code_puppy.plugins import config
config.get_disabled_plugins = lambda: set()
config.set_value = lambda *_args: None
assert config.set_plugin_disabled('plain_plugin', True)
assert 'code_puppy.i18n' not in sys.modules
assert 'code_puppy.i18n.catalog' not in sys.modules
"""
    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr


def test_plugin_without_i18n_does_not_import_i18n_stack():
    script = """
import sys
from code_puppy.plugins import _plugin_loading_context
assert 'code_puppy.i18n' not in sys.modules
assert 'code_puppy.i18n.catalog' not in sys.modules
with _plugin_loading_context('plain_plugin'):
    pass
assert 'code_puppy.i18n' not in sys.modules
assert 'code_puppy.i18n.catalog' not in sys.modules
"""
    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr
