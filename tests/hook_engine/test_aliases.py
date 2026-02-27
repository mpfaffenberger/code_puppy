"""
IMMUTABLE TEST FILE — DO NOT MODIFY.

Tests for code_puppy.hook_engine.aliases

These tests define the contract that implementing agents must satisfy.
Editing this file is cheating; all implementation work goes in
code_puppy/hook_engine/aliases.py and code_puppy/hook_engine/matcher.py.
"""

import pytest

from code_puppy.hook_engine.aliases import (
    ALIAS_LOOKUP,
    CLAUDE_CODE_ALIASES,
    CODEX_ALIASES,
    GEMINI_ALIASES,
    PROVIDER_ALIASES,
    SWARM_ALIASES,
    _build_lookup,
    get_aliases,
    resolve_internal_name,
)

# ---------------------------------------------------------------------------
# ALIAS_LOOKUP structure
# ---------------------------------------------------------------------------


class TestAliasLookup:
    def test_lookup_is_a_dict(self):
        assert isinstance(ALIAS_LOOKUP, dict)

    def test_all_keys_are_lowercase(self):
        for key in ALIAS_LOOKUP:
            assert key == key.lower(), f"Key '{key}' is not lowercase"

    def test_all_values_are_frozensets(self):
        for key, val in ALIAS_LOOKUP.items():
            assert isinstance(val, frozenset), f"Value for '{key}' is not a frozenset"

    def test_every_name_is_in_its_own_group(self):
        """Each name in ALIAS_LOOKUP must be a member of its own alias group."""
        for key, group in ALIAS_LOOKUP.items():
            assert any(name.lower() == key for name in group), (
                f"'{key}' not found in its own alias group {group}"
            )

    def test_lookup_is_symmetric(self):
        """If A maps to group G, every member of G must also map to G."""
        for key, group in ALIAS_LOOKUP.items():
            for member in group:
                member_key = member.lower()
                assert member_key in ALIAS_LOOKUP, (
                    f"'{member}' is in group for '{key}' but has no ALIAS_LOOKUP entry"
                )
                assert ALIAS_LOOKUP[member_key] == group, (
                    f"'{member}' resolves to a different group than '{key}'"
                )


# ---------------------------------------------------------------------------
# Claude Code aliases — every entry in the table must resolve correctly
# ---------------------------------------------------------------------------


class TestClaudeCodeAliases:
    @pytest.mark.parametrize(
        "provider_name,internal_name",
        [
            ("Bash", "agent_run_shell_command"),
            ("Glob", "list_files"),
            ("Read", "read_file"),
            ("Grep", "grep"),
            ("Edit", "edit_file"),
            ("Write", "edit_file"),
            ("AskUserQuestion", "ask_user_question"),
            ("Task", "invoke_agent"),
            ("Skill", "activate_skill"),
            ("ToolSearch", "list_or_search_skills"),
        ],
    )
    def test_claude_alias_in_table(self, provider_name, internal_name):
        assert CLAUDE_CODE_ALIASES[provider_name] == internal_name

    @pytest.mark.parametrize(
        "provider_name,internal_name",
        [
            ("Bash", "agent_run_shell_command"),
            ("Glob", "list_files"),
            ("Read", "read_file"),
            ("Grep", "grep"),
            ("Edit", "edit_file"),
            ("Write", "edit_file"),
            ("AskUserQuestion", "ask_user_question"),
            ("Task", "invoke_agent"),
            ("Skill", "activate_skill"),
            ("ToolSearch", "list_or_search_skills"),
        ],
    )
    def test_get_aliases_provider_name_contains_internal(
        self, provider_name, internal_name
    ):
        group = get_aliases(provider_name)
        assert isinstance(group, frozenset)
        # The group must contain the internal name (case-sensitive membership)
        assert internal_name in group, (
            f"get_aliases('{provider_name}') = {group!r}, expected to contain '{internal_name}'"
        )

    @pytest.mark.parametrize(
        "provider_name,internal_name",
        [
            ("Bash", "agent_run_shell_command"),
            ("Glob", "list_files"),
            ("Read", "read_file"),
            ("Grep", "grep"),
            ("Edit", "edit_file"),
            ("Write", "edit_file"),
            ("AskUserQuestion", "ask_user_question"),
            ("Task", "invoke_agent"),
            ("Skill", "activate_skill"),
            ("ToolSearch", "list_or_search_skills"),
        ],
    )
    def test_get_aliases_internal_name_contains_provider(
        self, provider_name, internal_name
    ):
        group = get_aliases(internal_name)
        assert isinstance(group, frozenset)
        assert provider_name in group, (
            f"get_aliases('{internal_name}') = {group!r}, expected to contain '{provider_name}'"
        )

    @pytest.mark.parametrize(
        "provider_name",
        [
            "Bash",
            "Glob",
            "Read",
            "Grep",
            "Edit",
            "Write",
            "AskUserQuestion",
            "Task",
            "Skill",
            "ToolSearch",
        ],
    )
    def test_resolve_internal_name_returns_string(self, provider_name):
        result = resolve_internal_name(provider_name)
        assert isinstance(result, str), (
            f"resolve_internal_name('{provider_name}') returned {result!r}"
        )

    @pytest.mark.parametrize(
        "provider_name,internal_name",
        [
            ("Bash", "agent_run_shell_command"),
            ("Glob", "list_files"),
            ("Read", "read_file"),
            ("Grep", "grep"),
            ("Edit", "edit_file"),
            ("Write", "edit_file"),
            ("AskUserQuestion", "ask_user_question"),
            ("Task", "invoke_agent"),
            ("Skill", "activate_skill"),
            ("ToolSearch", "list_or_search_skills"),
        ],
    )
    def test_resolve_internal_name_correct_value(self, provider_name, internal_name):
        assert resolve_internal_name(provider_name) == internal_name


