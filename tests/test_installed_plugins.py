"""Installed plugin entry-point discovery."""

import os
import subprocess
import sys
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


def test_installed_goal_discovery_in_clean_process(tmp_path):
    script = r"""
import sys
from importlib.metadata import entry_points
from unittest.mock import patch

prefix = "code_puppy_core_plugins.wiggum"
points = [p for p in entry_points(group="code_puppy.plugins") if p.name == "wiggum"]
assert len(points) == 1, points
assert points[0].value == prefix + ".register_callbacks"

from code_puppy import callbacks, plugins
from code_puppy.command_line.command_registry import get_command

# Pre-importing the plugin would hide broken entry-point discovery.
assert not any(name.startswith(prefix) for name in sys.modules)
with (
    patch("socket.socket.connect", side_effect=AssertionError("network forbidden")) as connect,
    patch("socket.socket.connect_ex", side_effect=AssertionError("network forbidden")) as connect_ex,
    patch("socket.getaddrinfo", side_effect=AssertionError("network forbidden")) as dns,
):
    loaded = plugins.load_plugin_callbacks()
    assert "wiggum" in loaded["builtin"], loaded
    assert loaded["user"] == loaded["project"] == []
    for name in ("goal", "goal_stop"):
        command = get_command(name)
        assert command is not None, name
        assert command.handler.__module__ == points[0].value
    hooks = [
        hook for hook in callbacks.get_callbacks("interactive_turn_end")
        if hook.__module__.startswith(prefix)
    ]
    assert len(hooks) == 1, hooks
    assert hooks[0].__module__ == points[0].value
    plugin = sys.modules[points[0].value]
    assert callable(getattr(plugin, "run_with_cancel_controls", None)), "missing goal cancellation controls"
    assert plugins.load_plugin_callbacks() == {"builtin": [], "user": [], "project": []}
    assert callbacks.get_callbacks("interactive_turn_end").count(hooks[0]) == 1
    connect.assert_not_called()
    connect_ex.assert_not_called()
    dns.assert_not_called()
"""
    env = os.environ.copy()
    for name in (
        "HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_CACHE_HOME",
        "XDG_STATE_HOME",
        "XDG_RUNTIME_DIR",
        "XDG_CONFIG_DIRS",
        "XDG_DATA_DIRS",
    ):
        root = tmp_path / name.lower()
        root.mkdir(mode=0o700)
        env[name] = str(root)
    env["USERPROFILE"] = env["HOME"]
    result = subprocess.run(
        [sys.executable, "-I", "-c", script],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_legacy_loader_skips_installed_duplicate(tmp_path):
    duplicate = tmp_path / "duplicate"
    duplicate.mkdir()
    (duplicate / "register_callbacks.py").write_text(
        "raise AssertionError('must not import')", encoding="utf-8"
    )

    assert plugins._load_builtin_plugins(tmp_path, {"duplicate"}) == []
