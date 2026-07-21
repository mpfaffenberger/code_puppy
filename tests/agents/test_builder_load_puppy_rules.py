"""Tests for load_puppy_rules() in code_puppy.agents._builder.

Covers the .code_puppy/ directory feature (PUP-34):
- Loading from .code_puppy/AGENTS.md (preferred)
- Precedence: .code_puppy/ over project root
- Backwards compatibility with root AGENTS.md
- Combining global + project rules
- Edge cases (dir is file, empty dir, etc.)

Also covers:
- @file reference expansion (one level deep)
- CLAUDE.md fallback when no AGENTS.md exists
"""

from unittest.mock import patch

import pytest


class TestLoadPuppyRulesCodePuppyDir:
    """Tests for .code_puppy/ directory support in load_puppy_rules()."""

    @pytest.fixture
    def temp_project(self, tmp_path, monkeypatch):
        """Set up a temporary project directory and cd into it."""
        monkeypatch.chdir(tmp_path)
        return tmp_path

    @pytest.fixture
    def mock_config_dir(self, tmp_path):
        """Create a mock global config directory."""
        config_dir = tmp_path / "global_config"
        config_dir.mkdir()
        return config_dir

    def test_load_from_code_puppy_dir(self, temp_project, mock_config_dir):
        """Load AGENTS.md from .code_puppy/ directory."""
        from code_puppy.agents._builder import load_puppy_rules

        # Create .code_puppy/AGENTS.md
        code_puppy_dir = temp_project / ".code_puppy"
        code_puppy_dir.mkdir()
        agents_file = code_puppy_dir / "AGENTS.md"
        agents_file.write_text("# Rules from .code_puppy dir")

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        assert result == "# Rules from .code_puppy dir"

    def test_precedence_code_puppy_over_root(self, temp_project, mock_config_dir):
        """Files in .code_puppy/ take precedence over project root."""
        from code_puppy.agents._builder import load_puppy_rules

        # Create both locations
        code_puppy_dir = temp_project / ".code_puppy"
        code_puppy_dir.mkdir()
        (code_puppy_dir / "AGENTS.md").write_text("# Preferred rules")
        (temp_project / "AGENTS.md").write_text("# Root rules")

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        # Should use .code_puppy/ version, NOT root
        assert result == "# Preferred rules"
        assert "Root rules" not in (result or "")

    def test_fallback_to_root(self, temp_project, mock_config_dir):
        """Fall back to root AGENTS.md if .code_puppy/ doesn't exist."""
        from code_puppy.agents._builder import load_puppy_rules

        # Only create root AGENTS.md
        (temp_project / "AGENTS.md").write_text("# Root rules")

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        assert result == "# Root rules"

    def test_global_and_code_puppy_combined(self, temp_project, mock_config_dir):
        """Global rules and .code_puppy rules are combined."""
        from code_puppy.agents._builder import load_puppy_rules

        # Create global rules
        (mock_config_dir / "AGENTS.md").write_text("# Global rules")

        # Create .code_puppy rules
        code_puppy_dir = temp_project / ".code_puppy"
        code_puppy_dir.mkdir()
        (code_puppy_dir / "AGENTS.md").write_text("# Project rules")

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        # Both should be present, global first
        assert "# Global rules" in result
        assert "# Project rules" in result
        assert result.index("# Global rules") < result.index("# Project rules")

    def test_global_and_root_combined(self, temp_project, mock_config_dir):
        """Global rules + root rules work together."""
        from code_puppy.agents._builder import load_puppy_rules

        # Create global rules
        (mock_config_dir / "AGENTS.md").write_text("# Global rules")

        # Create root rules
        (temp_project / "AGENTS.md").write_text("# Root rules")

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        # Both should be combined
        assert "# Global rules" in result
        assert "# Root rules" in result

    def test_code_puppy_is_file_not_dir(self, temp_project, mock_config_dir):
        """If .code_puppy is a file (not directory), fall back to root."""
        from code_puppy.agents._builder import load_puppy_rules

        # Create .code_puppy as a FILE, not directory
        (temp_project / ".code_puppy").write_text("I'm a file, not a dir!")

        # Create root AGENTS.md as fallback
        (temp_project / "AGENTS.md").write_text("# Root fallback")

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        # Should use root fallback
        assert result == "# Root fallback"

    def test_code_puppy_dir_exists_but_empty(self, temp_project, mock_config_dir):
        """Empty .code_puppy/ dir falls back to root AGENTS.md."""
        from code_puppy.agents._builder import load_puppy_rules

        # Create empty .code_puppy directory
        (temp_project / ".code_puppy").mkdir()

        # Create root AGENTS.md as fallback
        (temp_project / "AGENTS.md").write_text("# Root fallback")

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        # Should use root fallback
        assert result == "# Root fallback"

    def test_no_agents_files_anywhere(self, temp_project, mock_config_dir):
        """Returns None if no AGENTS.md files exist anywhere."""
        from code_puppy.agents._builder import load_puppy_rules

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        assert result is None

    def test_agent_md_variant_in_code_puppy_dir(self, temp_project, mock_config_dir):
        """Also supports AGENT.md (singular) in .code_puppy/."""
        from code_puppy.agents._builder import load_puppy_rules

        code_puppy_dir = temp_project / ".code_puppy"
        code_puppy_dir.mkdir()
        # Use singular AGENT.md instead of AGENTS.md
        (code_puppy_dir / "AGENT.md").write_text("# Singular agent rules")

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        assert result == "# Singular agent rules"

    def test_agents_md_takes_precedence_over_agent_md(
        self, temp_project, mock_config_dir
    ):
        """AGENTS.md (plural) takes precedence over AGENT.md (singular)."""
        from code_puppy.agents._builder import load_puppy_rules

        code_puppy_dir = temp_project / ".code_puppy"
        code_puppy_dir.mkdir()
        (code_puppy_dir / "AGENTS.md").write_text("# Plural wins")
        (code_puppy_dir / "AGENT.md").write_text("# Singular loses")

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        assert result == "# Plural wins"

    def test_only_global_rules(self, temp_project, mock_config_dir):
        """Only global rules loaded when no project rules exist."""
        from code_puppy.agents._builder import load_puppy_rules

        # Create only global rules
        (mock_config_dir / "AGENTS.md").write_text("# Global only")

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        assert result == "# Global only"


