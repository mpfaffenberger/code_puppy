import os
from unittest.mock import patch
from code_puppy.tools.file_operations import list_files, create_file, read_file

def test_create_file():
    test_file = "test_create.txt"
    with patch('os.path.exists') as mock_exists, patch('os.makedirs') as mock_makedirs, patch('builtins.open', new_callable=lambda *args, **kwargs: open(os.devnull, 'w')) as mock_file:
        mock_exists.return_value = False
        result = create_file(None, test_file, "content")
        assert result["success"]
        assert result["path"].endswith(test_file)

def test_read_file():
    test_file = "test_read.txt"
    with patch('os.path.exists') as mock_exists, patch('os.path.isfile') as mock_isfile, patch('builtins.open', new_callable=lambda *args, **kwargs: open(os.devnull, 'r')) as mock_file:
        mock_exists.return_value = True
        mock_isfile.return_value = True
        mock_file.return_value.read.return_value = "line1\nline2\nline3"
        result = read_file(None, test_file)
        assert "content" in result


def test_list_files():
    with patch('os.path.abspath') as mock_abspath, \
         patch('os.path.exists') as mock_exists, \
         patch('os.path.isdir') as mock_isdir, \
         patch('os.walk') as mock_walk, \
         patch('os.path.getsize') as mock_getsize:
        mock_abspath.return_value = '/test'
        mock_exists.return_value = True
        mock_isdir.return_value = True
        mock_walk.return_value = [('/test', ['dir'], ['file.txt'])]
        mock_getsize.return_value = 123
        result = list_files(None, directory="/test", recursive=True)
        assert len(result) > 0

def test_list_files_nonexistent_dir():
    with patch("os.path.exists", return_value=False):
        result = list_files(directory="nope")
        assert result[0]["error"] == "Directory 'nope' does not exist"


def test_list_files_not_a_directory():
    with patch("os.path.exists", return_value=True), patch("os.path.isdir", return_value=False):
        result = list_files(directory="fakefile")
        assert result[0]["error"].startswith("'fakefile' is not a directory")


def test_list_files_permission_error_on_getsize(tmp_path):
    # Create a directory and pretend a file exists, but getsize fails
    fake_dir = tmp_path
    fake_file = fake_dir / "file.txt"
    fake_file.write_text("hello")
    with patch("os.path.exists", return_value=True), patch("os.path.isdir", return_value=True), \
         patch("os.walk", return_value=[(str(fake_dir), [], ["file.txt"])]), \
         patch("code_puppy.tools.file_operations.should_ignore_path", return_value=False), \
         patch("os.path.getsize", side_effect=PermissionError):
        result = list_files(directory=str(fake_dir))
        # Should not throw, just quietly ignore
        assert all(f["type"] != "file" or f["path"] != "file.txt" for f in result)


def test_list_files_nonexistent_dir():
    with patch("os.path.exists", return_value=False):
        abs_path = os.path.abspath("nope")
        result = list_files(None, directory="nope")
        assert result[0]["error"] == f"Directory '{abs_path}' does not exist"


def test_list_files_not_a_directory():
    with patch("os.path.exists", return_value=True), patch("os.path.isdir", return_value=False):
        abs_path = os.path.abspath("fakefile")
        result = list_files(None, directory="fakefile")
        assert result[0]["error"].startswith(f"'{abs_path}' is not a directory")
