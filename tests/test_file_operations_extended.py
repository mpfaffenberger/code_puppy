import os
import pytest
from unittest.mock import patch, mock_open
from code_agent.tools import file_operations


def test_list_files_non_existent_dir():
    result = file_operations.list_files("/nonexistentpath", recursive=False)
    assert isinstance(result, list)
    assert any("error" in r for r in result)


def test_list_files_not_directory(tmp_path):
    file_path = tmp_path / "file.txt"
    file_path.write_text("hello")
    result = file_operations.list_files(str(file_path))
    assert isinstance(result, list)
    assert any("error" in r for r in result)


def test_create_file_success(tmp_path):
    file_path = tmp_path / "testfile.txt"
    result = file_operations.create_file(str(file_path), "content")
    assert result["success"] is True
    assert result["path"] == str(file_path)
    # Verify file content
    with open(file_path) as f:
        assert f.read() == "content"


def test_create_file_dir_creation_failure(monkeypatch):
    def raise_os_error(*args, **kwargs):
        raise OSError("No permission")

    monkeypatch.setattr(os, "makedirs", raise_os_error)
    result = file_operations.create_file("/protected/path/file.txt", "content")
    assert "error" in result


def test_read_file_binary(monkeypatch, tmp_path):
    file_path = tmp_path / "binaryfile"
    # Write binary content
    with open(file_path, "wb") as f:
        f.write(b"\x00\x01\x02")

    result = file_operations.read_file(str(file_path), 0, 10)
    assert "error" in result


def test_read_file_success(tmp_path):
    file_path = tmp_path / "textfile.txt"
    content = "line1\nline2\nline3"
    file_path.write_text(content)
    result = file_operations.read_file(str(file_path), 1, 3)
    assert result["success"] is True
    assert "content" in result
    assert "line2" in result["content"]
import os
import pytest
from unittest.mock import patch, mock_open
from code_agent.tools import file_operations


def test_list_files_non_existent_dir():
    result = file_operations.list_files("/nonexistentpath", recursive=False)
    assert isinstance(result, list)
    assert any(isinstance(r, dict) and "error" in r for r in result)


def test_list_files_not_directory(tmp_path):
    file_path = tmp_path / "file.txt"
    file_path.write_text("hello")
    result = file_operations.list_files(str(file_path))
    assert isinstance(result, list)
    assert any(isinstance(r, dict) and "error" in r for r in result)


def test_create_file_success(tmp_path):
    file_path = tmp_path / "testfile.txt"
    result = file_operations.create_file(str(file_path), "content")
    assert result["success"] is True
    assert os.path.abspath(result["path"]) == os.path.abspath(str(file_path))
    # Verify file content
    with open(file_path) as f:
        assert f.read() == "content"


def test_create_file_dir_creation_failure(monkeypatch):
    def raise_os_error(*args, **kwargs):
        raise OSError("No permission")

    monkeypatch.setattr(os, "makedirs", raise_os_error)
    result = file_operations.create_file("/protected/path/file.txt", "content")
    assert "error" in result


def test_read_file_binary(monkeypatch, tmp_path):
    file_path = tmp_path / "binaryfile"
    # Write binary content
    with open(file_path, "wb") as f:
        f.write(b"\x00\x01\x02")

    result = file_operations.read_file(str(file_path), 0, 10)
    assert "error" in result


def test_read_file_success(tmp_path):
    file_path = tmp_path / "textfile.txt"
    content = "line1\nline2\nline3"
    file_path.write_text(content)
    result = file_operations.read_file(str(file_path), 1, 3)
    assert result["success"] is True
    assert "content" in result
    assert "line2" in result["content"]
