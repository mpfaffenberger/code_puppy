"""Tests for the builtin plugin_trust command plugin."""

import json
import os
from unittest.mock import patch

import pytest

from code_puppy.plugins.plugin_trust.register_callbacks import (
    _handle_plugin_command,
    _plugin_command_help,
    _plugin_list,
    _plugin_revoke,
    _plugin_trust,
)


@pytest.fixture()
def fresh_manifest(tmp_path, monkeypatch):
    """Point the trust manifest at a temp file so tests don't pollute home."""
    manifest_path = tmp_path / "plugin_trust.json"
    monkeypatch.setenv("CODE_PUPPY_PLUGIN_TRUST_MANIFEST", str(manifest_path))
    return manifest_path


class TestPluginCommandHelp:
    """Test the custom_command_help hook."""

    def test_returns_expected_entries(self):
        entries = _plugin_command_help()
        assert isinstance(entries, list)
        names = [e[0] for e in entries]
        assert "plugin list" in names
        assert "plugin trust <name>" in names
        assert "plugin revoke <name>" in names
        assert "plugin help" in names


class TestHandlePluginCommandRouting:
    """Test command routing and guard clauses."""

    def test_returns_none_for_non_plugin_command(self):
        assert _handle_plugin_command("/foo bar", "foo") is None

    def test_returns_help_when_no_subcommand(self):
        result = _handle_plugin_command("/plugin", "plugin")
        assert "Plugin trust commands" in result

    def test_help_subcommand(self):
        result = _handle_plugin_command("/plugin help", "plugin")
        assert "Plugin trust commands" in result

    def test_unknown_subcommand(self):
        result = _handle_plugin_command("/plugin unknown", "plugin")
        assert "Unknown" in result

    def test_trust_missing_name(self):
        result = _handle_plugin_command("/plugin trust", "plugin")
        assert "Usage:" in result

    def test_revoke_missing_name(self):
        result = _handle_plugin_command("/plugin revoke", "plugin")
        assert "Usage:" in result


class TestPluginList:
    """Test /plugin list output."""

    def test_no_user_plugins_dir(self, tmp_path, monkeypatch):
        fake_dir = tmp_path / "missing"
        monkeypatch.setattr(
            "code_puppy.plugins.plugin_trust.register_callbacks.get_user_plugins_dir",
            lambda: fake_dir,
        )
        result = _plugin_list()
        assert "No user plugins directory" in result

    def test_empty_plugins_dir(self, tmp_path, monkeypatch):
        fake_dir = tmp_path / "plugins"
        fake_dir.mkdir()
        monkeypatch.setattr(
            "code_puppy.plugins.plugin_trust.register_callbacks.get_user_plugins_dir",
            lambda: fake_dir,
        )
        result = _plugin_list()
        assert "No user plugins found" in result

    def test_list_includes_trusted_and_untrusted(
        self, tmp_path, monkeypatch, fresh_manifest
    ):
        fake_dir = tmp_path / "plugins"
        fake_dir.mkdir()

        trusted = fake_dir / "trusted_plugin"
        trusted.mkdir()
        (trusted / "register_callbacks.py").write_text("# trusted")

        untrusted = fake_dir / "untrusted_plugin"
        untrusted.mkdir()
        (untrusted / "register_callbacks.py").write_text("# untrusted")

        # Pre-trust one plugin
        from code_puppy.plugins import compute_plugin_hash, record_plugin_trust

        h = compute_plugin_hash(trusted)
        record_plugin_trust("trusted_plugin", h, str(trusted))

        monkeypatch.setattr(
            "code_puppy.plugins.plugin_trust.register_callbacks.get_user_plugins_dir",
            lambda: fake_dir,
        )
        result = _plugin_list()
        assert "trusted_plugin" in result
        assert "untrusted_plugin" in result
        assert "trusted" in result
        assert "untrusted" in result

    def test_list_skips_hidden_and_underscore_dirs(self, tmp_path, monkeypatch):
        fake_dir = tmp_path / "plugins"
        fake_dir.mkdir()

        hidden = fake_dir / ".hidden"
        hidden.mkdir()
        (hidden / "register_callbacks.py").write_text("# hidden")

        under = fake_dir / "_private"
        under.mkdir()
        (under / "register_callbacks.py").write_text("# private")

        valid = fake_dir / "valid"
        valid.mkdir()
        (valid / "register_callbacks.py").write_text("# valid")

        monkeypatch.setattr(
            "code_puppy.plugins.plugin_trust.register_callbacks.get_user_plugins_dir",
            lambda: fake_dir,
        )
        result = _plugin_list()
        assert ".hidden" not in result
        assert "_private" not in result
        assert "valid" in result

    def test_list_skips_dirs_without_entrypoint(self, tmp_path, monkeypatch):
        fake_dir = tmp_path / "plugins"
        fake_dir.mkdir()

        empty = fake_dir / "empty"
        empty.mkdir()
        (empty / "README.md").write_text("# no callbacks")

        monkeypatch.setattr(
            "code_puppy.plugins.plugin_trust.register_callbacks.get_user_plugins_dir",
            lambda: fake_dir,
        )
        result = _plugin_list()
        assert "empty" not in result
        assert "No user plugins found" in result


