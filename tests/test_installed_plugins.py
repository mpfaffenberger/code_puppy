"""Installed plugin entry-point discovery."""

import threading
from types import SimpleNamespace
from unittest.mock import patch

from code_puppy import plugins


class FakeEntryPoint:
    def __init__(self, name, callback):
        self.name = name
        self._callback = callback

    def load(self):
        return self._callback()


def test_installed_plugins_load_deterministically_with_context():
    events = []
    points = [
        FakeEntryPoint("zeta", lambda: events.append("zeta")),
        FakeEntryPoint("alpha", lambda: events.append("alpha")),
    ]

    transaction = SimpleNamespace(guard=threading.RLock())

    with (
        patch.object(plugins, "entry_points", return_value=points),
        patch.object(
            plugins,
            "set_loading_context",
            side_effect=lambda name, _transaction: events.append(name),
        ),
        patch.object(plugins, "_get_loading_transaction", return_value=transaction),
        patch.object(
            plugins,
            "_deactivate_loading_transaction",
            return_value=(None, True),
        ),
        patch.object(
            plugins,
            "clear_loading_context",
            side_effect=lambda _token: events.append("clear"),
        ),
    ):
        assert plugins._load_installed_plugins() == ["alpha", "zeta"]

    assert events == ["alpha", "alpha", "clear", "zeta", "zeta", "clear"]


def test_same_name_tier_policy_is_passed_to_each_loader(monkeypatch, tmp_path):
    """Installed wins user; trusted project supersedes user and loads last."""
    project_dir = tmp_path / ".code_puppy" / "plugins"
    project_plugin = project_dir / "shared-project"
    project_plugin.mkdir(parents=True)
    (project_plugin / "register_callbacks.py").write_text("LOADED = True\n")
    observed: dict[str, set[str]] = {}

    monkeypatch.setattr(plugins, "_PLUGINS_LOADED", False)
    monkeypatch.setattr(
        plugins,
        "_loaded_plugin_names",
        {"builtin": [], "user": [], "project": []},
    )
    monkeypatch.setattr(plugins, "get_project_plugins_directory", lambda: project_dir)
    monkeypatch.setattr(plugins._trust, "is_plugin_trusted", lambda *_args: True)
    monkeypatch.setattr(
        plugins, "_load_installed_plugins", lambda: ["shared-installed"]
    )

    def load_legacy(_directory, skip_names):
        observed["legacy_skip"] = set(skip_names)
        return ["legacy"]

    def load_user(_directory, skip_names):
        observed["user_skip"] = set(skip_names)
        return []

    def load_project(_directory, builtin_names, user_names):
        observed["project_builtins"] = set(builtin_names)
        observed["project_users"] = set(user_names)
        return ["shared-project"]

    monkeypatch.setattr(plugins, "_load_builtin_plugins", load_legacy)
    monkeypatch.setattr(plugins, "_load_user_plugins", load_user)
    monkeypatch.setattr(plugins, "_load_project_plugins", load_project)

    assert plugins.load_plugin_callbacks() == {
        "builtin": ["shared-installed", "legacy"],
        "user": [],
        "project": ["shared-project"],
    }
    assert observed == {
        "legacy_skip": {"shared-installed"},
        "user_skip": {"shared-installed", "legacy", "shared-project"},
        "project_builtins": {"shared-installed", "legacy"},
        "project_users": set(),
    }


def test_installed_plugin_failures_are_isolated(caplog):
    def fail():
        raise RuntimeError("boom")

    points = [FakeEntryPoint("broken", fail), FakeEntryPoint("healthy", lambda: None)]
    with (
        patch.object(plugins, "entry_points", return_value=points),
    ):
        assert plugins._load_installed_plugins() == ["healthy"]

    assert "broken" in caplog.text


def test_legacy_loader_skips_installed_duplicate(tmp_path):
    duplicate = tmp_path / "duplicate"
    duplicate.mkdir()
    (duplicate / "register_callbacks.py").write_text(
        "raise AssertionError('must not import')", encoding="utf-8"
    )

    assert plugins._load_builtin_plugins(tmp_path, {"duplicate"}) == []
