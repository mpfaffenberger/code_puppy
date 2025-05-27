import pytest
from unittest.mock import patch, mock_open
from code_agent.tools.file_modifications import modify_file, delete_file

# Clean, deduplicated file. All relevant modify_file calls receive (ctx, path, proposed, replace_content)
def test_modify_file_append():
    with patch("os.path.exists", return_value=True), patch("builtins.open", mock_open(read_data="Original content")) as mock_file:
        result = modify_file(None, "dummy_path", " New content", "Original content")
        assert result.get("success")
        assert "New content" in mock_file().write.call_args[0][0]

def test_modify_file_target_replace():
    original_content = "Original content"
    target_content = "Original"
    proposed_content = "Modified"
    with patch("os.path.exists", return_value=True), patch("builtins.open", mock_open(read_data=original_content)) as mock_file:
        result = modify_file(None, "dummy_path", proposed_content, target_content)
        assert result.get("success")
        assert proposed_content in mock_file().write.call_args[0][0]

def test_modify_file_not_found():
    with patch("os.path.exists", return_value=False):
        result = modify_file(None, "dummy_path", "content", "content")
        assert "error" in result

def test_modify_file_no_changes():
    original_content = "Original content"
    with patch("os.path.exists", return_value=True), patch("builtins.open", mock_open(read_data=original_content)):
        result = modify_file(None, "dummy_path", original_content, original_content)
        assert not result.get("changed")
        assert result.get("message") == "No changes to apply."

@pytest.mark.parametrize("file_exists", [True, False])
def test_modify_file_file_not_exist(file_exists):
    with patch("os.path.exists", return_value=file_exists):
        if not file_exists:
            result = modify_file(None, "dummy_path", "content", "content")
            assert "error" in result
        else:
            with patch("builtins.open", mock_open(read_data="Original content")) as mock_file:
                result = modify_file(None, "dummy_path", " New content", "Original content")
                assert result.get("success")
                assert "New content" in mock_file().write.call_args[0][0]

def test_modify_file_file_is_directory():
    with patch("os.path.exists", return_value=True), patch("os.path.isdir", return_value=True):
        result = modify_file(None, "dummy_path", "some change", "some change")
        assert result["message"].startswith("No changes needed for")
        assert not result["changed"]

def test_delete_file_success():
    with patch("os.path.exists", return_value=True), \
         patch("os.path.isfile", return_value=True), \
         patch("os.remove") as mock_remove:
        result = delete_file(None, "dummy_path")
        assert result.get("success")
        mock_remove.assert_called()

def test_delete_file_not_exist():
    with patch("os.path.exists", return_value=False):
        result = delete_file(None, "dummy_path")
        assert "error" in result

def test_delete_file_permission_error():
    with patch("os.path.exists", return_value=True), \
         patch("os.path.isfile", return_value=True), \
         patch("os.remove", side_effect=PermissionError("Permission denied")):
        result = delete_file(None, "dummy_path")
        assert "error" in result and "Permission denied" in result["error"]

def test_delete_file_not_file():
    with patch("os.path.exists", return_value=True), \
         patch("os.path.isfile", return_value=False):
        result = delete_file(None, "dummy_path")
        assert "error" in result

def test_modify_file_unicode_decode_error():
    with patch("os.path.exists", return_value=True):
        with patch("builtins.open", side_effect=UnicodeDecodeError("utf8", b"", 0, 1, "fail")):
            result = modify_file(None, "dummy_path", "new", "target")
            assert "error" in result and "binary" in result["error"]

def test_modify_file_generic_exception():
    with patch("os.path.exists", return_value=True):
        with patch("builtins.open", side_effect=Exception("kaboom")):
            result = modify_file(None, "dummy_path", "new", "target")
            assert "error" in result and "kaboom" in result["error"]