class TestTruncation:
    """Tests for the AGENTS.md character-cap behaviour.

    Each AGENTS.md file (global and project) is independently capped at
    ``AGENTS_MD_MAX_CHARS``. Overflowing files keep the first N chars
    verbatim and have a labelled warning notice appended; under-limit
    files are returned untouched.
    """

    @pytest.fixture
    def temp_project(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        return tmp_path

    @pytest.fixture
    def mock_config_dir(self, tmp_path):
        config_dir = tmp_path / "global_config"
        config_dir.mkdir()
        return config_dir

    # --- direct unit tests on the pure helper -----------------------------

    def test_helper_under_limit_returns_verbatim(self):
        from code_puppy.agents._builder import (
            AGENTS_MD_MAX_CHARS,
            _truncate_agents_md,
        )

        content = "x" * (AGENTS_MD_MAX_CHARS - 1)
        assert (
            _truncate_agents_md(content, source="test", max_chars=AGENTS_MD_MAX_CHARS)
            == content
        )

    def test_helper_at_limit_returns_verbatim(self):
        from code_puppy.agents._builder import (
            AGENTS_MD_MAX_CHARS,
            _truncate_agents_md,
        )

        content = "x" * AGENTS_MD_MAX_CHARS
        result = _truncate_agents_md(
            content, source="test", max_chars=AGENTS_MD_MAX_CHARS
        )
        assert result == content
        assert "truncated" not in result

    def test_helper_over_limit_truncates_with_warning(self):
        from code_puppy.agents._builder import (
            AGENTS_MD_MAX_CHARS,
            _truncate_agents_md,
        )

        original_len = AGENTS_MD_MAX_CHARS + 5_000
        content = "y" * original_len
        result = _truncate_agents_md(
            content, source="global ~/x/AGENTS.md", max_chars=AGENTS_MD_MAX_CHARS
        )

        # First N chars verbatim from the original.
        assert result[:AGENTS_MD_MAX_CHARS] == content[:AGENTS_MD_MAX_CHARS]
        # Notice present and addressed to the agent.
        assert "--- AGENTS.md truncated ---" in result
        assert "--- end truncation notice ---" in result
        # Source label propagated so the agent can name the offending file.
        assert "global ~/x/AGENTS.md" in result
        # Counts present (thousands-separated, since that's what the notice uses).
        assert f"{original_len:,}" in result
        assert f"{original_len - AGENTS_MD_MAX_CHARS:,}" in result
        # Hints the user at the config knob.
        assert "agents_md_max_chars" in result

    def test_helper_respects_caller_max_chars(self):
        """Cap is whatever the caller passes — not a hardcoded global."""
        from code_puppy.agents._builder import _truncate_agents_md

        content = "z" * 5_000
        # Caller-provided cap below the default — should truncate.
        result = _truncate_agents_md(content, source="test", max_chars=1_000)
        assert result[:1_000] == content[:1_000]
        assert "--- AGENTS.md truncated ---" in result
        assert "4,000 chars dropped" in result

    # --- end-to-end through load_puppy_rules ------------------------------

    def test_under_limit_unchanged(self, temp_project, mock_config_dir):
        from code_puppy.agents._builder import load_puppy_rules

        (temp_project / "AGENTS.md").write_text("a" * 5_000)

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        assert result == "a" * 5_000
        assert "truncated" not in result

    def test_exactly_at_limit_unchanged(self, temp_project, mock_config_dir):
        from code_puppy.agents._builder import (
            AGENTS_MD_MAX_CHARS,
            load_puppy_rules,
        )

        (temp_project / "AGENTS.md").write_text("a" * AGENTS_MD_MAX_CHARS)

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        assert result == "a" * AGENTS_MD_MAX_CHARS
        assert "truncated" not in result

    def test_over_limit_truncated_with_warning(self, temp_project, mock_config_dir):
        from code_puppy.agents._builder import (
            AGENTS_MD_MAX_CHARS,
            load_puppy_rules,
        )

        original_len = 15_000
        content = "b" * original_len
        (temp_project / "AGENTS.md").write_text(content)

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        assert result is not None
        # First N chars are verbatim from the original.
        assert result[:AGENTS_MD_MAX_CHARS] == content[:AGENTS_MD_MAX_CHARS]
        # Notice block follows.
        assert "--- AGENTS.md truncated ---" in result
        # Numbers reported correctly.
        assert f"{original_len:,}" in result
        assert f"{original_len - AGENTS_MD_MAX_CHARS:,}" in result
        # Source label includes the file path so the agent can name it.
        assert "AGENTS.md" in result
        assert "project" in result

    def test_truncation_per_file_global_only(self, temp_project, mock_config_dir):
        from code_puppy.agents._builder import (
            AGENTS_MD_MAX_CHARS,
            load_puppy_rules,
        )

        # Fat global, small project. Per-file truncation must keep the
        # project file fully intact.
        (mock_config_dir / "AGENTS.md").write_text("g" * 15_000)
        (temp_project / "AGENTS.md").write_text("# Project rules (short)")

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        assert result is not None
        # Project file landed untouched.
        assert "# Project rules (short)" in result
        # Global file got truncated with a labelled notice.
        assert "--- AGENTS.md truncated ---" in result
        assert "global" in result
        # The 15k of 'g' was capped at AGENTS_MD_MAX_CHARS: a contiguous
        # block of exactly N g's survives, but a block of N+1 does not.
        assert "g" * AGENTS_MD_MAX_CHARS in result
        assert "g" * (AGENTS_MD_MAX_CHARS + 1) not in result

    def test_truncation_per_file_project_only(self, temp_project, mock_config_dir):
        from code_puppy.agents._builder import (
            AGENTS_MD_MAX_CHARS,
            load_puppy_rules,
        )

        # Small global, fat project. Global must land untouched.
        (mock_config_dir / "AGENTS.md").write_text("# Global rules (short)")
        (temp_project / "AGENTS.md").write_text("p" * 15_000)

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        assert result is not None
        assert "# Global rules (short)" in result
        assert "--- AGENTS.md truncated ---" in result
        assert "project" in result
        assert "p" * AGENTS_MD_MAX_CHARS in result
        assert "p" * (AGENTS_MD_MAX_CHARS + 1) not in result

    def test_warning_identifies_source_when_both_truncated(
        self, temp_project, mock_config_dir
    ):
        """When both files overflow, the agent must be able to tell them apart."""
        from code_puppy.agents._builder import load_puppy_rules

        (mock_config_dir / "AGENTS.md").write_text("g" * 15_000)
        (temp_project / "AGENTS.md").write_text("p" * 15_000)

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        assert result is not None
        # Two distinct truncation notices.
        assert result.count("--- AGENTS.md truncated ---") == 2
        # Both source classes are named so the agent can disambiguate.
        assert "global" in result
        assert "project" in result

    def test_truncation_via_preferred_code_puppy_dir(
        self, temp_project, mock_config_dir
    ):
        """Closes branch-coverage parity: truncation also fires from .code_puppy/."""
        from code_puppy.agents._builder import (
            AGENTS_MD_MAX_CHARS,
            load_puppy_rules,
        )

        code_puppy_dir = temp_project / ".code_puppy"
        code_puppy_dir.mkdir()
        (code_puppy_dir / "AGENTS.md").write_text("q" * 15_000)

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        assert result is not None
        assert "--- AGENTS.md truncated ---" in result
        assert ".code_puppy" in result  # source label names the preferred path
        assert "q" * AGENTS_MD_MAX_CHARS in result
        assert "q" * (AGENTS_MD_MAX_CHARS + 1) not in result

    def test_friendly_path_collapses_home(self, tmp_path, monkeypatch):
        """Paths under $HOME render as ~/...; paths outside fall back to absolute."""
        from pathlib import Path

        from code_puppy.agents._builder import _friendly_path

        fake_home = tmp_path / "home" / "user"
        fake_home.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        under_home = fake_home / ".code_puppy" / "AGENTS.md"
        assert _friendly_path(under_home) == "~/.code_puppy/AGENTS.md"

        outside_home = tmp_path / "elsewhere" / "AGENTS.md"
        assert _friendly_path(outside_home) == str(outside_home)

    # --- /set agents_md_max_chars override ----------------------------------

    def test_override_raises_cap_and_keeps_file_intact(
        self, temp_project, mock_config_dir
    ):
        """`/set agents_md_max_chars=20000` lets a 15k file load verbatim."""
        from code_puppy.agents._builder import load_puppy_rules

        (temp_project / "AGENTS.md").write_text("r" * 15_000)

        with (
            patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)),
            patch(
                "code_puppy.agents._builder.get_agents_md_max_chars",
                return_value=20_000,
            ),
        ):
            result = load_puppy_rules()

        assert result == "r" * 15_000
        assert "truncated" not in result

    def test_override_lowers_cap_and_truncates_under_default(
        self, temp_project, mock_config_dir
    ):
        """`/set agents_md_max_chars=2000` truncates an 8k file the default would have allowed."""
        from code_puppy.agents._builder import load_puppy_rules

        (temp_project / "AGENTS.md").write_text("s" * 8_000)

        with (
            patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)),
            patch(
                "code_puppy.agents._builder.get_agents_md_max_chars",
                return_value=2_000,
            ),
        ):
            result = load_puppy_rules()

        assert result is not None
        assert result[:2_000] == "s" * 2_000
        assert "--- AGENTS.md truncated ---" in result
        assert "6,000 chars dropped" in result
        # The new cap is reflected in the user-facing notice.
        assert "2,000" in result


