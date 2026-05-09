"""Tests for file listing caps, huge-file gates, and diff capping (Epic 3/7)."""

from unittest.mock import MagicMock

from pydantic_ai import RunContext


def test_list_files_caps_ui_entries(tmp_path, monkeypatch):
    from code_puppy.tools.file_operations import (
        MAX_LIST_FILES_UI_ENTRIES,
        _list_files,
    )

    monkeypatch.chdir(tmp_path)
    for i in range(MAX_LIST_FILES_UI_ENTRIES + 10):
        (tmp_path / f"f{i}.txt").write_text("x")

    ctx = MagicMock(spec=RunContext)
    result = _list_files(ctx, str(tmp_path), recursive=False)
    assert (
        "truncated" in result.content.lower()
        or "truncated" in (result.error or "").lower()
    )


def test_list_files_caps_llm_content(tmp_path, monkeypatch):
    from code_puppy.tools.file_operations import (
        MAX_LIST_FILES_LLM_ENTRIES,
        _list_files,
    )

    monkeypatch.chdir(tmp_path)
    for i in range(MAX_LIST_FILES_LLM_ENTRIES + 10):
        (tmp_path / f"f{i}.txt").write_text("x")

    ctx = MagicMock(spec=RunContext)
    result = _list_files(ctx, str(tmp_path), recursive=False)
    lines = result.content.splitlines()
    # The result should not contain more entries than the cap plus header/summary lines
    assert len(lines) < MAX_LIST_FILES_LLM_ENTRIES + 20


def test_list_files_denies_sensitive_directory(tmp_path, monkeypatch):
    from code_puppy.tools.file_operations import _list_files

    monkeypatch.chdir(tmp_path)
    ctx = MagicMock(spec=RunContext)
    result = _list_files(ctx, str(tmp_path / ".ssh"), recursive=False)
    assert result.error is not None
    assert "sensitive" in result.error.lower() or "policy" in result.error.lower()


def test_read_huge_file_rejected_before_full_read(tmp_path, monkeypatch):
    from code_puppy.tools.file_operations import MAX_READ_FILE_BYTES, _read_file

    monkeypatch.chdir(tmp_path)
    huge = tmp_path / "huge.txt"
    huge.write_text("x" * (MAX_READ_FILE_BYTES + 100))

    ctx = MagicMock(spec=RunContext)
    result = _read_file(ctx, str(huge))
    assert result.error is not None
    assert "too large" in result.error.lower() or "chunk" in result.error.lower()


def test_read_huge_file_chunk_allowed(tmp_path, monkeypatch):
    from code_puppy.tools.file_operations import MAX_READ_FILE_BYTES, _read_file

    monkeypatch.chdir(tmp_path)
    huge = tmp_path / "huge.txt"
    huge.write_text("line\n" * (MAX_READ_FILE_BYTES // 2))

    ctx = MagicMock(spec=RunContext)
    result = _read_file(ctx, str(huge), start_line=1, num_lines=5)
    assert result.error is None
    assert result.content is not None


def test_replace_huge_file_rejected_before_full_read(tmp_path, monkeypatch):
    from code_puppy.tools.file_modifications import (
        MAX_EDIT_FILE_BYTES,
        _replace_in_file,
    )

    monkeypatch.chdir(tmp_path)
    huge = tmp_path / "huge.txt"
    huge.write_text("x" * (MAX_EDIT_FILE_BYTES + 100))

    result = _replace_in_file(
        None,
        str(huge),
        [{"old_str": "x", "new_str": "y"}],
    )
    assert result.get("error") is not None
    assert "too large" in result["error"].lower()


def test_delete_snippet_huge_file_rejected_before_full_read(tmp_path, monkeypatch):
    from code_puppy.tools.file_modifications import (
        MAX_EDIT_FILE_BYTES,
        _delete_snippet_from_file,
    )

    monkeypatch.chdir(tmp_path)
    huge = tmp_path / "huge.txt"
    huge.write_text("x" * (MAX_EDIT_FILE_BYTES + 100))

    result = _delete_snippet_from_file(
        None,
        str(huge),
        "xxx",
    )
    assert result.get("error") is not None
    assert "too large" in result["error"].lower()


def test_diff_output_capped(tmp_path, monkeypatch):
    from code_puppy.tools.file_modifications import MAX_DIFF_BYTES, _write_to_file

    monkeypatch.chdir(tmp_path)
    existing = tmp_path / "big.txt"
    existing.write_text("a\n" * (MAX_DIFF_BYTES // 2))

    result = _write_to_file(
        None,
        str(existing),
        "b\n" * (MAX_DIFF_BYTES // 2),
        overwrite=True,
    )
    diff = result.get("diff", "")
    if len(diff) > MAX_DIFF_BYTES:
        assert "truncated" in diff.lower()
