"""Tests for hook engine pattern matcher."""

from code_puppy.hook_engine.matcher import _extract_file_path, matches


class TestMatches:
    def test_wildcard_matches_all(self):
        assert matches("*", "Edit", {}) is True
        assert matches("*", "Bash", {"command": "ls"}) is True

    def test_exact_tool_name(self):
        assert matches("Edit", "Edit", {}) is True
        assert matches("Edit", "Bash", {}) is False

    def test_case_insensitive_tool_name(self):
        assert matches("edit", "Edit", {}) is True
        assert matches("BASH", "bash", {}) is True

    def test_file_extension_match(self):
        assert matches(".py", "Edit", {"file_path": "test.py"}) is True
        assert matches(".py", "Edit", {"file_path": "test.js"}) is False
        assert matches(".ts", "Edit", {"file_path": "app.ts"}) is True

    def test_and_condition(self):
        assert matches("Edit && .py", "Edit", {"file_path": "test.py"}) is True
        assert matches("Edit && .py", "Edit", {"file_path": "test.js"}) is False
        assert matches("Edit && .py", "Bash", {"file_path": "test.py"}) is False

    def test_or_condition(self):
        assert matches("Edit || Write", "Edit", {}) is True
        assert matches("Edit || Write", "Write", {}) is True
        assert matches("Edit || Write", "Bash", {}) is False

    def test_pipe_regex_as_or(self):
        assert matches("Bash|agent_run_shell_command", "Bash", {}) is True
        assert (
            matches("Bash|agent_run_shell_command", "agent_run_shell_command", {})
            is True
        )
        assert matches("Bash|agent_run_shell_command", "Edit", {}) is False

    def test_wildcard_in_name(self):
        assert matches("Edit*", "EditFile", {}) is True
        assert matches("*git*", "run_git_command", {}) is True

    def test_empty_matcher_returns_false(self):
        assert matches("", "Edit", {}) is False

    def test_complex_compound(self):
        assert matches("Edit && .py || Bash", "Edit", {"file_path": "app.py"}) is True
        assert matches("Edit && .py || Bash", "Bash", {}) is True
        assert matches("Edit && .py || Bash", "Edit", {"file_path": "app.js"}) is False


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
