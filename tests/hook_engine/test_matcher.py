"""Tests for hook engine pattern matcher."""

import pytest

from code_puppy.hook_engine.matcher import _extract_file_path, matches

# One row per branch: (matcher, tool_name, tool_args, expected) — folded from one
# test per case into a matrix: same branches, less boilerplate.
_MATCH_CASES = [
    # wildcard matches all
    ("*", "Edit", {}, True),
    ("*", "Bash", {"command": "ls"}, True),
    # exact tool name
    ("Edit", "Edit", {}, True),
    ("Edit", "Bash", {}, False),
    # case insensitivity
    ("edit", "Edit", {}, True),
    ("BASH", "bash", {}, True),
    # file extension matching
    (".py", "Edit", {"file_path": "test.py"}, True),
    (".py", "Edit", {"file_path": "test.js"}, False),
    (".ts", "Edit", {"file_path": "app.ts"}, True),
    # && condition
    ("Edit && .py", "Edit", {"file_path": "test.py"}, True),
    ("Edit && .py", "Edit", {"file_path": "test.js"}, False),
    ("Edit && .py", "Bash", {"file_path": "test.py"}, False),
    # || condition
    ("Edit || Write", "Edit", {}, True),
    ("Edit || Write", "Write", {}, True),
    ("Edit || Write", "Bash", {}, False),
    # pipe regex as OR
    ("Bash|agent_run_shell_command", "Bash", {}, True),
    ("Bash|agent_run_shell_command", "agent_run_shell_command", {}, True),
    ("Bash|agent_run_shell_command", "Edit", {}, False),
    # wildcard inside a name
    ("Edit*", "EditFile", {}, True),
    ("*git*", "run_git_command", {}, True),
    # empty matcher never matches
    ("", "Edit", {}, False),
    # compound precedence: Edit && .py || Bash
    ("Edit && .py || Bash", "Edit", {"file_path": "app.py"}, True),
    ("Edit && .py || Bash", "Bash", {}, True),
    ("Edit && .py || Bash", "Edit", {"file_path": "app.js"}, False),
    # Anthropic native-editor facade tool: without an alias entry, hooks
    # written against Edit/Write/replace_in_file/create_file silently stop
    # firing when an agent runs the native-editor profile, since the wire
    # tool name (str_replace_based_edit_tool) shares nothing textually with
    # any of those names. See hook_engine/aliases.py's
    # ANTHROPIC_NATIVE_EDITOR_ALIASES for the mapping this exercises.
    ("Edit", "str_replace_based_edit_tool", {"path": "app.py"}, True),
    ("replace_in_file", "str_replace_based_edit_tool", {"path": "app.py"}, True),
]


@pytest.mark.parametrize(
    "matcher,tool_name,tool_args,expected",
    _MATCH_CASES,
    ids=[f"{m}~{t}" for m, t, _a, _e in _MATCH_CASES],
)
def test_matches(matcher, tool_name, tool_args, expected):
    assert matches(matcher, tool_name, tool_args) is expected


class TestExtractFilePath:
    def test_file_path_key(self):
        assert _extract_file_path({"file_path": "test.py"}) == "test.py"

    def test_path_key(self):
        assert _extract_file_path({"path": "/tmp/test.py"}) == "/tmp/test.py"

    def test_file_key(self):
        assert _extract_file_path({"file": "test.py"}) == "test.py"

    def test_no_file_path(self):
        assert _extract_file_path({"command": "ls"}) is None

    def test_empty_args(self):
        assert _extract_file_path({}) is None

    def test_priority_order(self):
        # file_path takes priority over path
        result = _extract_file_path({"file_path": "a.py", "path": "b.py"})
        assert result == "a.py"


def test_distinct_alias_groups_stay_disjoint():
    """Guard rail for the obvious 'fix' to the native-editor alias gap.

    ``str_replace_based_edit_tool`` multiplexes view/str_replace/create/
    insert, so it's tempting to widen ANTHROPIC_NATIVE_EDITOR_ALIASES to
    map it to create_file and read_file as well. That silently breaks
    unrelated hooks: ``_build_lookup`` groups by internal name and unions
    every provider name mapping to it, so a second mapping transitively
    merges the Edit and Write groups and ``matches("Write", "Edit")``
    starts returning True -- a hook scoped to file creation would begin
    firing on every in-place edit.

    Asserted through the public matcher (not the lookup internals) because
    the cross-group bleed is what actually harms users.
    """
    assert not matches("Write", "Edit", {"file_path": "a.py"})
    assert not matches("create_file", "replace_in_file", {"file_path": "a.py"})
    assert not matches("Read", "Edit", {"file_path": "a.py"})
    assert not matches("read_file", "replace_in_file", {"file_path": "a.py"})
