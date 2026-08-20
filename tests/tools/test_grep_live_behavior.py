"""End-to-end grep behavior against the real ripgrep binary.

Covers the output contract the model relies on: -A/-B/-C context lines are
returned, -t restricts types, and a trailing value flag errors instead of
silently re-scoping the search.
"""

from code_puppy.tools import file_operations
from code_puppy.tools.file_operations import (
    _MAX_GREP_CONTEXT_ROWS,
    MatchInfo,
    _emit_grep_result,
    _grep,
)


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


def test_grep_context_lines_do_not_evict_real_matches(tmp_path):
    """Under -C, the 50-cap counts real matches; context lines ride along free."""
    # 60 real matches, each isolated by filler so -C pulls in context lines.
    block = "filler\ntarget\nfiller\n"
    (tmp_path / "big.py").write_text(block * 60)

    out = _grep(None, "-C 1 target", str(tmp_path))

    assert out.error is None
    real = [m for m in out.matches if not m.is_context]
    context = [m for m in out.matches if m.is_context]
    # The old total-count cap let context lines evict real matches well before
    # 50; real matches must now fill the whole budget.
    assert len(real) == 50
    assert all(m.line_content == "target" for m in real)
    # Context lines are still surfaced, just never counted as matches.
    assert context


def test_wide_context_is_capped_without_evicting_matches(tmp_path):
    """A wide -C caps context rows separately; real matches still fill the budget.

    Context is bounded by ``_MAX_GREP_CONTEXT_ROWS`` so an enormous -C can't grow
    the output without limit, yet the 50 real matches are never evicted.
    """
    # A large filler preamble sits within a huge context radius of the first
    # match, so the raw context stream far exceeds the cap; the 60 matches then
    # exceed the 50-match budget.
    lines = ["filler"] * 400 + ["target", "filler"] * 60
    (tmp_path / "big.py").write_text("\n".join(lines) + "\n")

    out = _grep(None, "-C 9999 target", str(tmp_path))

    assert out.error is None
    real = [m for m in out.matches if not m.is_context]
    assert len(real) == 50
    assert len(out.matches) <= 50 + _MAX_GREP_CONTEXT_ROWS


def test_emit_grep_result_excludes_context_from_counts(monkeypatch):
    """total_matches / files_searched count real matches only, not context."""
    captured = {}

    class _Bus:
        def emit(self, message):
            captured["msg"] = message

    monkeypatch.setattr(file_operations, "get_message_bus", lambda: _Bus())

    matches = [
        MatchInfo(file_path="a.py", line_number=1, line_content="hit"),
        MatchInfo(file_path="c.py", line_number=2, line_content="ctx", is_context=True),
        MatchInfo(file_path="b.py", line_number=9, line_content="hit"),
    ]

    out = _emit_grep_result("target", ".", matches, None)

    # Context stays in the displayed/returned matches...
    assert len(out.matches) == 3
    # ...but only the two real hits (in a.py and b.py) feed the counts.
    assert captured["msg"].total_matches == 2
    assert captured["msg"].files_searched == 2
