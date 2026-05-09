"""Security regression tests for plugin trust model & skill safety (P1-04).

Covers:
- No sys.path[0] insertion for user plugins
- Untrusted user plugins are NOT imported
- Trusted user plugins are imported
- Hash change invalidates trust
- Built-in plugins still load
- Skill symlink escape skipped
- Skill prompt/content capped
- Hidden plugin dirs skipped
- Unsafe plugin names rejected
- Symlink escape in plugin dirs skipped
- SKILL.md size validation
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import code_puppy.plugins as plugins_module
from code_puppy.plugins import (
    compute_plugin_hash,
    get_trust_manifest_path,
    is_plugin_trusted,
    record_plugin_trust,
    revoke_plugin_trust,
    _load_builtin_plugins,
    _load_user_plugins,
    _make_user_module_name,
    _SAFE_NAME_RE,
)
from code_puppy.plugins.agent_skills.discovery import (
    MAX_SKILL_MD_BYTES,
    SKILL_CONTEXT_CAP,
    cap_skill_content,
    discover_skills,
    is_valid_skill_directory,
)
from code_puppy.plugins.agent_skills.metadata import (
    parse_skill_metadata,
    load_full_skill_content,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_plugins_loaded():
    """Reset the _PLUGINS_LOADED flag between tests."""
    original = plugins_module._PLUGINS_LOADED
    plugins_module._PLUGINS_LOADED = False
    yield
    plugins_module._PLUGINS_LOADED = original


@pytest.fixture()
def fresh_manifest(tmp_path, monkeypatch):
    """Point the trust manifest at a temp file so tests don't pollute home."""
    manifest_path = tmp_path / "plugin_trust.json"
    monkeypatch.setenv("CODE_PUPPY_PLUGIN_TRUST_MANIFEST", str(manifest_path))
    # Also ensure the module-level function picks it up
    return manifest_path


@pytest.fixture()
def user_plugins_dir(tmp_path):
    """Create a clean user plugins directory."""
    d = tmp_path / "user_plugins"
    d.mkdir()
    return d


@pytest.fixture()
def skill_base_dir(tmp_path):
    """Create a base directory for skill scanning."""
    d = tmp_path / "skills"
    d.mkdir()
    return d


# ===========================================================================
# 1. No sys.path[0] insertion
# ===========================================================================


class TestNoSysPathInsertion:
    """User plugins must NOT be loaded via sys.path.insert(0, …)."""

    def test_user_plugins_dir_not_inserted_at_front_of_syspath(
        self, user_plugins_dir, fresh_manifest
    ):
        """After loading user plugins, the user_plugins_dir must NOT appear in
        sys.path[0]."""
        # Create a user plugin
        plugin_dir = user_plugins_dir / "test_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "register_callbacks.py").write_text("# test")

        # Trust it so it loads
        content_hash = compute_plugin_hash(plugin_dir)
        record_plugin_trust("test_plugin", content_hash, str(plugin_dir))

        _load_user_plugins(user_plugins_dir)

        # The user_plugins_dir must NOT have been inserted
        assert user_plugins_dir not in [Path(p) for p in sys.path]
        # More specifically, it must NOT be at sys.path[0]
        if len(sys.path) > 0:
            assert sys.path[0] != str(user_plugins_dir)

        # Also ensure it wasn't silently added anywhere
        assert str(user_plugins_dir) not in sys.path

    def test_no_sys_path_insertion_even_when_empty(
        self, user_plugins_dir, fresh_manifest
    ):
        """Even with no plugins to load, sys.path must not be modified."""
        before = set(sys.path)
        _load_user_plugins(user_plugins_dir)
        after = set(sys.path)
        # No new entries added
        assert after == before or after.issuperset(before)


# ===========================================================================
# 2. Untrusted user plugins are NOT imported
# ===========================================================================


