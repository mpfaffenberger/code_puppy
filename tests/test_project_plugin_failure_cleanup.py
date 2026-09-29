"""Failure cleanup boundaries for trusted project-plugin imports."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from code_puppy import plugins


def _plugin(root: Path, name: str) -> Path:
    plugin_dir = root / name
    plugin_dir.mkdir(parents=True)
    return plugin_dir


def test_failed_init_removes_absolute_root_helper_and_retry_uses_repair(tmp_path):
    root = tmp_path / "plugins"
    plugin_dir = _plugin(root, "absolute_init_retry")
    helper_name = "absolute_init_retry_helper"
    helper = root / f"{helper_name}.py"
    helper.write_text("VALUE = 'broken'\n", encoding="utf-8")
    (plugin_dir / "__init__.py").write_text(
        f"import {helper_name}\nraise RuntimeError('broken init')\n",
        encoding="utf-8",
    )
    (plugin_dir / "register_callbacks.py").write_text("LOADED = True\n")
    plugins._ensure_project_ns()

    try:
        assert not plugins._load_one_project_plugin(plugin_dir, plugin_dir.name)
        assert helper_name not in sys.modules

        helper.write_text("VALUE = 'repaired'\n", encoding="utf-8")
        (plugin_dir / "__init__.py").write_text(
            f"import {helper_name}\nassert {helper_name}.VALUE == 'repaired'\n",
            encoding="utf-8",
        )
        assert plugins._load_one_project_plugin(plugin_dir, plugin_dir.name)
        assert sys.modules[helper_name].VALUE == "repaired"
    finally:
        sys.modules.pop(helper_name, None)


def test_failed_callbacks_remove_absolute_root_helper_and_retry_uses_repair(tmp_path):
    root = tmp_path / "plugins"
    plugin_dir = _plugin(root, "absolute_callbacks_retry")
    helper_name = "absolute_callbacks_retry_helper"
    helper = root / f"{helper_name}.py"
    helper.write_text("VALUE = 'broken'\n", encoding="utf-8")
    (plugin_dir / "__init__.py").write_text("LOADED = True\n")
    callbacks_file = plugin_dir / "register_callbacks.py"
    callbacks_file.write_text(
        f"import {helper_name}\nraise RuntimeError('broken callbacks')\n",
        encoding="utf-8",
    )
    plugins._ensure_project_ns()

    try:
        assert not plugins._load_one_project_plugin(plugin_dir, plugin_dir.name)
        assert helper_name not in sys.modules

        helper.write_text("VALUE = 'repaired'\n", encoding="utf-8")
        callbacks_file.write_text(
            f"import {helper_name}\nassert {helper_name}.VALUE == 'repaired'\n",
            encoding="utf-8",
        )
        assert plugins._load_one_project_plugin(plugin_dir, plugin_dir.name)
        assert sys.modules[helper_name].VALUE == "repaired"
    finally:
        sys.modules.pop(helper_name, None)


def test_failed_load_preserves_preexisting_root_helper_identity(tmp_path):
    root = tmp_path / "plugins"
    plugin_dir = _plugin(root, "absolute_preexisting")
    helper_name = "absolute_preexisting_helper"
    helper = types.ModuleType(helper_name)
    helper.__file__ = str(root / f"{helper_name}.py")
    sys.modules[helper_name] = helper
    (plugin_dir / "register_callbacks.py").write_text(
        f"import {helper_name}\nraise RuntimeError('broken callbacks')\n",
        encoding="utf-8",
    )
    plugins._ensure_project_ns()

    try:
        assert not plugins._load_one_project_plugin(plugin_dir, plugin_dir.name)
        assert sys.modules[helper_name] is helper
    finally:
        sys.modules.pop(helper_name, None)


def test_pycache_prefix_restored_when_setup_snapshot_raises(tmp_path, monkeypatch):
    plugin_dir = _plugin(tmp_path / "plugins", "snapshot_oom")
    (plugin_dir / "register_callbacks.py").write_text("LOADED = True\n")
    original_prefix = object()
    monkeypatch.setattr(sys, "pycache_prefix", original_prefix)

    def exhausted_snapshot():
        raise MemoryError("synthetic snapshot exhaustion")

    monkeypatch.setattr(
        plugins, "_snapshot_project_modules", exhausted_snapshot, raising=False
    )

    with pytest.raises(MemoryError, match="snapshot exhaustion"):
        plugins._load_one_project_plugin(plugin_dir, plugin_dir.name)
    assert sys.pycache_prefix is original_prefix


def test_pycache_prefix_restored_when_failure_cleanup_raises(tmp_path, monkeypatch):
    plugin_dir = _plugin(tmp_path / "plugins", "cleanup_oom")
    (plugin_dir / "register_callbacks.py").write_text(
        "raise RuntimeError('load failed')\n", encoding="utf-8"
    )
    original_prefix = object()
    monkeypatch.setattr(sys, "pycache_prefix", original_prefix)

    def exhausted_cleanup(*_args, **_kwargs):
        raise MemoryError("synthetic cleanup exhaustion")

    monkeypatch.setattr(
        plugins, "_restore_failed_project_modules", exhausted_cleanup, raising=False
    )

    with pytest.raises(MemoryError, match="cleanup exhaustion"):
        plugins._load_one_project_plugin(plugin_dir, plugin_dir.name)
    assert sys.pycache_prefix is original_prefix
