from unittest.mock import patch, mock_open
from code_puppy.tools.file_operations import list_files, create_file, read_file


def test_create_file():
    test_file = "test_create.txt"
    m = mock_open()
    with (
        patch("os.path.exists") as mock_exists,
        patch("builtins.open", m),
    ):
        mock_exists.return_value = False
        result = create_file(None, test_file, "content")
        assert "success" in result
        assert result["success"]
        assert result["path"].endswith(test_file)


def test_read_file():
    test_file = "test_read.txt"
    m = mock_open(read_data="line1\nline2\nline3")
    with (
        patch("os.path.exists") as mock_exists,
        patch("os.path.isfile") as mock_isfile,
        patch("builtins.open", m),
    ):
        mock_exists.return_value = True
        mock_isfile.return_value = True
        result = read_file(None, test_file)
        assert "content" in result


def test_list_files_permission_error_on_getsize(tmp_path):
    # Create a directory and pretend a file exists, but getsize fails
    fake_dir = tmp_path
    fake_file = fake_dir / "file.txt"
    fake_file.write_text("hello")
    with (
        patch("os.path.exists", return_value=True),
        patch("os.path.isdir", return_value=True),
        patch("os.walk", return_value=[(str(fake_dir), [], ["file.txt"])]),
        patch(
            "code_puppy.tools.file_operations.should_ignore_path", return_value=False
        ),
        patch("os.path.getsize", side_effect=PermissionError),
    ):
        result = list_files(None, directory=str(fake_dir))
        # Should not throw, just quietly ignore
        assert all(f["type"] != "file" or f["path"] != "file.txt" for f in result)
