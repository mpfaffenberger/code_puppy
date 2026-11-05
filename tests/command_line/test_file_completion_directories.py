"""@name completion must surface folders and only rows whose name matches."""

import os
import shutil

import pytest
from termflow.tui.completion import Document

from code_puppy.command_line import file_index as fi
from code_puppy.command_line.file_path_completion import FilePathCompleter
from code_puppy.file_completion_io import read_paths

FILES = [
    os.path.join("Exact-folderName", "readme.md"),
    os.path.join("Exact-folderName", "nested", "inner.py"),
    os.path.join("Exact-folderName", "nested", "deep", "leaf.txt"),
    os.path.join("Exact-folderNameTwo", "two.md"),
    "Exact-folderName.txt",
    "unrelated.txt",
]


@pytest.fixture
def complete(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    snapshot = fi._make_index(os.getcwd(), FILES)
    monkeypatch.setattr(fi, "get_index", lambda: snapshot)
    monkeypatch.setattr(fi, "reindex", lambda *a, **kw: None)

    def run(query):
        text = "@" + query
        return list(
            FilePathCompleter().get_completions(Document(text, len(text)), None)
        )

    return run


def test_exact_folder_name_surfaces_the_folder_first(complete):
    results = complete("Exact-folderName")
    assert results[0].text == "Exact-folderName"
    assert results[0].display_meta == "Exact-folderName" + os.sep


def test_prefix_lists_every_matching_folder_and_file(complete):
    assert {r.text for r in complete("Exact-fold")} == {
        "Exact-folderName",
        "Exact-folderNameTwo",
        "Exact-folderName.txt",
    }


def test_every_row_name_contains_the_query(complete):
    for query in ("Exact-folderName", "nested", "leaf"):
        rows = complete(query)
        assert rows
        assert all(query.lower() in r.display.lower() for r in rows)


def test_nested_folder_found_by_name_with_full_path_inserted(complete):
    results = complete("nest")
    assert [r.text for r in results] == [os.path.join("Exact-folderName", "nested")]


def test_folder_lookup_is_case_insensitive(complete):
    assert complete("exact-folderN")[0].text == "Exact-folderName"


def test_file_lookup_still_works(complete):
    assert [r.text for r in complete("unrel")] == ["unrelated.txt"]


def test_ignored_directories_are_not_indexed(tmp_path):
    rg = shutil.which("rg")
    if not rg:
        pytest.skip("ripgrep unavailable")
    (tmp_path / ".ignore").write_text("ignored\n")
    (tmp_path / "ignored").mkdir()
    (tmp_path / "ignored" / "x.py").touch()
    (tmp_path / "kept").mkdir()
    (tmp_path / "kept" / "y.py").touch()
    paths = read_paths(rg, str(tmp_path), 100, 5)
    assert paths is not None
    snapshot = fi._make_index(str(tmp_path), paths)
    assert "kept" in snapshot.dirs
    assert "ignored" not in snapshot.dirs