class TestGetAgentsMdMaxChars:
    """Tests for the config getter that backs ``/set agents_md_max_chars``."""

    def test_unset_returns_default(self):
        from code_puppy.config import (
            AGENTS_MD_MAX_CHARS_DEFAULT,
            get_agents_md_max_chars,
        )

        with patch("code_puppy.config.get_value", return_value=None):
            assert get_agents_md_max_chars() == AGENTS_MD_MAX_CHARS_DEFAULT

    def test_valid_int_string_is_honoured(self):
        from code_puppy.config import get_agents_md_max_chars

        with patch("code_puppy.config.get_value", return_value="25000"):
            assert get_agents_md_max_chars() == 25_000

    def test_garbage_falls_back_to_default(self):
        from code_puppy.config import (
            AGENTS_MD_MAX_CHARS_DEFAULT,
            get_agents_md_max_chars,
        )

        with patch("code_puppy.config.get_value", return_value="banana"):
            assert get_agents_md_max_chars() == AGENTS_MD_MAX_CHARS_DEFAULT

    def test_zero_or_negative_falls_back_to_default(self):
        from code_puppy.config import (
            AGENTS_MD_MAX_CHARS_DEFAULT,
            get_agents_md_max_chars,
        )

        for bogus in ("0", "-1", "-9999"):
            with patch("code_puppy.config.get_value", return_value=bogus):
                assert get_agents_md_max_chars() == AGENTS_MD_MAX_CHARS_DEFAULT

    def test_very_large_values_pass_through_uncapped(self):
        """No upper clamp: 1M-context models can opt into huge AGENTS.md files."""
        from code_puppy.config import get_agents_md_max_chars

        with patch("code_puppy.config.get_value", return_value="500000"):
            assert get_agents_md_max_chars() == 500_000

        with patch("code_puppy.config.get_value", return_value="99999999"):
            assert get_agents_md_max_chars() == 99_999_999

    def test_key_is_in_config_keys_for_set_autocomplete(self):
        """The key must appear in get_config_keys() so /set tab-completes it."""
        from code_puppy.config import get_config_keys

        assert "agents_md_max_chars" in get_config_keys()


