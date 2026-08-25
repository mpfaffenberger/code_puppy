"""Focused tests for the Codex/OpenCode patch contract."""

from pathlib import Path

import pytest

from code_puppy.tools.apply_patch import PatchError, _apply_changes, parse_patch


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


@pytest.mark.parametrize("raw_path", ["../outside.txt", "/tmp/outside.txt", ""])
def test_patch_rejects_paths_outside_or_without_a_target(tmp_path: Path, raw_path: str):
    with pytest.raises(PatchError):
        parse_patch(
            f"""*** Begin Patch
*** Add File: {raw_path}
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
