"""Plugin load failures reach errors.log once, named by tier and plugin."""

from __future__ import annotations

import importlib
import logging
import re
import sys
from collections import OrderedDict
from pathlib import Path

import pytest

from code_puppy import error_logging, plugins

BAD = "bad_plugin"
GOOD = "good_plugin"

# One failing body per failure kind; file-based tiers write it to disk and the
# callable-based tiers exec it, so both raise the identical exception.
FAILING_SOURCE = {
    "runtime": "raise RuntimeError('boom')\n",
    "import": "import plugin_dependency_that_does_not_exist\n",
}
ERROR_TYPE = {"runtime": "RuntimeError", "import": "ModuleNotFoundError"}
LEVEL = {"runtime": logging.ERROR, "import": logging.WARNING}


@pytest.fixture
def isolated_log(tmp_path, monkeypatch):
    """Redirect errors.log into tmp_path, as the error-hook tests do."""
    log_file = tmp_path / "errors.log"
    monkeypatch.setattr(error_logging, "LOGS_DIR", str(tmp_path))
    monkeypatch.setattr(error_logging, "ERROR_LOG_FILE", str(log_file))
    monkeypatch.setattr(error_logging, "_fallback", OrderedDict())
    return log_file


@pytest.fixture(autouse=True)
def _restore_import_state():
    """Loaders add sys.path entries and sys.modules keys; undo them."""
    path_before = list(sys.path)
    modules_before = set(sys.modules)
    plugins._project_plugin_status.clear()
    yield
    sys.path[:] = path_before
    for name in set(sys.modules) - modules_before:
        del sys.modules[name]
    plugins._project_plugin_status.clear()


@pytest.fixture
def trust_all(monkeypatch):
    monkeypatch.setattr(plugins._trust, "get_trust_status", lambda *_a: "trusted")
    monkeypatch.setattr(
        "code_puppy.plugins.config.is_plugin_disabled", lambda _name: False
    )


def _entries(log_file: Path) -> list[str]:
    if not log_file.exists():
        return []
    chunks = re.split(r"(?m)^(?=Error Type:)", log_file.read_text())
    return [c for c in chunks if c.startswith("Error Type:")]


def _write_plugin(root: Path, name: str, source: str, *, via_init: bool = False):
    plugin_dir = root / name
    plugin_dir.mkdir(parents=True)
    (plugin_dir / ("__init__.py" if via_init else "register_callbacks.py")).write_text(
        source
    )


def _write_pair(root: Path, kind: str, *, via_init: bool = False) -> None:
    _write_plugin(root, BAD, FAILING_SOURCE[kind], via_init=via_init)
    _write_plugin(root, GOOD, "LOADED = True\n", via_init=via_init)


class _FakeEntryPoint:
    def __init__(self, name: str, kind: str | None):
        self.name = name
        self._kind = kind

    def load(self) -> None:
        if self._kind:
            exec(FAILING_SOURCE[self._kind], {})


def _drive_installed(root, monkeypatch, kind):
    points = [_FakeEntryPoint(BAD, kind), _FakeEntryPoint(GOOD, None)]
    monkeypatch.setattr(plugins, "entry_points", lambda **_kw: points)
    return plugins._load_installed_plugins()


def _drive_builtin(root, monkeypatch, kind):
    _write_plugin(root, BAD, "", via_init=False)
    _write_plugin(root, GOOD, "", via_init=False)

    def fake_import(name):
        if f".{BAD}." in name:
            exec(FAILING_SOURCE[kind], {})

    class _Shim:
        import_module = staticmethod(fake_import)

        def __getattr__(self, attr):
            return getattr(importlib, attr)

    monkeypatch.setattr(plugins, "importlib", _Shim())
    return plugins._load_builtin_plugins(root)


def _drive_user(root, monkeypatch, kind):
    _write_pair(root, kind)
    return plugins._load_user_plugins(root)


def _drive_user_init(root, monkeypatch, kind):
    _write_pair(root, kind, via_init=True)
    return plugins._load_user_plugins(root)


def _drive_project(root, monkeypatch, kind):
    _write_pair(root, kind)
    return plugins._load_project_plugins(root, set(), set())


