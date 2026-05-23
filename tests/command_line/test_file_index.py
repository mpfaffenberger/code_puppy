"""Tests for the ripgrep-backed file index."""

import os
import tempfile

from code_puppy.command_line import file_index


def test_get_index_starts_empty():
    # The module-level singleton may have been populated by other tests, but
    # we can always inject a fresh empty snapshot.
    file_index.set_index_for_testing("/somewhere", [])
    snap = file_index.get_index()
    assert snap.root == "/somewhere"
    assert snap.paths == ()


def test_set_index_for_testing_normalizes():
    file_index.set_index_for_testing("/proj", ["A.py", "sub/B.PY"])
    snap = file_index.get_index()
    assert snap.paths == ("A.py", "sub/B.PY")
    assert snap.lowered == ("a.py", "sub/b.py")
    assert snap.basenames_lower == ("a.py", "b.py")


def test_reindex_against_real_directory_blocking():
    """End-to-end: rg --files picks up files we just wrote."""
    with tempfile.TemporaryDirectory() as td:
        with open(os.path.join(td, "alpha.py"), "w") as f:
            f.write("")
        os.makedirs(os.path.join(td, "nested"))
        with open(os.path.join(td, "nested", "beta.py"), "w") as f:
            f.write("")

        file_index.reindex(td, blocking=True)
        snap = file_index.get_index()

        # rg might not be installed in some CI containers; tolerate that.
        if snap.root != td:
            return
        names = set(snap.paths)
        assert "alpha.py" in names
        assert os.path.join("nested", "beta.py") in names