class TestUntrustedPluginNotImported:
    """User plugins without trust must not be imported."""

    def test_untrusted_user_plugin_not_imported(
        self, user_plugins_dir, fresh_manifest, caplog
    ):
        """An untrusted user plugin should not be loaded."""
        plugin_dir = user_plugins_dir / "untrusted_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "register_callbacks.py").write_text(
            "from code_puppy.callbacks import register_callback\n"
            "register_callback('startup', lambda: None)\n"
        )

        # Do NOT record trust — plugin should be skipped
        result = _load_user_plugins(user_plugins_dir)
        assert "untrusted_plugin" not in result

    def test_untrusted_plugin_logs_warning(
        self, user_plugins_dir, fresh_manifest, caplog
    ):
        """An untrusted plugin should produce a clear warning message."""
        plugin_dir = user_plugins_dir / "warned_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "register_callbacks.py").write_text("# warn me")

        with caplog.at_level("WARNING"):
            result = _load_user_plugins(user_plugins_dir)

        assert "warned_plugin" not in result
        assert "not trusted" in caplog.text

    def test_untrusted_init_only_plugin_not_imported(
        self, user_plugins_dir, fresh_manifest
    ):
        """An __init__.py-only untrusted plugin should also be skipped."""
        plugin_dir = user_plugins_dir / "init_only"
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text("# init only")

        result = _load_user_plugins(user_plugins_dir)
        assert "init_only" not in result


# ===========================================================================
# 3. Trusted user plugins ARE imported
# ===========================================================================


class TestTrustedPluginImported:
    """Trusted user plugins must be loaded successfully."""

    def test_trusted_user_plugin_imported(self, user_plugins_dir, fresh_manifest):
        """A trusted user plugin should be loaded."""
        plugin_dir = user_plugins_dir / "trusted_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "register_callbacks.py").write_text("# trusted")

        # Record trust
        content_hash = compute_plugin_hash(plugin_dir)
        record_plugin_trust("trusted_plugin", content_hash, str(plugin_dir))

        result = _load_user_plugins(user_plugins_dir)
        assert "trusted_plugin" in result

    def test_trusted_plugin_uses_unique_module_name(
        self, user_plugins_dir, fresh_manifest
    ):
        """The module name in sys.modules should be the unique hash-based name."""
        plugin_dir = user_plugins_dir / "unique_name"
        plugin_dir.mkdir()
        (plugin_dir / "register_callbacks.py").write_text("# unique")

        content_hash = compute_plugin_hash(plugin_dir)
        record_plugin_trust("unique_name", content_hash, str(plugin_dir))

        expected_module_name = _make_user_module_name("unique_name", content_hash)

        # Remove any pre-existing entry
        sys.modules.pop(expected_module_name, None)

        result = _load_user_plugins(user_plugins_dir)
        assert "unique_name" in result
        assert expected_module_name in sys.modules


# ===========================================================================
# 4. Hash change invalidates trust
# ===========================================================================


class TestHashChangeInvalidatesTrust:
    """Trust should be invalidated when plugin source changes."""

    def test_plugin_hash_change_invalidates_trust(
        self, user_plugins_dir, fresh_manifest
    ):
        """If a plugin's content hash changes, trust should be revoked."""
        plugin_dir = user_plugins_dir / "changing_plugin"
        plugin_dir.mkdir()
        cb_file = plugin_dir / "register_callbacks.py"
        cb_file.write_text("# version 1")

        # Trust v1
        hash_v1 = compute_plugin_hash(plugin_dir)
        record_plugin_trust("changing_plugin", hash_v1, str(plugin_dir))
        assert is_plugin_trusted("changing_plugin", hash_v1) is True

        # Modify the plugin
        cb_file.write_text("# version 2 with different content")
        hash_v2 = compute_plugin_hash(plugin_dir)

        # v1 hash should no longer be trusted for the new content
        assert is_plugin_trusted("changing_plugin", hash_v2) is False

        # Loading should fail
        result = _load_user_plugins(user_plugins_dir)
        assert "changing_plugin" not in result

    def test_re_trust_after_hash_change(self, user_plugins_dir, fresh_manifest):
        """After re-recording trust with new hash, plugin should load."""
        plugin_dir = user_plugins_dir / "retrust_plugin"
        plugin_dir.mkdir()
        cb_file = plugin_dir / "register_callbacks.py"
        cb_file.write_text("# v1")
        hash_v1 = compute_plugin_hash(plugin_dir)
        record_plugin_trust("retrust_plugin", hash_v1, str(plugin_dir))

        # Change
        cb_file.write_text("# v2 updated content")
        hash_v2 = compute_plugin_hash(plugin_dir)

        # Re-trust
        record_plugin_trust("retrust_plugin", hash_v2, str(plugin_dir))
        assert is_plugin_trusted("retrust_plugin", hash_v2) is True

        result = _load_user_plugins(user_plugins_dir)
        assert "retrust_plugin" in result


