"""In-tree plugins get a pre-import startup hook, inside the splash window."""

import ast
import importlib
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

import code_puppy
from code_puppy import early_startup

REPO_ROOT = Path(__file__).resolve().parents[1]
PKG = "early_pkg"


def _write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture
def plugins(tmp_path, monkeypatch):
    """A throwaway ``early_pkg.plugins`` tree wired in place of the real one."""
    root = tmp_path / PKG
    _write(root / "__init__.py", "calls = []\n")
    _write(root / "plugins" / "__init__.py")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(early_startup, "_PLUGINS_DIR", root / "plugins")
    monkeypatch.setattr(early_startup, "_PLUGINS_PACKAGE", f"{PKG}.plugins")
    yield root / "plugins"
    for name in [m for m in sys.modules if m == PKG or m.startswith(f"{PKG}.")]:
        del sys.modules[name]


def _add_hook(plugins: Path, name: str, body: str = "") -> None:
    _write(plugins / name / "__init__.py")
    _write(
        plugins / name / "early_startup.py",
        f"import {PKG}\n\ndef run():\n    {PKG}.calls.append({name!r})\n{body}",
    )


def _calls() -> list[str]:
    return importlib.import_module(PKG).calls


def test_discovers_only_plugins_that_ship_a_hook_and_sorts_them(plugins):
    _add_hook(plugins, "zeta")
    _add_hook(plugins, "alpha")
    _write(plugins / "no_hook" / "__init__.py")
    _write(plugins / "_private" / "early_startup.py", "def run(): pass\n")
    _write(plugins / ".hidden" / "early_startup.py", "def run(): pass\n")
    _write(plugins / "plain_file.py")

    assert early_startup.discover() == ["alpha", "zeta"]


def test_missing_plugins_directory_is_a_no_op(plugins, monkeypatch):
    monkeypatch.setattr(early_startup, "_PLUGINS_DIR", plugins / "does_not_exist")

    assert early_startup.discover() == []
    early_startup.run_early_startup()


def test_runs_every_hook_in_name_order(plugins):
    _add_hook(plugins, "b")
    _add_hook(plugins, "a")
    _add_hook(plugins, "c")

    early_startup.run_early_startup()

    assert _calls() == ["a", "b", "c"]


def test_failing_hook_is_logged_and_does_not_stop_the_others(plugins, caplog):
    _add_hook(plugins, "a")
    _add_hook(plugins, "b", body="    raise RuntimeError('boom')\n")
    _add_hook(plugins, "c")

    with caplog.at_level("DEBUG", logger=early_startup.logger.name):
        early_startup.run_early_startup()

    assert _calls() == ["a", "b", "c"]
    assert "early startup hook of plugin 'b' failed" in caplog.text


def test_hook_that_cannot_even_be_imported_is_skipped(plugins):
    _add_hook(plugins, "a")
    _write(plugins / "b" / "__init__.py")
    _write(plugins / "b" / "early_startup.py", "raise ImportError('missing dep')\n")
    _add_hook(plugins, "c")

    early_startup.run_early_startup()

    assert _calls() == ["a", "c"]


def test_ctrl_c_during_a_hook_still_propagates(plugins):
    _add_hook(plugins, "a", body="    raise KeyboardInterrupt\n")

    with pytest.raises(KeyboardInterrupt):
        early_startup.run_early_startup()


def test_module_stays_stdlib_only(tmp_path):
    code = (
        "import sys, code_puppy\n"
        "before = set(sys.modules)\n"
        "import code_puppy.early_startup\n"
        "print(sorted(set(sys.modules) - before))\n"
    )
    env = {
        **os.environ,
        "HOME": str(tmp_path),
        "USERPROFILE": str(tmp_path),
        "PYTHONPATH": str(REPO_ROOT),
    }
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )

    new_modules = ast.literal_eval(result.stdout.strip())

    offenders = [
        m
        for m in new_modules
        if m.startswith("code_puppy.") and m != "code_puppy.early_startup"
    ] + [
        m
        for m in new_modules
        if m.split(".")[0] in {"pydantic_ai", "rich", "prompt_toolkit", "httpx"}
    ]
    assert offenders == []


@pytest.fixture
def isolated_main_import():
    """Let a test import ``code_puppy.main`` afresh, then put things back."""
    original = sys.modules.pop("code_puppy.main", None)
    yield
    sys.modules.pop("code_puppy.main", None)
    vars(code_puppy).pop("main", None)
    if original is not None:
        sys.modules["code_puppy.main"] = original
        code_puppy.main = original


def test_main_runs_the_hook_inside_the_splash_before_the_runner_import(
    monkeypatch, isolated_main_import
):
    events: list[str] = []

    class _Splash:
        def stop(self):
            events.append("splash.stop")

    class _RunnerModule(types.ModuleType):
        def __getattr__(self, name):  # ``from ... import main_entry`` lands here
            if name != "main_entry":  # the import system also probes __path__ etc.
                raise AttributeError(name)
            events.append("cli_runner import")
            return lambda: None

    splash = types.ModuleType("code_puppy.splash")
    splash.start_splash = lambda: events.append("splash.start") or _Splash()
    error_hooks = types.ModuleType("code_puppy.error_hooks")
    error_hooks.install_error_hooks = lambda: events.append("error_hooks")
    early = types.ModuleType("code_puppy.early_startup")
    early.run_early_startup = lambda: events.append("early_startup")
    for module in (
        splash,
        error_hooks,
        early,
        _RunnerModule("code_puppy.cli_runner"),
    ):
        monkeypatch.setitem(sys.modules, module.__name__, module)

    importlib.import_module("code_puppy.main")

    assert events == [
        "splash.start",
        "error_hooks",
        "early_startup",
        "cli_runner import",
        "splash.stop",
    ]
