"""Safety-contract regression tests for ``_replace_in_file``.

This module replaces ``tests/test_replace_in_file_baseline.py`` (2026-08-25),
which documented the pre-fix behavior of
``code_puppy.tools.file_modifications._replace_in_file`` -- including several
live bugs (silent empty-``old_str`` corruption, unconditional undo recording,
a fuzzy-mutation fallback that could silently pick the wrong location). That
baseline was used to verify this fix actually changes behavior; it is
superseded by this file, which asserts the corrected, intended contract:

- an empty ``old_str`` is rejected explicitly, never silently mutated;
- zero exact matches and ambiguous (multiple) exact matches both fail closed
  without writing -- fuzzy matching is used only to build a bounded,
  whole-line suggestion, never to select a mutation target;
- undo is recorded exactly once, only immediately before a real write, never
  on a validation failure or no-op; and
- a plain no-op replacement is reported as such without erroring.
"""

from unittest.mock import patch

from code_puppy.tools.file_modifications import _replace_in_file
from code_puppy.undo_manager import UndoManager


def _write(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(content)
    return p


def test_empty_old_str_is_rejected_explicitly(tmp_path):
    """An empty old_str must never be treated as a valid (zero-width) match."""
    original = "line1\nline2\nline3\n"
    p = _write(tmp_path, "f.txt", original)

    result = _replace_in_file(None, str(p), [{"old_str": "", "new_str": "INJECTED"}])

    assert result["error"] == "empty_old_str"
    assert "diff" in result
    assert not result.get("success")
    # File must be completely untouched -- no silent prepend.
    assert p.read_text() == original


def test_near_miss_fuzzy_match_fails_closed_with_suggestion(tmp_path):
    """A near-miss (high overlap, not exact) must fail closed with a bounded
    suggestion, never silently mutate at the closest guess."""
    original = "STATUS_LINE: not_started\nother\n"
    p = _write(tmp_path, "f2.txt", original)

    result = _replace_in_file(
        None,
        str(p),
        [{"old_str": "STATUS_LINE: done", "new_str": "STATUS_LINE: xxx"}],
    )

    assert result["error"] == "match_not_found"
    assert result["match_count"] == 0
    assert result["received"] == "STATUS_LINE: done"
    assert result["diff"] == ""
    # A bounded, whole-line, line-numbered suggestion is offered for retry.
    assert "suggested_current_text" in result
    assert "1: STATUS_LINE: not_started" in result["suggested_current_text"]

    # File is untouched on a failed match -- no approximate mutation.
    assert p.read_text() == original


def test_record_change_not_called_on_guaranteed_failure(tmp_path):
    """must not be recorded when nothing was written."""
    missing = tmp_path / "does_not_exist.txt"

    with patch("code_puppy.undo_manager.UndoManager.record_change") as mock_record:
        result = _replace_in_file(None, str(missing), [{"old_str": "a", "new_str": "b"}])

    assert result["error"] == f"File '{missing}' does not exist."
    mock_record.assert_not_called()


def test_record_change_called_once_only_on_successful_write(tmp_path):
    """Undo must be captured once and committed once, only after a real write.

    capture_change/commit_change (rather than the old one-shot record_change)
    is what lets a failed write skip history entirely without an unsafe
    pop-the-most-recent-entry rollback -- see UndoManager.capture_change.
    """
    p = _write(tmp_path, "f3.txt", "hello world\n")

    with (
        patch(
            "code_puppy.undo_manager.UndoManager.capture_change",
            wraps=UndoManager().capture_change,
        ) as mock_capture,
        patch(
            "code_puppy.undo_manager.UndoManager.commit_change",
            wraps=UndoManager().commit_change,
        ) as mock_commit,
    ):
        result = _replace_in_file(None, str(p), [{"old_str": "hello", "new_str": "hi"}])

    assert result["success"] is True
    assert result["changed"] is True
    mock_capture.assert_called_once_with(str(p), "replace_in_file")
    mock_commit.assert_called_once()


def test_noop_replacement_returns_changed_false_without_recording_undo(tmp_path):
    """A no-op (old_str == new_str, present) must report unchanged, not error,
    and must not record undo since nothing was written."""
    original = "hello world\n"
    p = _write(tmp_path, "f4.txt", original)

    with patch("code_puppy.undo_manager.UndoManager.record_change") as mock_record:
        result = _replace_in_file(None, str(p), [{"old_str": "hello", "new_str": "hello"}])

    assert "error" not in result
    assert result["success"] is False
    assert result["changed"] is False
    assert result["message"] == "No changes to apply."
    assert result["diff"] == ""
    mock_record.assert_not_called()

    assert p.read_text() == original


def test_zero_exact_matches_fails_closed_without_writing(tmp_path):
    """A wholly-absent pattern fails closed with no fuzzy guess applied."""
    original = "aaaa\nbbbb\ncccc\n"
    p = _write(tmp_path, "f5.txt", original)

    result = _replace_in_file(None, str(p), [{"old_str": "zzzzzzzzzzz", "new_str": "q"}])

    assert result["error"] == "match_not_found"
    assert result["match_count"] == 0
    assert result["received"] == "zzzzzzzzzzz"
    assert result["diff"] == ""

    assert p.read_text() == original


def test_multiple_exact_matches_is_ambiguous_and_fails_closed(tmp_path):
    """Multiple exact matches must never guess "the first one" -- fail closed
    and require the caller to disambiguate. This is a deliberate behavior
    change from the old ``str.replace(old, new, 1)`` silent-first-match
    approach."""
    p = _write(tmp_path, "f6.txt", "dog dog dog\n")

    result = _replace_in_file(None, str(p), [{"old_str": "dog", "new_str": "cat"}])

    assert result["error"] == "ambiguous_match"
    assert result["match_count"] == 3
    assert result["received"] == "dog"
    assert result["diff"] == ""

    # File is untouched -- no first-match guess applied.
    assert p.read_text() == "dog dog dog\n"


def test_unique_exact_match_replaces_and_preserves_crlf(tmp_path):
    """A single unique exact match is applied via plain string replacement,
    which naturally preserves original line endings (CRLF in this case) --
    unlike the old fuzzy-branch splitlines()/join() reconstruction, which
    normalized CRLF to LF across the whole file on any fuzzy hit."""
    p = tmp_path / "f7.txt"
    p.write_bytes(b"line one\r\nline two\r\nline three\r\n")

    result = _replace_in_file(
        None, str(p), [{"old_str": "line two", "new_str": "LINE TWO"}]
    )

    assert result["success"] is True
    assert result["changed"] is True
    assert p.read_bytes() == b"line one\r\nLINE TWO\r\nline three\r\n"


def test_undo_restores_true_pre_edit_content(tmp_path):
    """Regression guard for a subtle timing bug introduced (and caught by
    tests/tools/test_fs_backend.py::test_undo_is_backend_coherent) while
    fixing this file: record_change() snapshots whatever is CURRENTLY on
    disk, so it must run immediately before the write, never after -- after
    the write it would snapshot the NEW content and undo would restore into
    a no-op instead of reverting."""
    from code_puppy.undo_manager import UndoManager

    original = "before\n"
    p = _write(tmp_path, "f9.txt", original)

    UndoManager()._instance.history.clear()
    result = _replace_in_file(None, str(p), [{"old_str": "before", "new_str": "after"}])
    assert result["success"] is True
    assert p.read_text() == "after\n"

    msg = UndoManager().undo_last()
    assert "restored" in msg
    assert p.read_text() == original


def test_crlf_file_matches_model_supplied_lf_pattern(tmp_path):
    """Regression guard for a break introduced while fixing CRLF handling.

    Making the I/O layer byte-faithful (newline="") is correct, but it means
    in-memory content keeps literal \\r\\n while models ALWAYS emit \\n in
    old_str. Without reconciliation every multi-line edit to every CRLF file
    failed with match_count=0 despite a perfect jw_score of 1.0.
    """
    p = tmp_path / "crlf.py"
    p.write_bytes(b"def foo():\r\n    return 1\r\n\r\ndef bar():\r\n    return 2\r\n")

    result = _replace_in_file(
        None,
        str(p),
        [{"old_str": "def foo():\n    return 1", "new_str": "def foo():\n    return 99"}],
    )

    assert result["success"] is True
    assert p.read_bytes() == (
        b"def foo():\r\n    return 99\r\n\r\ndef bar():\r\n    return 2\r\n"
    )


def test_multiline_new_str_adopts_file_line_endings(tmp_path):
    """Inserted text must adopt the file's style, not leave an LF island."""
    p = tmp_path / "crlf2.py"
    p.write_bytes(b"a = 1\r\nb = 2\r\n")

    result = _replace_in_file(
        None, str(p), [{"old_str": "a = 1", "new_str": "a = 1\nassert a"}]
    )

    assert result["success"] is True
    assert p.read_bytes() == b"a = 1\r\nassert a\r\nb = 2\r\n"


def test_mixed_line_endings_leave_untouched_regions_byte_identical(tmp_path):
    """A targeted edit must not normalize terminators elsewhere in the file."""
    p = tmp_path / "mixed.py"
    p.write_bytes(b"crlf = 1\r\nlf = 2\ncrlf2 = 3\r\n")

    result = _replace_in_file(
        None, str(p), [{"old_str": "lf = 2", "new_str": "lf = 22"}]
    )

    assert result["success"] is True
    assert p.read_bytes() == b"crlf = 1\r\nlf = 22\ncrlf2 = 3\r\n"


def test_cr_only_legacy_file_is_editable(tmp_path):
    """Classic-Mac CR-only files must round-trip without corruption."""
    p = tmp_path / "cr.py"
    p.write_bytes(b"a = 1\rb = 2\r")

    result = _replace_in_file(
        None, str(p), [{"old_str": "a = 1\rb = 2", "new_str": "a = 9\rb = 8"}]
    )

    assert result["success"] is True
    assert p.read_bytes() == b"a = 9\rb = 8\r"


def test_atomic_multi_replacement_all_or_nothing(tmp_path):
    """If any replacement in a multi-replacement batch is invalid, none of
    the batch is written -- validated fully in memory before a single write."""
    original = "alpha\nbeta\ngamma\n"
    p = _write(tmp_path, "f8.txt", original)

    result = _replace_in_file(
        None,
        str(p),
        [
            {"old_str": "alpha", "new_str": "ALPHA"},
            {"old_str": "does-not-exist", "new_str": "X"},
        ],
    )

    assert result["error"] == "match_not_found"
    # Neither replacement was applied -- the first one is not partially written.
    assert p.read_text() == original