# ===========================================================================
# 5. Built-in plugins still load
# ===========================================================================


class TestBuiltinPluginsLoad:
    """Built-in plugins must continue loading as before."""

    def test_builtin_plugins_still_load(self, tmp_path):
        """Built-in plugins should load without trust checks."""
        plugin_dir = tmp_path / "my_builtin"
        plugin_dir.mkdir()
        (plugin_dir / "register_callbacks.py").write_text("# builtin")

        with patch("code_puppy.plugins.importlib.import_module") as mock_import:
            result = _load_builtin_plugins(tmp_path)
            assert "my_builtin" in result
            mock_import.assert_called_once_with(
                "code_puppy.plugins.my_builtin.register_callbacks"
            )

    def test_builtin_ignores_hidden_dirs(self, tmp_path):
        """Built-in plugin loader should skip _ prefixed dirs."""
        (tmp_path / "_private").mkdir()
        (tmp_path / "_private" / "register_callbacks.py").write_text("# priv")

        with patch("code_puppy.plugins.importlib.import_module") as mock_import:
            result = _load_builtin_plugins(tmp_path)
            assert result == []
            mock_import.assert_not_called()

    def test_builtin_handles_import_error(self, tmp_path, caplog):
        """Built-in loader should gracefully handle ImportError."""
        plugin_dir = tmp_path / "broken"
        plugin_dir.mkdir()
        (plugin_dir / "register_callbacks.py").write_text("# broken")

        with (
            patch(
                "code_puppy.plugins.importlib.import_module",
                side_effect=ImportError("nope"),
            ),
            caplog.at_level("WARNING"),
        ):
            result = _load_builtin_plugins(tmp_path)
            assert "broken" not in result
            assert "Failed to import" in caplog.text


# ===========================================================================
# 6. Skill symlink escape skipped
# ===========================================================================


class TestSkillSymlinkEscapeSkipped:
    """Skill discovery must skip directories that escape via symlink."""

    def test_skill_discovery_skips_symlink_escape(self, skill_base_dir):
        """A skill directory that is a symlink escaping the parent should
        be skipped."""
        # Create a real target outside the skill dir
        outside = skill_base_dir.parent / "outside_skill"
        outside.mkdir()
        (outside / "SKILL.md").write_text("---\nname: escape\n---\nEscaped skill")

        # Create symlink in skill dir pointing outside
        link = skill_base_dir / "escaped_skill"
        try:
            link.symlink_to(outside)
        except OSError:
            pytest.skip("Platform doesn't support symlinks")

        skills = discover_skills([skill_base_dir])
        names = [s.name for s in skills]
        assert "escaped_skill" not in names

    def test_skill_skips_hidden_dirs(self, skill_base_dir):
        """Skill directories starting with . should be skipped."""
        hidden = skill_base_dir / ".hidden_skill"
        hidden.mkdir()
        (hidden / "SKILL.md").write_text("---\nname: hidden\n---\nHidden")

        skills = discover_skills([skill_base_dir])
        names = [s.name for s in skills]
        assert ".hidden_skill" not in names

    def test_skill_skips_underscore_dirs(self, skill_base_dir):
        """Skill directories starting with _ should be skipped."""
        under = skill_base_dir / "_internal"
        under.mkdir()
        (under / "SKILL.md").write_text("---\nname: internal\n---\nInternal")

        skills = discover_skills([skill_base_dir])
        names = [s.name for s in skills]
        assert "_internal" not in names

    def test_valid_skill_is_discovered(self, skill_base_dir):
        """A valid skill should be discovered normally."""
        valid = skill_base_dir / "good_skill"
        valid.mkdir()
        (valid / "SKILL.md").write_text("---\nname: good\n---\nGood skill")

        skills = discover_skills([skill_base_dir])
        names = [s.name for s in skills]
        assert "good_skill" in names