class TestExpandAtReferences:
    """Tests for _expand_at_references() — @file inclusion."""

    def test_expands_at_reference(self, tmp_path):
        """@filename on its own line is replaced with file contents."""
        from code_puppy.agents._builder import _expand_at_references

        included = tmp_path / "rules.md"
        included.write_text("# Included content")

        result = _expand_at_references("@rules.md", base_dir=tmp_path)
        assert result == "# Included content"

    def test_expands_at_reference_in_context(self, tmp_path):
        """@ref surrounded by other text replaces only the @ref line."""
        from code_puppy.agents._builder import _expand_at_references

        included = tmp_path / "extra.md"
        included.write_text("extra stuff")

        text = "before\n@extra.md\nafter"
        result = _expand_at_references(text, base_dir=tmp_path)
        assert result == "before\nextra stuff\nafter"

    def test_missing_at_reference_left_intact(self, tmp_path):
        """Unknown @ref is left as-is so the agent can see it failed."""
        from code_puppy.agents._builder import _expand_at_references

        result = _expand_at_references("@nonexistent.md", base_dir=tmp_path)
        assert result == "@nonexistent.md"

    def test_only_one_level_deep(self, tmp_path):
        """@refs inside included files are NOT expanded (one level only)."""
        from code_puppy.agents._builder import _expand_at_references

        nested = tmp_path / "nested.md"
        nested.write_text("# nested")
        included = tmp_path / "included.md"
        included.write_text("@nested.md")

        result = _expand_at_references("@included.md", base_dir=tmp_path)
        # Should contain the literal text of included.md, NOT expand @nested.md
        assert result == "@nested.md"

    def test_at_ref_with_subdirectory_path(self, tmp_path):
        """@subdir/file.md resolves relative to base_dir."""
        from code_puppy.agents._builder import _expand_at_references

        subdir = tmp_path / "rules"
        subdir.mkdir()
        (subdir / "dev.md").write_text("# dev rules")

        result = _expand_at_references("@rules/dev.md", base_dir=tmp_path)
        assert result == "# dev rules"

    def test_at_ref_not_expanded_mid_line(self, tmp_path):
        """@ref mid-line (not at line start) is NOT expanded."""
        from code_puppy.agents._builder import _expand_at_references

        included = tmp_path / "rules.md"
        included.write_text("should not appear")

        result = _expand_at_references("see @rules.md for details", base_dir=tmp_path)
        assert result == "see @rules.md for details"

    def test_multiple_at_references(self, tmp_path):
        """Multiple @refs in the same file are all expanded."""
        from code_puppy.agents._builder import _expand_at_references

        (tmp_path / "a.md").write_text("# A")
        (tmp_path / "b.md").write_text("# B")

        result = _expand_at_references("@a.md\n@b.md", base_dir=tmp_path)
        assert result == "# A\n# B"


