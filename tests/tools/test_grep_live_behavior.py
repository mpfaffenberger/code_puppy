"""End-to-end grep behavior against the real ripgrep binary.

Covers the output contract the model relies on: -A/-B/-C context lines are
returned, -t restricts types, and a trailing value flag errors instead of
silently re-scoping the search.
"""

from code_puppy.tools.file_operations import _grep


def _setup(tmp_path):
    (tmp_path / "a.py").write_text("line1\nmatch\nline3\nmatch\nline5\n")
    (tmp_path / "b.txt").write_text("match\n")


def test_grep_returns_context_lines(tmp_path):
    _setup(tmp_path)

    out = _grep(None, "-A 1 match", str(tmp_path))

    contents = [m.line_content for m in out.matches]
    assert out.error is None
    # a.py contributes 2 matches + 2 context lines; b.txt contributes 1 match.
    assert "line3" in contents and "line5" in contents
    assert contents.count("match") == 3


def test_grep_type_flag_restricts_matches(tmp_path):
    _setup(tmp_path)

    out = _grep(None, "-t py match", str(tmp_path))

    assert out.error is None
    assert {m.file_path for m in out.matches} == {str(tmp_path / "a.py")}


def test_grep_trailing_value_flag_errors(tmp_path):
    _setup(tmp_path)

    out = _grep(None, "-t", str(tmp_path))

    assert out.matches == []
    assert out.error is not None
    assert "value" in out.error
