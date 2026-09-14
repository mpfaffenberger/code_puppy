"""Focused tests for the Codex/OpenCode patch contract."""

from pathlib import Path

import pytest

from code_puppy.tools.apply_patch import (
    PatchError,
    _apply_changes,
    _diff_operation,
    _parse_chunks,
    _seek_sequence,
    parse_patch,
)


@pytest.mark.parametrize(
    ("kind", "operation"),
    [
        ("add", "create"),
        ("update", "modify"),
        ("move", "modify"),
        ("delete", "delete"),
    ],
)
def test_diff_operation_uses_renderer_vocabulary(kind: str, operation: str):
    assert _diff_operation(kind) == operation


def test_seek_sequence_exact_match():
    assert _seek_sequence(["foo", "bar", "baz"], ["bar", "baz"], 0) == 1


def test_seek_sequence_rstrip_match():
    assert _seek_sequence(["foo   ", "bar\t\t"], ["foo", "bar"], 0) == 0


def test_seek_sequence_trim_match():
    assert _seek_sequence(["    foo   ", "   bar\t"], ["foo", "bar"], 0) == 0


def test_seek_sequence_normalizes_unicode_punctuation():
    source = ["“quoted” — isn’t\u00a0plain"]
    assert _seek_sequence(source, ['"quoted" - isn\'t plain'], 0) == 0


def test_seek_sequence_pattern_longer_than_input():
    assert _seek_sequence(["just one line"], ["too", "many", "lines"], 0) is None


def test_seek_sequence_empty_pattern_returns_start():
    assert _seek_sequence(["line"], [], 1) == 1


def test_seek_sequence_eof_is_anchored_only_no_fallback():
    # Rust seek_sequence restricts every pass to the single EOF-anchored index
    # when eof=true; a pattern matching only mid-file is NOT found. (The Rust
    # doc comment mentions a fallback, but the code has none.)
    assert _seek_sequence(["match", "tail"], ["match"], 0, eof=True) is None
    assert _seek_sequence(["head", "match"], ["match"], 0, eof=True) == 1


def test_update_patch_applies_context_and_replacement(tmp_path: Path):
    target = tmp_path / "app.py"
    target.write_text("one\ntwo\nthree\n")

    changes = parse_patch(
        """*** Begin Patch
*** Update File: app.py
@@
 one
-two
+TWO
 three
*** End Patch""",
        base_dir=str(tmp_path),
    )

    assert len(changes) == 1
    assert changes[0].new_content == "one\nTWO\nthree\n"


def test_update_patch_accepts_open_code_end_of_file_marker(tmp_path: Path):
    target = tmp_path / "app.py"
    target.write_text("one\ntwo\n")

    changes = parse_patch(
        """wrapper text
*** Begin Patch
*** Update File: app.py
@@
 one
-two
+TWO
*** End of File
*** End Patch
trailing text""",
        base_dir=str(tmp_path),
    )

    assert changes[0].new_content == "one\nTWO\n"


def test_change_context_seeks_and_disambiguates_identical_hunks(tmp_path: Path):
    target = tmp_path / "app.py"
    target.write_text("def first():\n    value = 1\n\ndef second():\n    value = 1\n")

    changes = parse_patch(
        """*** Begin Patch
*** Update File: app.py
@@ def first():
-    value = 1
+    value = 10
@@ def second():
-    value = 1
+    value = 20
*** End Patch""",
        base_dir=str(tmp_path),
    )

    assert changes[0].new_content == (
        "def first():\n    value = 10\n\ndef second():\n    value = 20\n"
    )


def test_missing_change_context_reports_codex_error(tmp_path: Path):
    target = tmp_path / "app.py"
    target.write_text("present\n")

    with pytest.raises(
        PatchError, match=r"Failed to find context 'missing' in .*app\.py"
    ):
        parse_patch(
            """*** Begin Patch
*** Update File: app.py
@@ missing
-present
+changed
*** End Patch""",
            base_dir=str(tmp_path),
        )


def test_end_of_file_match_is_anchored_before_fallback(tmp_path: Path):
    target = tmp_path / "app.py"
    target.write_text("same\nmiddle\nsame\n")

    changes = parse_patch(
        """*** Begin Patch
*** Update File: app.py
@@
-same
+last
*** End of File
*** End Patch""",
        base_dir=str(tmp_path),
    )

    assert changes[0].new_content == "same\nmiddle\nlast\n"


def test_trailing_empty_line_match_retries_without_sentinel(tmp_path: Path):
    target = tmp_path / "app.py"
    target.write_text("first\nlast\n")

    changes = parse_patch(
        """*** Begin Patch
*** Update File: app.py
@@
-last

*** End of File
*** End Patch""",
        base_dir=str(tmp_path),
    )

    assert changes[0].new_content == "first\n"


def test_pure_addition_appends_at_end_not_cursor(tmp_path: Path):
    target = tmp_path / "app.py"
    target.write_text("first\nsecond\n")

    changes = parse_patch(
        """*** Begin Patch
*** Update File: app.py
@@ first
+third
*** End Patch""",
        base_dir=str(tmp_path),
    )

    assert changes[0].new_content == "first\nsecond\nthird\n"