class TestResolveAtRef:
    """Tests for _resolve_at_ref() path containment."""

    def test_absolute_path_rejected(self, tmp_path):
        """Absolute @refs are rejected outright."""
        from code_puppy.agents._builder import _resolve_at_ref

        result = _resolve_at_ref(tmp_path, "/etc/hostname")
        assert result is None

    def test_parent_traversal_rejected(self, tmp_path):
        """@../outside refs that escape base_dir are rejected."""
        from code_puppy.agents._builder import _resolve_at_ref

        # Create a file outside tmp_path to ensure the path would be valid
        # if traversal were allowed
        result = _resolve_at_ref(tmp_path, "../../.env")
        assert result is None

    def test_simple_traversal_rejected(self, tmp_path):
        """@../file that resolves outside base_dir is rejected."""
        from code_puppy.agents._builder import _resolve_at_ref

        result = _resolve_at_ref(tmp_path, "../secret.txt")
        assert result is None

    def test_symlink_escape_rejected(self, tmp_path):
        """Symlink pointing outside base_dir is rejected."""
        from code_puppy.agents._builder import _resolve_at_ref

        outside = tmp_path.parent / "outside.md"
        outside.write_text("secret")
        link = tmp_path / "link.md"
        link.symlink_to(outside)

        result = _resolve_at_ref(tmp_path, "link.md")
        assert result is None

    def test_valid_path_accepted(self, tmp_path):
        """Normal relative path within base_dir resolves correctly."""
        from code_puppy.agents._builder import _resolve_at_ref

        f = tmp_path / "rules.md"
        f.write_text("content")

        result = _resolve_at_ref(tmp_path, "rules.md")
        assert result == f.resolve()

    def test_absolute_path_left_intact_in_expansion(self, tmp_path):
        """Absolute @ref in expansion is left as-is in output."""
        from code_puppy.agents._builder import _expand_at_references

        result = _expand_at_references("@/etc/hostname", base_dir=tmp_path)
        assert result == "@/etc/hostname"

    def test_traversal_left_intact_in_expansion(self, tmp_path):
        """Traversal @ref in expansion is left as-is in output."""
        from code_puppy.agents._builder import _expand_at_references

        result = _expand_at_references("@../../.env", base_dir=tmp_path)
        assert result == "@../../.env"