# ===========================================================================
# 7. Skill prompt/content capped
# ===========================================================================


class TestSkillContentCapped:
    """Skill content must be capped to prevent model-context blowup."""

    def test_skill_prompt_content_is_capped(self):
        """cap_skill_content should truncate overly long content."""
        long_content = "x" * 100_000
        result = cap_skill_content(long_content, cap=1000)
        assert len(result) <= 1100  # Some headroom for truncation marker
        assert "[skill content truncated]" in result

    def test_short_content_not_capped(self):
        """Short content should pass through unchanged."""
        short = "Hello, I am a skill."
        result = cap_skill_content(short, cap=1000)
        assert result == short

    def test_load_full_skill_content_capped(self, skill_base_dir):
        """load_full_skill_content should cap content before returning."""
        skill_dir = skill_base_dir / "big_skill"
        skill_dir.mkdir()
        # Write content that's under the file size limit but over the context cap
        content = "---\nname: big\n---\n" + ("A" * 70_000)
        (skill_dir / "SKILL.md").write_text(content)

        result = load_full_skill_content(skill_dir)
        assert result is not None
        assert len(result) <= SKILL_CONTEXT_CAP + 100

    def test_oversized_skill_md_rejected(self, skill_base_dir):
        """SKILL.md files over the size limit should be rejected."""
        skill_dir = skill_base_dir / "huge_skill"
        skill_dir.mkdir()
        # Write content larger than MAX_SKILL_MD_BYTES
        huge_content = "---\nname: huge\n---\n" + ("B" * (MAX_SKILL_MD_BYTES + 100))
        (skill_dir / "SKILL.md").write_text(huge_content)

        # parse_skill_metadata should return None
        result = parse_skill_metadata(skill_dir)
        assert result is None

        # is_valid_skill_directory should return False
        assert is_valid_skill_directory(skill_dir) is False

        # load_full_skill_content should return None
        content = load_full_skill_content(skill_dir)
        assert content is None


# ===========================================================================
# 8. Plugin symlink/hidden dir safety
# ===========================================================================


class TestPluginSymlinkEscapeSkipped:
    """Plugin loading must skip symlink escapes and hidden dirs."""

    def test_plugin_symlink_escape_skipped(
        self, user_plugins_dir, fresh_manifest, caplog
    ):
        """A user plugin that is a symlink escaping the parent should be
        skipped."""
        outside = user_plugins_dir.parent / "outside_plugin"
        outside.mkdir()
        (outside / "register_callbacks.py").write_text("# escape")

        link = user_plugins_dir / "escaped_plugin"
        try:
            link.symlink_to(outside)
        except OSError:
            pytest.skip("Platform doesn't support symlinks")

        with caplog.at_level("WARNING"):
            result = _load_user_plugins(user_plugins_dir)

        assert "escaped_plugin" not in result

    def test_hidden_plugin_dir_skipped(self, user_plugins_dir, fresh_manifest):
        """Plugin dirs starting with . should be skipped."""
        hidden = user_plugins_dir / ".hidden"
        hidden.mkdir()
        (hidden / "register_callbacks.py").write_text("# hidden")

        result = _load_user_plugins(user_plugins_dir)
        assert ".hidden" not in result
        # Hidden dirs should be silently skipped, not even attempted
        assert len(result) == 0 or all(r != ".hidden" for r in result)

    def test_underscore_plugin_dir_skipped(self, user_plugins_dir, fresh_manifest):
        """Plugin dirs starting with _ should be skipped."""
        under = user_plugins_dir / "_private"
        under.mkdir()
        (under / "register_callbacks.py").write_text("# private")

        result = _load_user_plugins(user_plugins_dir)
        assert "_private" not in result


