"""Tests for the project-plugin trust store (code_puppy.plugins.trust)."""

from __future__ import annotations

from pathlib import Path

import pytest

from code_puppy.plugins import trust


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path: Path, monkeypatch):
    """Point the trust store at a throwaway file for every test."""
    monkeypatch.setattr(trust, "TRUST_STORE_FILE", tmp_path / "trusted_plugins.json")


@pytest.fixture()
def plugin_dir(tmp_path: Path) -> Path:
    d = tmp_path / "proj" / ".code_puppy" / "plugins" / "my_plugin"
    d.mkdir(parents=True)
    (d / "register_callbacks.py").write_text("# hello\n")
    return d


@pytest.fixture()
def project_root(plugin_dir: Path) -> Path:
    return plugin_dir.parent.parent.parent


class TestComputePluginHash:
    def test_deterministic(self, plugin_dir: Path):
        assert trust.compute_plugin_hash(plugin_dir) == trust.compute_plugin_hash(
            plugin_dir
        )

    def test_content_change_changes_hash(self, plugin_dir: Path):
        before = trust.compute_plugin_hash(plugin_dir)
        (plugin_dir / "register_callbacks.py").write_text("# tampered\n")
        assert trust.compute_plugin_hash(plugin_dir) != before

    def test_new_file_changes_hash(self, plugin_dir: Path):
        before = trust.compute_plugin_hash(plugin_dir)
        (plugin_dir / "payload.py").write_text("x = 1\n")
        assert trust.compute_plugin_hash(plugin_dir) != before

    def test_rename_changes_hash(self, plugin_dir: Path):
        (plugin_dir / "a.py").write_text("same\n")
        before = trust.compute_plugin_hash(plugin_dir)
        (plugin_dir / "a.py").rename(plugin_dir / "b.py")
        assert trust.compute_plugin_hash(plugin_dir) != before

    def test_pycache_and_hidden_ignored(self, plugin_dir: Path):
        before = trust.compute_plugin_hash(plugin_dir)
        cache = plugin_dir / "__pycache__"
        cache.mkdir()
        (cache / "junk.cpython-312.pyc").write_bytes(b"\x00\x01")
        (plugin_dir / ".secret").write_text("shh\n")
        assert trust.compute_plugin_hash(plugin_dir) == before


class TestTrustLifecycle:
    def test_untrusted_by_default(self, project_root: Path, plugin_dir: Path):
        assert (
            trust.get_trust_status(project_root, "my_plugin", plugin_dir)
            == trust.UNTRUSTED
        )
        assert not trust.is_plugin_trusted(project_root, "my_plugin", plugin_dir)

    def test_trust_then_trusted(self, project_root: Path, plugin_dir: Path):
        assert trust.trust_plugin(project_root, "my_plugin", plugin_dir)
        assert trust.is_plugin_trusted(project_root, "my_plugin", plugin_dir)

    def test_modification_revokes_trust(self, project_root: Path, plugin_dir: Path):
        trust.trust_plugin(project_root, "my_plugin", plugin_dir)
        (plugin_dir / "register_callbacks.py").write_text("import os  # evil\n")
        assert (
            trust.get_trust_status(project_root, "my_plugin", plugin_dir)
            == trust.CHANGED
        )
        assert not trust.is_plugin_trusted(project_root, "my_plugin", plugin_dir)

    def test_revoke(self, project_root: Path, plugin_dir: Path):
        trust.trust_plugin(project_root, "my_plugin", plugin_dir)
        assert trust.revoke_plugin(project_root, "my_plugin")
        assert (
            trust.get_trust_status(project_root, "my_plugin", plugin_dir)
            == trust.UNTRUSTED
        )

    def test_revoke_missing_returns_false(self, project_root: Path):
        assert not trust.revoke_plugin(project_root, "never_trusted")

    def test_trust_scoped_per_project(
        self, project_root: Path, plugin_dir: Path, tmp_path: Path
    ):
        trust.trust_plugin(project_root, "my_plugin", plugin_dir)
        other_root = tmp_path / "other_project"
        other_root.mkdir()
        assert not trust.is_plugin_trusted(other_root, "my_plugin", plugin_dir)


class TestStoreRobustness:
    def test_malformed_json_fails_closed(self, project_root: Path, plugin_dir: Path):
        trust.TRUST_STORE_FILE.write_text("{not json!!", encoding="utf-8")
        assert (
            trust.get_trust_status(project_root, "my_plugin", plugin_dir)
            == trust.UNTRUSTED
        )

    def test_wrong_shape_fails_closed(self, project_root: Path, plugin_dir: Path):
        trust.TRUST_STORE_FILE.write_text('{"projects": []}', encoding="utf-8")
        assert not trust.is_plugin_trusted(project_root, "my_plugin", plugin_dir)

    def test_trust_survives_reload(self, project_root: Path, plugin_dir: Path):
        trust.trust_plugin(project_root, "my_plugin", plugin_dir)
        # Fresh read from disk (no in-memory caching to go stale)
        assert trust.is_plugin_trusted(project_root, "my_plugin", plugin_dir)
        assert trust.TRUST_STORE_FILE.is_file()