class TestClaudeMdFallback:
    """Tests for CLAUDE.md fallback when no AGENTS.md exists."""

    @pytest.fixture
    def temp_project(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        return tmp_path

    @pytest.fixture
    def mock_config_dir(self, tmp_path):
        config_dir = tmp_path / "global_config"
        config_dir.mkdir()
        return config_dir

    def test_falls_back_to_claude_md(self, temp_project, mock_config_dir):
        """CLAUDE.md is loaded when no AGENTS.md exists anywhere."""
        from code_puppy.agents._builder import load_puppy_rules

        (temp_project / "CLAUDE.md").write_text("# Claude fallback")

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        assert result == "# Claude fallback"

    def test_agents_md_takes_priority_over_claude_md(
        self, temp_project, mock_config_dir
    ):
        """AGENTS.md wins over CLAUDE.md when both exist."""
        from code_puppy.agents._builder import load_puppy_rules

        (temp_project / "AGENTS.md").write_text("# Agents wins")
        (temp_project / "CLAUDE.md").write_text("# Claude loses")

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        assert result == "# Agents wins"
        assert "Claude loses" not in (result or "")

    def test_claude_md_not_loaded_when_code_puppy_agents_md_exists(
        self, temp_project, mock_config_dir
    ):
        """.code_puppy/AGENTS.md prevents CLAUDE.md fallback."""
        from code_puppy.agents._builder import load_puppy_rules

        code_puppy_dir = temp_project / ".code_puppy"
        code_puppy_dir.mkdir()
        (code_puppy_dir / "AGENTS.md").write_text("# Preferred rules")
        (temp_project / "CLAUDE.md").write_text("# Should not load")

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        assert result == "# Preferred rules"
        assert "Should not load" not in (result or "")

    def test_claude_md_with_at_references(self, temp_project, mock_config_dir):
        """@refs in CLAUDE.md are expanded."""
        from code_puppy.agents._builder import load_puppy_rules

        rules_dir = temp_project / ".claude" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "developer.md").write_text("# Dev rules")
        (temp_project / "CLAUDE.md").write_text("@.claude/rules/developer.md")

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        assert result == "# Dev rules"

    def test_no_rules_anywhere_returns_none(self, temp_project, mock_config_dir):
        """Returns None when neither AGENTS.md nor CLAUDE.md exist."""
        from code_puppy.agents._builder import load_puppy_rules

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        assert result is None