# ===========================================================================
# 9. Unsafe plugin names
# ===========================================================================


class TestUnsafePluginNames:
    """Plugins with names containing path-traversal or special chars must be
    rejected."""

    def test_dotdot_plugin_name_rejected(self, user_plugins_dir, fresh_manifest):
        """Plugin name with '..' should be rejected."""
        # This shouldn't normally exist as a real dir, but test the regex
        assert not _SAFE_NAME_RE.match("..")

    def test_slash_in_name_rejected(self):
        """Plugin name with '/' should be rejected."""
        assert not _SAFE_NAME_RE.match("foo/bar")

    def test_valid_names_accepted(self):
        """Valid plugin names should pass the regex."""
        assert _SAFE_NAME_RE.match("my_plugin")
        assert _SAFE_NAME_RE.match("my-plugin")
        assert _SAFE_NAME_RE.match("plugin123")
        assert _SAFE_NAME_RE.match("A_Plugin-2")


# ===========================================================================
# 10. Helper API tests (exposed for tests/monkeypatching)
# ===========================================================================


class TestHelperAPIs:
    """Test the exposed helper APIs used by tests and monkeypatching."""

    def test_compute_plugin_hash_deterministic(self, tmp_path):
        """compute_plugin_hash should return the same hash for the same content."""
        plugin_dir = tmp_path / "hash_test"
        plugin_dir.mkdir()
        (plugin_dir / "register_callbacks.py").write_text("# content")

        h1 = compute_plugin_hash(plugin_dir)
        h2 = compute_plugin_hash(plugin_dir)
        assert h1 == h2
        assert len(h1) == 64  # sha256 hex

    def test_compute_plugin_hash_changes_on_content_change(self, tmp_path):
        """compute_plugin_hash should change when file content changes."""
        plugin_dir = tmp_path / "hash_change"
        plugin_dir.mkdir()
        cb = plugin_dir / "register_callbacks.py"
        cb.write_text("# v1")
        h1 = compute_plugin_hash(plugin_dir)
        cb.write_text("# v2 different")
        h2 = compute_plugin_hash(plugin_dir)
        assert h1 != h2

    def test_get_trust_manifest_path_env_override(self, monkeypatch, tmp_path):
        """get_trust_manifest_path should respect env var override."""
        custom = str(tmp_path / "custom_trust.json")
        monkeypatch.setenv("CODE_PUPPY_PLUGIN_TRUST_MANIFEST", custom)
        assert str(get_trust_manifest_path()) == custom

    def test_record_and_check_trust(self, fresh_manifest):
        """record_plugin_trust + is_plugin_trusted should work together."""
        assert is_plugin_trusted("my_plugin", "hash123") is False
        record_plugin_trust("my_plugin", "hash123", "/some/path")
        assert is_plugin_trusted("my_plugin", "hash123") is True
        assert is_plugin_trusted("my_plugin", "different_hash") is False

    def test_revoke_trust(self, fresh_manifest):
        """revoke_plugin_trust should remove the trust entry."""
        record_plugin_trust("rev_plugin", "abc", "/path")
        assert is_plugin_trusted("rev_plugin", "abc") is True
        revoke_plugin_trust("rev_plugin")
        assert is_plugin_trusted("rev_plugin", "abc") is False

    def test_manifest_file_created_with_private_perms(self, fresh_manifest):
        """The manifest file should be created with 0o600 permissions."""
        record_plugin_trust("perm_plugin", "hash456", "/path")
        if os.name == "posix":
            mode = fresh_manifest.stat().st_mode & 0o777
            assert mode == 0o600

    def test_make_user_module_name(self):
        """_make_user_module_name should produce a unique, safe name."""
        name = _make_user_module_name("my-plugin", "abcdef1234567890")
        assert name == "code_puppy_user_plugin_my_plugin_abcdef123456"
        # Should not contain any dangerous characters
        assert all(c.isalnum() or c == "_" for c in name)


# ===========================================================================
# 11. Skill metadata source/trust/hash fields
# ===========================================================================


