"""End-to-end grep behavior against the real ripgrep binary.

Covers the output contract the model relies on: -A/-B/-C context lines are
returned, -t restricts types, and a trailing value flag errors instead of
silently re-scoping the search.
"""

from code_puppy.tools import file_operations
from code_puppy.tools.file_operations import (
    _MAX_GREP_CONTEXT_ROWS,
    _MAX_GREP_MATCHES,
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


def test_grep_searches_a_root_nested_under_an_ignored_directory(tmp_path):
    """A root sitting *inside* an ignored directory name must still be searched.

    ``DIR_IGNORE_PATTERNS`` carries ``**/tmp/**`` (and ``**/.cache/**``,
    ``**/node_modules/**`` ...) to prune a project's own scratch dirs. Matched
    against absolute paths they also matched the search root's *ancestors*, so a
    root under /tmp -- every pytest tmp_path on Linux, and any project parked in
    /tmp, ~/.cache or node_modules -- had every file skipped: zero matches, no
    error, completely silent. CI only runs macOS, whose temp dirs live elsewhere.
    """
    root = tmp_path / ".cache" / "checkout"
    root.mkdir(parents=True)
    (root / "app.py").write_text("needle\n")

    out = _grep(None, "needle", str(root))

    assert out.error is None
    assert [m.line_content for m in out.matches] == ["needle"]


def test_grep_still_prunes_ignored_dirs_inside_the_search_root(tmp_path):
    """The ancestor fix must not weaken ignoring below the root.

    Also pins that reported paths stay absolute now that ripgrep is handed '.'.
    """
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "vendored.py").write_text("needle\n")
    (tmp_path / "app.py").write_text("needle\n")

    out = _grep(None, "needle", str(tmp_path))

    assert out.error is None
    assert {m.file_path for m in out.matches} == {str(tmp_path / "app.py")}


def test_grep_missing_directory_names_the_directory(tmp_path):
    """A bad target must blame itself, not the ripgrep binary we cwd'd into it."""
    missing = tmp_path / "nope"

    out = _grep(None, "needle", str(missing))

    assert out.matches == []
    assert out.error is not None and "does not exist" in out.error


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


def _write_hits(path, count):
    path.write_text("".join(f"hit {i}\n" for i in range(count)))


def test_grep_beyond_budget_is_flagged_truncated(tmp_path):
    """More matches than the budget -> truncated=True, budget-sized result (#903)."""
    for name in ("a.py", "b.py", "c.py"):
        _write_hits(tmp_path / name, 30)

    out = _grep(None, "hit", str(tmp_path))

    assert out.error is None
    assert len(out.matches) == _MAX_GREP_MATCHES
    assert out.truncated is True


def test_grep_exactly_at_budget_is_not_truncated(tmp_path):
    """Exactly the budget is complete, not truncated -- never lie either way."""
    _write_hits(tmp_path / "a.py", 20)
    _write_hits(tmp_path / "b.py", _MAX_GREP_MATCHES - 20)

    out = _grep(None, "hit", str(tmp_path))

    assert out.error is None
    assert len(out.matches) == _MAX_GREP_MATCHES
    assert out.truncated is False


def test_grep_single_file_beyond_budget_is_flagged_truncated(tmp_path):
    """ripgrep's per-file --max-count must not mask truncation in one fat file."""
    _write_hits(tmp_path / "fat.py", _MAX_GREP_MATCHES + 1)

    out = _grep(None, "hit", str(tmp_path))

    assert out.error is None
    assert len(out.matches) == _MAX_GREP_MATCHES
    assert out.truncated is True


def test_grep_truncation_survives_context_lines(tmp_path):
    """Context rows neither consume the budget nor hide that it overflowed."""
    lines = ["target", "filler"] * (_MAX_GREP_MATCHES + 5)
    (tmp_path / "ctx.py").write_text("\n".join(lines) + "\n")

    out = _grep(None, "-A 1 target", str(tmp_path))

    real = [m for m in out.matches if not m.is_context]
    assert len(real) == _MAX_GREP_MATCHES
    assert out.truncated is True


def test_emit_grep_result_forwards_truncated_to_ui(monkeypatch):
    captured = {}

    class _Bus:
        def emit(self, message):
            captured["msg"] = message

    monkeypatch.setattr(file_operations, "get_message_bus", lambda: _Bus())

    out = _emit_grep_result("t", ".", [], None, truncated=True)

    assert out.truncated is True
    assert captured["msg"].truncated is True
