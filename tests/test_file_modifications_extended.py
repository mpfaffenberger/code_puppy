import os
import pytest
from unittest.mock import patch, mock_open
from code_agent.tools import file_modifications

# We will test modify_file and delete_file

def test_modify_file_target_not_found(tmp_path):
    file_path = tmp_path / "foo.txt"
    file_path.write_text("hello world")
    result = file_modifications.modify_file(
        str(file_path),
        proposed_changes="goodbye",
        target_content="not found"
    )
    assert "error" in result


def test_modify_file_no_change(tmp_path):
    file_path = tmp_path / "foo.txt"
    file_path.write_text("hello world")
    result = file_modifications.modify_file(
        str(file_path),
        proposed_changes="hello world",
        target_content=None
    )
    assert result["changed"] is False


def test_modify_file_success(tmp_path):
    file_path = tmp_path / "foo.txt"
    file_path.write_text("hello world")
    result = file_modifications.modify_file(
        str(file_path),
        proposed_changes="goodbye world",
        target_content="hello world"
    )
    assert result["changed"] is True
    # The file content should be updated
    with open(file_path) as f:
        content = f.read()
        assert "goodbye world" in content


def test_delete_file_success(tmp_path):
    file_path = tmp_path / "foo.txt"
    file_path.write_text("hello world")
    result = file_modifications.delete_file(str(file_path))
    assert result["success"] is True
    assert not file_path.exists()


def test_delete_file_nonexistent(tmp_path):
    file_path = tmp_path / "nonexistent.txt"
    result = file_modifications.delete_file(str(file_path))
    assert result["success"] is False
    assert "error" in result


def test_modify_file_binary(tmp_path):
    file_path = tmp_path / "binary"
    with open(file_path, "wb") as f:
        f.write(b"\x00\x01\x02")

    result = file_modifications.modify_file(
        str(file_path), "new content"
    )
    assert "error" in result

import os
import pytest
from unittest.mock import patch, mock_open
from code_agent.tools import file_modifications

# We will test modify_file and delete_file

def test_modify_file_target_not_found(tmp_path):
    file_path = tmp_path / "foo.txt"
    file_path.write_text("hello world")
    result = file_modifications.modify_file(
        file_path=str(file_path),
        proposed_changes="goodbye",
        target_content="not found"
    )
    assert "error" in result


def test_modify_file_no_change(tmp_path):
    file_path = tmp_path / "foo.txt"
    file_path.write_text("hello world")
    result = file_modifications.modify_file(
        file_path=str(file_path),
        proposed_changes="hello world",
        target_content=None
    )
    assert result["changed"] is False


def test_modify_file_success(tmp_path):
    file_path = tmp_path / "foo.txt"
    file_path.write_text("hello world")
    result = file_modifications.modify_file(
        file_path=str(file_path),
        proposed_changes="goodbye world",
        target_content="hello world"
    )
    assert result["changed"] is True
    # The file content should be updated
    with open(file_path) as f:
        content = f.read()
        assert "goodbye world" in content


def test_delete_file_success(tmp_path):
    file_path = tmp_path / "foo.txt"
    file_path.write_text("hello world")
    result = file_modifications.delete_file(file_path=str(file_path))
    assert result["success"] is True
    assert not file_path.exists()


def test_delete_file_nonexistent(tmp_path):
    file_path = tmp_path / "nonexistent.txt"
    result = file_modifications.delete_file(file_path=str(file_path))
    assert result["success"] is False
    assert "error" in result


def test_modify_file_binary(tmp_path):
    file_path = tmp_path / "binary"
    with open(file_path, "wb") as f:
        f.write(b"\x00\x01\x02")

    result = file_modifications.modify_file(
        file_path=str(file_path), proposed_changes="new content"
    )
    assert "error" in result