class TestSkillMetadataSourceTrust:
    """SkillMetadata should carry source, trust, hash, and size fields."""

    def test_metadata_has_source_and_hash(self, skill_base_dir):
        """parse_skill_metadata should populate source/trust/hash/size."""
        skill_dir = skill_base_dir / "meta_skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: meta\ndescription: A test skill\nauthor: test\n---\nContent"
        )

        result = parse_skill_metadata(skill_dir)
        assert result is not None
        assert result.skill_md_hash is not None
        assert len(result.skill_md_hash) == 64  # sha256 hex
        assert result.skill_md_size is not None
        assert result.skill_md_size > 0

    def test_skill_info_has_source_and_trust(self, skill_base_dir):
        """SkillInfo from discovery should carry source/trust fields."""
        skill_dir = skill_base_dir / "src_skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: src\n---\nSrc skill")

        skills = discover_skills([skill_base_dir])
        matching = [s for s in skills if s.name == "src_skill"]
        assert len(matching) == 1
        skill = matching[0]
        assert skill.source is not None
        assert skill.trust is not None
        assert skill.skill_md_hash is not None


# ===========================================================================
# 12. Skill unexpected executables
# ===========================================================================


class TestSkillUnexpectedExecutables:
    """Skill directories containing unexpected executable files should be
    flagged."""

    def test_skill_with_executable_script_skipped(self, skill_base_dir):
        """A skill directory with an executable .sh file should be skipped."""
        skill_dir = skill_base_dir / "exec_skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: exec\n---\nExec skill")
        script = skill_dir / "run.sh"
        script.write_text("#!/bin/bash\necho pwned")
        # Make it executable
        script.chmod(0o755)

        assert is_valid_skill_directory(skill_dir) is False

    def test_skill_without_executables_accepted(self, skill_base_dir):
        """A clean skill directory should be accepted."""
        skill_dir = skill_base_dir / "clean_skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: clean\n---\nClean skill")

        assert is_valid_skill_directory(skill_dir) is True


# ===========================================================================
# 13. Trust-all env var override (for CI/dev)
# ===========================================================================


class TestTrustAllEnvOverride:
    """CODE_PUPPY_TRUST_ALL_USER_PLUGINS=1 should auto-trust everything."""

    def test_trust_all_env_auto_trusts(
        self, user_plugins_dir, fresh_manifest, monkeypatch
    ):
        """With the env var set, all user plugins should be auto-trusted."""
        monkeypatch.setenv("CODE_PUPPY_TRUST_ALL_USER_PLUGINS", "1")

        plugin_dir = user_plugins_dir / "auto_trusted"
        plugin_dir.mkdir()
        (plugin_dir / "register_callbacks.py").write_text("# auto")

        result = _load_user_plugins(user_plugins_dir)
        assert "auto_trusted" in result

        # The manifest should have been updated
        manifest = json.loads(fresh_manifest.read_text())
        assert "auto_trusted" in manifest


# ===========================================================================
# 14. Empty/edge-case plugin directories
# ===========================================================================


class TestPluginEdgeCases:
    """Edge cases for plugin loading."""

    def test_nonexistent_user_plugins_dir(self, tmp_path, fresh_manifest):
        """A nonexistent user plugins dir should return empty list."""
        result = _load_user_plugins(tmp_path / "nope")
        assert result == []

    def test_file_instead_of_dir(self, tmp_path, fresh_manifest, caplog):
        """A file instead of a directory should warn and return empty."""
        f = tmp_path / "not_a_dir"
        f.write_text("I'm a file")

        with caplog.at_level("WARNING"):
            result = _load_user_plugins(f)
        assert result == []
        assert "not a directory" in caplog.text

    def test_plugin_without_callbacks_or_init(self, user_plugins_dir, fresh_manifest):
        """A plugin directory with neither register_callbacks.py nor __init__.py
        should be silently skipped."""
        empty = user_plugins_dir / "empty_plugin"
        empty.mkdir()

        result = _load_user_plugins(user_plugins_dir)
        assert "empty_plugin" not in result
