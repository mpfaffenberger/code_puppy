from unittest.mock import patch, mock_open
from code_puppy.agent import get_code_generation_agent


def test_create_file():
    agent = get_code_generation_agent()
    test_file = "test_create.txt"
    m = mock_open()
    with (
        patch("os.path.exists") as mock_exists,
        patch("builtins.open", m),
        patch("os.makedirs") as mock_makedirs,
    ):

        def side_effect(path):
            if path == test_file or path.endswith(test_file):
                return False
            else:
                return True

        mock_exists.side_effect = side_effect
        mock_makedirs.return_value = None
        result = agent.tools["edit_file"](None, test_file, "content")
        assert "success" in result
        assert result["success"] is True
        assert result["path"].endswith(test_file)


def test_read_file():
    agent = get_code_generation_agent()
    test_file = "test_read.txt"
    m = mock_open(read_data="line1\nline2\nline3")
    with (
        patch("os.path.exists") as mock_exists,
        patch("os.path.isfile") as mock_isfile,
        patch("builtins.open", m),
    ):
        mock_exists.return_value = True
        mock_isfile.return_value = True
        result = agent.tools["read_file"](None, test_file)
        assert "content" in result


def test_list_files_permission_error_on_getsize(tmp_path):
    agent = get_code_generation_agent()
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
        result = agent.tools["list_files"](None, directory=str(fake_dir))
        assert all(f["type"] != "file" or f["path"] != "file.txt" for f in result)