# ---------------------------------------------------------------------------
# get_aliases behaviour for unknown names
# ---------------------------------------------------------------------------


class TestGetAliasesUnknown:
    def test_unknown_name_returns_frozenset_with_itself(self):
        result = get_aliases("completely_unknown_tool_xyz")
        assert isinstance(result, frozenset)
        assert "completely_unknown_tool_xyz" in result

    def test_unknown_name_group_has_exactly_one_member(self):
        result = get_aliases("no_alias_here_at_all")
        assert len(result) == 1

    def test_resolve_internal_name_unknown_returns_none(self):
        assert resolve_internal_name("totally_unknown_xyz_provider") is None


# ---------------------------------------------------------------------------
# Case-insensitive lookup
# ---------------------------------------------------------------------------


class TestCaseInsensitivity:
    def test_bash_lowercase(self):
        group = get_aliases("bash")
        assert "agent_run_shell_command" in group

    def test_bash_uppercase(self):
        group = get_aliases("BASH")
        assert "agent_run_shell_command" in group

    def test_bash_mixed(self):
        group = get_aliases("BaSh")
        assert "agent_run_shell_command" in group

    def test_internal_name_case_variations(self):
        group = get_aliases("AGENT_RUN_SHELL_COMMAND")
        assert "Bash" in group

    def test_glob_case_insensitive(self):
        group = get_aliases("glob")
        assert "list_files" in group


# ---------------------------------------------------------------------------
# PROVIDER_ALIASES registry structure
# ---------------------------------------------------------------------------


class TestProviderAliasesRegistry:
    def test_registry_is_dict(self):
        assert isinstance(PROVIDER_ALIASES, dict)

    def test_claude_provider_present(self):
        assert "claude" in PROVIDER_ALIASES

    def test_gemini_provider_present(self):
        assert "gemini" in PROVIDER_ALIASES

    def test_codex_provider_present(self):
        assert "codex" in PROVIDER_ALIASES

    def test_swarm_provider_present(self):
        assert "swarm" in PROVIDER_ALIASES

    def test_claude_table_is_correct_dict(self):
        assert PROVIDER_ALIASES["claude"] is CLAUDE_CODE_ALIASES

    def test_gemini_table_is_empty_or_dict(self):
        assert isinstance(GEMINI_ALIASES, dict)

    def test_codex_table_is_empty_or_dict(self):
        assert isinstance(CODEX_ALIASES, dict)

    def test_swarm_table_is_empty_or_dict(self):
        assert isinstance(SWARM_ALIASES, dict)


# ---------------------------------------------------------------------------
# _build_lookup helper
# ---------------------------------------------------------------------------


class TestBuildLookup:
    def test_build_lookup_returns_dict(self):
        result = _build_lookup()
        assert isinstance(result, dict)

    def test_build_lookup_includes_bash(self):
        result = _build_lookup()
        assert "bash" in result

    def test_build_lookup_includes_internal_names(self):
        result = _build_lookup()
        assert "agent_run_shell_command" in result

    def test_build_lookup_bash_group_bidirectional(self):
        result = _build_lookup()
        bash_group = result["bash"]
        internal_group = result["agent_run_shell_command"]
        assert bash_group == internal_group