class TestPluginTrust:
    """Test /plugin trust <name>."""

    def test_trust_nonexistent_plugin(self, tmp_path, monkeypatch):
        fake_dir = tmp_path / "plugins"
        fake_dir.mkdir()
        monkeypatch.setattr(
            "code_puppy.plugins.plugin_trust.register_callbacks.get_user_plugins_dir",
            lambda: fake_dir,
        )
        result = _plugin_trust("missing")
        assert "not found" in result

    def test_trust_plugin_without_entrypoint(self, tmp_path, monkeypatch):
        fake_dir = tmp_path / "plugins"
        fake_dir.mkdir()
        bad = fake_dir / "bad"
        bad.mkdir()
        (bad / "README.md").write_text("# no callbacks")
        monkeypatch.setattr(
            "code_puppy.plugins.plugin_trust.register_callbacks.get_user_plugins_dir",
            lambda: fake_dir,
        )
        result = _plugin_trust("bad")
        assert "no register_callbacks.py" in result

    def test_trust_valid_plugin(self, tmp_path, monkeypatch, fresh_manifest):
        fake_dir = tmp_path / "plugins"
        fake_dir.mkdir()
        plugin_dir = fake_dir / "good"
        plugin_dir.mkdir()
        (plugin_dir / "register_callbacks.py").write_text("# good")

        monkeypatch.setattr(
            "code_puppy.plugins.plugin_trust.register_callbacks.get_user_plugins_dir",
            lambda: fake_dir,
        )

        result = _plugin_trust("good")
        assert "Trust recorded" in result
        assert "good" in result

        # Verify manifest was written
        manifest = json.loads(fresh_manifest.read_text())
        assert "good" in manifest
        assert manifest["good"]["path"] == str(plugin_dir)

    def test_trust_warns_when_plugins_already_loaded(
        self, tmp_path, monkeypatch, fresh_manifest
    ):
        fake_dir = tmp_path / "plugins"
        fake_dir.mkdir()
        plugin_dir = fake_dir / "late"
        plugin_dir.mkdir()
        (plugin_dir / "register_callbacks.py").write_text("# late")

        monkeypatch.setattr(
            "code_puppy.plugins.plugin_trust.register_callbacks.get_user_plugins_dir",
            lambda: fake_dir,
        )

        import code_puppy.plugins.plugin_trust.register_callbacks as trust_mod

        orig = trust_mod._PLUGINS_LOADED
        try:
            trust_mod._PLUGINS_LOADED = True
            result = _plugin_trust("late")
            assert "Restart" in result
        finally:
            trust_mod._PLUGINS_LOADED = orig


class TestPluginRevoke:
    """Test /plugin revoke <name>."""

    def test_revoke_removes_trust(self, tmp_path, fresh_manifest, monkeypatch):
        fake_dir = tmp_path / "plugins"
        fake_dir.mkdir()
        plugin_dir = fake_dir / "gone"
        plugin_dir.mkdir()
        (plugin_dir / "register_callbacks.py").write_text("# gone")

        from code_puppy.plugins import (
            compute_plugin_hash,
            record_plugin_trust,
            is_plugin_trusted,
        )

        h = compute_plugin_hash(plugin_dir)
        record_plugin_trust("gone", h, str(plugin_dir))
        assert is_plugin_trusted("gone", h) is True

        monkeypatch.setattr(
            "code_puppy.plugins.plugin_trust.register_callbacks.get_user_plugins_dir",
            lambda: fake_dir,
        )

        result = _plugin_revoke("gone")
        assert "Trust revoked" in result
        assert is_plugin_trusted("gone", h) is False


class TestManifestPermissions:
    """Verify that trust manifest writes use atomic private helpers."""

    def test_manifest_file_is_0o600(self, fresh_manifest):
        from code_puppy.plugins import record_plugin_trust

        record_plugin_trust("perm_check", "abc123", "/some/path")
        if os.name == "posix":
            mode = fresh_manifest.stat().st_mode & 0o777
            assert mode == 0o600

    def test_user_plugins_dir_is_0o700(self, tmp_path, monkeypatch):
        import code_puppy.plugins as plugins_module
        from code_puppy.plugins import ensure_user_plugins_dir

        test_dir = tmp_path / ".code_puppy" / "plugins"
        with patch.object(plugins_module, "USER_PLUGINS_DIR", test_dir):
            ensure_user_plugins_dir()
            assert test_dir.exists()
            if os.name == "posix":
                mode = test_dir.stat().st_mode & 0o777
                assert mode == 0o700