def test_empty_line_inside_hunk_is_empty_context(tmp_path: Path):
    target = tmp_path / "app.py"
    target.write_text("one\n\ntwo\n")

    changes = parse_patch(
        """*** Begin Patch
*** Update File: app.py
@@
 one

-two
+TWO
*** End Patch""",
        base_dir=str(tmp_path),
    )

    assert changes[0].new_content == "one\n\nTWO\n"


def test_first_update_chunk_may_omit_context_marker(tmp_path: Path):
    target = tmp_path / "app.py"
    target.write_text("import foo\n")

    changes = parse_patch(
        """*** Begin Patch
*** Update File: app.py
 import foo
+bar
*** End Patch""",
        base_dir=str(tmp_path),
    )

    assert changes[0].new_content == "import foo\nbar\n"


def test_unknown_prefix_after_diff_starts_next_chunk():
    chunks = _parse_chunks(
        ["@@ first", "-old", "+new", "@@ second", "-before", "+after"],
        "app.py",
    )

    assert len(chunks) == 2
    assert chunks[0].change_context == "first"
    assert chunks[1].change_context == "second"


def test_blank_lines_between_chunks_are_skipped():
    chunks = _parse_chunks(
        ["@@ first", "-old", "+new", "", "   ", "@@ second", "-before", "+after"],
        "app.py",
    )

    assert chunks[0].old_lines == ("old",)
    assert chunks[0].new_lines == ("new",)
    assert chunks[1].change_context == "second"


def test_unknown_prefix_as_first_diff_line_uses_codex_error():
    with pytest.raises(PatchError, match="Unexpected line found in update hunk"):
        _parse_chunks(["@@", "invalid"], "app.py")


def test_patch_supports_add_delete_and_move(tmp_path: Path):
    old = tmp_path / "old.txt"
    old.write_text("old\n")
    doomed = tmp_path / "doomed.txt"
    doomed.write_text("remove me\n")

    changes = parse_patch(
        """*** Begin Patch
*** Add File: new.txt
+created
*** Update File: old.txt
*** Move to: moved.txt
@@
-old
+moved
*** Delete File: doomed.txt
*** End Patch""",
        base_dir=str(tmp_path),
    )

    assert [(change.kind, change.path.rsplit("/", 1)[-1]) for change in changes] == [
        ("add", "new.txt"),
        ("move", "old.txt"),
        ("delete", "doomed.txt"),
    ]
    assert changes[1].move_to == str(tmp_path / "moved.txt")
    assert changes[1].new_content == "moved\n"


def test_patch_changes_are_applied_after_full_validation(tmp_path: Path):
    old = tmp_path / "old.txt"
    old.write_text("old\n")
    doomed = tmp_path / "doomed.txt"
    doomed.write_text("remove me\n")

    changes = parse_patch(
        """*** Begin Patch
*** Add File: new.txt
+created
*** Update File: old.txt
*** Move to: moved.txt
@@
-old
+moved
*** Delete File: doomed.txt
*** End Patch""",
        base_dir=str(tmp_path),
    )
    _apply_changes(changes)

    assert (tmp_path / "new.txt").read_text() == "created\n"
    assert not old.exists()
    assert (tmp_path / "moved.txt").read_text() == "moved\n"
    assert not doomed.exists()


def test_patch_accepts_sibling_path(tmp_path: Path):
    base = tmp_path / "project"
    base.mkdir()

    changes = parse_patch(
        """*** Begin Patch
*** Add File: ../sibling/new.txt
+created
*** End Patch""",
        base_dir=str(base),
    )

    assert changes[0].path == str(tmp_path / "sibling" / "new.txt")


def test_patch_accepts_absolute_path(tmp_path: Path):
    target = tmp_path / "absolute.txt"

    changes = parse_patch(
        f"""*** Begin Patch
*** Add File: {target}
+created
*** End Patch""",
        base_dir=str(tmp_path / "unrelated"),
    )

    assert changes[0].path == str(target)


def test_patch_resolves_sibling_move_destination(tmp_path: Path):
    base = tmp_path / "project"
    base.mkdir()
    (base / "old.txt").write_text("old\n")

    changes = parse_patch(
        """*** Begin Patch
*** Update File: old.txt
*** Move to: ../sibling/moved.txt
@@
-old
+moved
*** End Patch""",
        base_dir=str(base),
    )

    assert changes[0].move_to == str(tmp_path / "sibling" / "moved.txt")


def test_patch_rejects_empty_path(tmp_path: Path):
    with pytest.raises(PatchError):
        parse_patch(
            """*** Begin Patch
*** Add File:
+unsafe
*** End Patch""",
            base_dir=str(tmp_path),
        )


def test_patch_rejects_stale_context_without_touching_file(tmp_path: Path):
    target = tmp_path / "app.py"
    target.write_text("current\n")

    with pytest.raises(PatchError):
        parse_patch(
            """*** Begin Patch
*** Update File: app.py
@@
-stale
+new
*** End Patch""",
            base_dir=str(tmp_path),
        )

    assert target.read_text() == "current\n"
