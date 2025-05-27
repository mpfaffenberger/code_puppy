from unittest.mock import patch, mock_open
from code_puppy.tools.file_modifications import delete_snippet_from_file


def test_delete_snippet_success():
    content = "This is foo text containing the SNIPPET to delete."
    with (
        patch("os.path.exists", return_value=True),
        patch("os.path.isfile", return_value=True),
        patch("builtins.open", mock_open(read_data=content)) as m,
    ):
        # Snippet to delete that is present in the content
        snippet = "SNIPPET"
        # Our write should have the snippet removed
        result = delete_snippet_from_file(None, "dummy_path", snippet)
        assert result.get("success") is True
        assert snippet not in m().write.call_args[0][0]


def test_delete_snippet_file_not_found():
    with patch("os.path.exists", return_value=False):
        res = delete_snippet_from_file(None, "dummy_path", "SNIPPET")
        assert "error" in res


def test_delete_snippet_not_a_file():
    with (
        patch("os.path.exists", return_value=True),
        patch("os.path.isfile", return_value=False),
    ):
        res = delete_snippet_from_file(None, "dummy_path", "FOO")
        assert "error" in res


def test_delete_snippet_snippet_not_found():
    content = "no such snippet here"
    with (
        patch("os.path.exists", return_value=True),
        patch("os.path.isfile", return_value=True),
        patch("builtins.open", mock_open(read_data=content)),
    ):
        res = delete_snippet_from_file(None, "dummy_path", "SNIPPET_NOT_THERE")
        assert "error" in res


def test_delete_snippet_no_changes():
    # The same as 'snippet not found', it should early return
    content = "no match"
    with (
        patch("os.path.exists", return_value=True),
        patch("os.path.isfile", return_value=True),
        patch("builtins.open", mock_open(read_data=content)),
    ):
        res = delete_snippet_from_file(None, "dummy_path", "notfound")
        # Should return error as per actual code
        assert "error" in res
        assert "Snippet not found" in res["error"]


def test_delete_snippet_permission_error():
    with (
        patch("os.path.exists", return_value=True),
        patch("os.path.isfile", return_value=True),
        patch("builtins.open", side_effect=PermissionError("DENIED")),
    ):
        res = delete_snippet_from_file(None, "dummy_path", "foo")
        assert "error" in res


def test_delete_snippet_filenotfounderror():
    # Even though checked above, simulate FileNotFoundError anyway
    with (
        patch("os.path.exists", return_value=True),
        patch("os.path.isfile", return_value=True),
        patch("builtins.open", side_effect=FileNotFoundError("NO FILE")),
    ):
        res = delete_snippet_from_file(None, "dummy_path", "foo")
        assert "error" in res


def test_delete_snippet_fails_with_unknown_exception():
    with (
        patch("os.path.exists", return_value=True),
        patch("os.path.isfile", return_value=True),
        patch("builtins.open", side_effect=Exception("kaboom")),
    ):
        res = delete_snippet_from_file(None, "dummy_path", "foo")
        assert "error" in res and "kaboom" in res["error"]