# (driver, qualname, failure kind, constant phrase before the plugin name)
SITES = [
    (
        _drive_installed,
        "_load_installed_plugins",
        "import",
        "import the installed plugin",
    ),
    (
        _drive_installed,
        "_load_installed_plugins",
        "runtime",
        "load the installed plugin",
    ),
    (_drive_builtin, "_load_builtin_plugins", "import", "import the builtin plugin"),
    (_drive_builtin, "_load_builtin_plugins", "runtime", "load the builtin plugin"),
    (_drive_user, "_load_user_plugins", "import", "import the user plugin"),
    (_drive_user, "_load_user_plugins", "runtime", "load the user plugin"),
    (
        _drive_user_init,
        "_load_user_plugins",
        "runtime",
        "execute the user plugin package",
    ),
    (_drive_project, "_load_one_project_plugin", "import", "import the project plugin"),
    (_drive_project, "_load_one_project_plugin", "runtime", "load the project plugin"),
]


@pytest.mark.parametrize(
    ("driver", "qualname", "kind", "phrase"),
    SITES,
    ids=[f"{s[1]}-{s[3].replace(' ', '_')}" for s in SITES],
)
def test_load_failure_writes_one_named_entry(
    driver,
    qualname,
    kind,
    phrase,
    isolated_log,
    trust_all,
    tmp_path,
    monkeypatch,
    caplog,
):
    caplog.set_level(logging.WARNING, logger="code_puppy.plugins")

    loaded = driver(tmp_path / "plugins", monkeypatch, kind)

    assert loaded == [GOOD]
    entries = _entries(isolated_log)
    assert len(entries) == 1
    assert entries[0].startswith(f"Error Type: {ERROR_TYPE[kind]}\n")
    assert (
        f"Context: code_puppy.plugins::{qualname}: startup/plugins: {phrase} {BAD}\n"
        in entries[0]
    )
    # The pre-existing log line is untouched, so stderr is unchanged.
    kept = [r for r in caplog.records if BAD in r.getMessage()]
    assert [r.levelno for r in kept] == [LEVEL[kind]]


def test_load_plugin_callbacks_survives_failing_user_plugin(
    isolated_log, tmp_path, monkeypatch
):
    user_dir = tmp_path / "user_plugins"
    _write_pair(user_dir, "runtime")
    monkeypatch.setattr(plugins, "_PLUGINS_LOADED", False)
    monkeypatch.setattr(
        plugins, "_loaded_plugin_names", {"builtin": [], "user": [], "project": []}
    )
    monkeypatch.setattr(plugins, "USER_PLUGINS_DIR", user_dir)
    monkeypatch.setattr(plugins, "entry_points", lambda **_kw: [])
    monkeypatch.setattr(plugins, "_load_builtin_plugins", lambda *_a, **_kw: [])
    monkeypatch.setattr(plugins, "get_project_plugins_directory", lambda: None)

    assert plugins.load_plugin_callbacks() == {
        "builtin": [],
        "user": [GOOD],
        "project": [],
    }
    entries = _entries(isolated_log)
    assert len(entries) == 1
    assert f"load the user plugin {BAD}" in entries[0]


@pytest.mark.parametrize(
    ("has_project_dir", "expected_dir", "expect_debug"),
    [(True, True, True), (False, False, False)],
    ids=["unreadable-user-dir", "missing-project-dir"],
)
def test_missing_directories_are_expected_and_write_nothing(
    has_project_dir,
    expected_dir,
    expect_debug,
    isolated_log,
    tmp_path,
    monkeypatch,
    caplog,
):
    project = tmp_path / "repo"
    if has_project_dir:
        (project / ".code_puppy" / "plugins").mkdir(parents=True)
    else:
        project.mkdir()
    monkeypatch.chdir(project)
    monkeypatch.setattr(plugins, "USER_PLUGINS_DIR", tmp_path / "no_such_user_dir")
    caplog.set_level(logging.DEBUG, logger="code_puppy.plugins")

    result = plugins.get_project_plugins_directory()

    assert (result is not None) is expected_dir
    assert _entries(isolated_log) == []
    debug = [
        r for r in caplog.records if "get_project_plugins_directory" in r.getMessage()
    ]
    assert len(debug) == int(expect_debug)
    assert all(r.levelno == logging.DEBUG and r.exc_info for r in debug)
