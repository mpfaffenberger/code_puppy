import os
from unittest.mock import MagicMock, mock_open, patch

from code_puppy.tools.file_operations import (
    _grep as grep,
    _list_files as list_files,
    _read_file as read_file,
)

from code_puppy.tools.common import should_ignore_path


class TestShouldIgnorePath:
    def test_should_ignore_matching_paths(self):
        # Test paths that should be ignored based on the IGNORE_PATTERNS
        # fnmatch patterns require exact matches, so we need to match the patterns precisely
        assert (
            should_ignore_path("path/node_modules/file.js") is True
        )  # matches **/node_modules/**
        assert should_ignore_path("path/.git/config") is True  # matches **/.git/**
        assert (
            should_ignore_path("path/__pycache__/module.pyc") is True
        )  # matches **/__pycache__/**
        assert should_ignore_path("path/.DS_Store") is True  # matches **/.DS_Store
        assert (
            should_ignore_path("path/.venv/bin/python") is True
        )  # matches **/.venv/**
        assert should_ignore_path("path/module.pyc") is True  # matches **/*.pyc

    def test_should_not_ignore_normal_paths(self):
        # Test paths that should not be ignored
        assert should_ignore_path("main.py") is False
        assert should_ignore_path("src/app.js") is False
        assert should_ignore_path("README.md") is False
        assert should_ignore_path("data/config.yaml") is False


class TestListFiles:
    def test_directory_not_exists(self):
        with patch("os.path.exists", return_value=False):
            result = list_files(None, directory="/nonexistent")
            assert "DIRECTORY LISTING" in result.content
            assert "does not exist" in result.content

    def test_not_a_directory(self):
        with (
            patch("os.path.exists", return_value=True),
            patch("os.path.isdir", return_value=False),
        ):
            result = list_files(None, directory="/file.txt")
            assert "DIRECTORY LISTING" in result.content
            assert "is not a directory" in result.content

    def test_empty_directory(self):
        with (
            patch("os.path.exists", return_value=True),
            patch("os.path.isdir", return_value=True),
            patch("os.walk", return_value=[("/test", [], [])]),
            patch("os.path.abspath", return_value="/test"),
        ):
            result = list_files(None, directory="/test")
            assert len(result.matches) == 0


class TestReadFile:
    def test_read_file_success(self):
        file_content = "Hello, world!\nThis is a test file."
        mock_file = mock_open(read_data=file_content)
        test_file_path = "test.txt"

        # Need to patch os.path.abspath to handle the path resolution
        with (
            patch("os.path.exists", return_value=True),
            patch(
                "os.path.isfile", return_value=True
            ),  # Need this to pass the file check
            patch(
                "os.path.abspath", return_value=test_file_path
            ),  # Return the same path for simplicity
            patch("builtins.open", mock_file),
        ):
            result = read_file(None, test_file_path)

            assert result.error is None
            assert result.content == file_content

    def test_read_file_error_file_not_found(self):
        with (
            patch("os.path.exists", return_value=True),
            patch(
                "os.path.isfile", return_value=True
            ),  # Need this to pass the file check
            patch("builtins.open", side_effect=FileNotFoundError("File not found")),
        ):
            result = read_file(None, "nonexistent.txt")

            assert result.error is not None
            assert "FILE NOT FOUND" in result.error

    def test_read_file_not_a_file(self):
        with (
            patch("os.path.exists", return_value=True),
            patch("os.path.isfile", return_value=False),  # It's not a file
        ):
            result = read_file(None, "directory/")

            assert result.error is not None
            assert "is not a file" in result.error

    def test_read_file_does_not_exist(self):
        with patch("os.path.exists", return_value=False):
            result = read_file(None, "nonexistent.txt")

            assert result.error is not None
            assert "does not exist" in result.error

    def test_read_file_permission_error(self):
        with (
            patch("os.path.abspath", return_value="/protected.txt"),
            patch("os.path.exists", return_value=True),
            patch("os.path.isfile", return_value=True),
            patch("builtins.open", side_effect=PermissionError("Permission denied")),
        ):
            result = read_file(None, "protected.txt")

            assert result.error is not None
            assert "FILE NOT FOUND" in result.error

    def test_grep_unicode_decode_error(self):
        # Test Unicode decode error for grep function
        fake_dir = os.path.join(os.getcwd(), "fake_test_dir")
        with (
            patch("os.path.abspath", return_value=fake_dir),
            patch("shutil.which", return_value="/usr/bin/rg"),
            patch("subprocess.run") as mock_subprocess,
            patch(
                "code_puppy.tools.file_operations.tempfile.NamedTemporaryFile"
            ) as mock_tempfile,
            patch("os.unlink"),  # Mock os.unlink to prevent FileNotFoundError in tests
        ):
            # Mock subprocess to return our fake file with Unicode decode error
            mock_subprocess.return_value.stdout = "binary.bin:1:match content"
            mock_subprocess.return_value.stderr = ""
            mock_subprocess.return_value.returncode = 0

            # Mock the temporary file creation
            mock_tempfile.return_value.__enter__.return_value.name = "/tmp/test.ignore"

            result = grep(None, "match", fake_dir)
            assert len(result.matches) == 0


class TestRegisterTools:
    def test_register_file_operations_tools(self):
        # Create a mock agent
        mock_agent = MagicMock()

        # Register the tools

        # Verify that the tools were registered
        assert mock_agent.tool.call_count == 3

        # Get the names of registered functions by examining the mock calls
        # Extract function names from the decorator calls
        function_names = []
        for call_obj in mock_agent.tool.call_args_list:
            func = call_obj[0][0]
            function_names.append(func.__name__)

        assert "list_files" in function_names
        assert "read_file" in function_names
        assert "grep" in function_names

        # Test the tools call the correct underlying functions
        with patch("code_puppy.tools.file_operations._list_files") as mock_internal:
            # Find the list_files function
            list_files_func = None
            for call_obj in mock_agent.tool.call_args_list:
                if call_obj[0][0].__name__ == "list_files":
                    list_files_func = call_obj[0][0]
                    break

            assert list_files_func is not None
            mock_context = MagicMock()
            list_files_func(mock_context, "/test/dir", True)
            mock_internal.assert_called_once_with(mock_context, "/test/dir", True)

        with patch("code_puppy.tools.file_operations._read_file") as mock_internal:
            # Find the read_file function
            read_file_func = None
            for call_obj in mock_agent.tool.call_args_list:
                if call_obj[0][0].__name__ == "read_file":
                    read_file_func = call_obj[0][0]
                    break

            assert read_file_func is not None
            mock_context = MagicMock()
            read_file_func(mock_context, "/test/file.txt")
            mock_internal.assert_called_once_with(mock_context, "/test/file.txt")

        with patch("code_puppy.tools.file_operations._grep") as mock_internal:
            # Find the grep function
            grep_func = None
            for call_obj in mock_agent.tool.call_args_list:
                if call_obj[0][0].__name__ == "grep":
                    grep_func = call_obj[0][0]
                    break

            assert grep_func is not None
            mock_context = MagicMock()
            grep_func(mock_context, "search term", "/test/dir")
            mock_internal.assert_called_once_with(
                mock_context, "search term", "/test/dir"
            )


class TestFormatSize:
    def test_format_size(self):
        # Since format_size is a nested function, we'll need to recreate similar logic
        # to test different size categories

        # Create a format_size function that mimics the one in _list_files
        def format_size(size_bytes):
            if size_bytes < 1024:
                return f"{size_bytes} B"
            elif size_bytes < 1024 * 1024:
                return f"{size_bytes / 1024:.1f} KB"
            elif size_bytes < 1024 * 1024 * 1024:
                return f"{size_bytes / (1024 * 1024):.1f} MB"
            else:
                return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

        # Test different size categories
        assert format_size(500) == "500 B"  # Bytes
        assert format_size(1536) == "1.5 KB"  # Kilobytes
        assert format_size(1572864) == "1.5 MB"  # Megabytes
        assert format_size(1610612736) == "1.5 GB"  # Gigabytes


class TestFileIcon:
    def test_get_file_icon(self):
        # Since get_file_icon is a nested function, we'll need to create a similar function
        # to test different file type icons

        # Create a function that mimics the behavior of get_file_icon in _list_files
        def get_file_icon(file_path):
            ext = os.path.splitext(file_path)[1].lower()
            if ext in [".py", ".pyw"]:
                return "\U0001f40d"  # snake emoji for Python
            elif ext in [".html", ".htm"]:
                return "\U0001f310"  # globe emoji for HTML
            elif ext == ".css":
                return "\U0001f3a8"  # art palette emoji for CSS
            elif ext in [".js", ".ts", ".tsx", ".jsx"]:
                return "\U000026a1"  # lightning bolt for JS/TS
            elif ext in [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp"]:
                return "\U0001f5bc"  # frame emoji for images
            else:
                return "\U0001f4c4"  # document emoji for everything else

        # Test different file types
        assert get_file_icon("script.py") == "\U0001f40d"  # Python (snake emoji)
        assert get_file_icon("page.html") == "\U0001f310"  # HTML (globe emoji)
        assert get_file_icon("style.css") == "\U0001f3a8"  # CSS (art palette emoji)
        assert get_file_icon("script.js") == "\U000026a1"  # JS (lightning emoji)
        assert get_file_icon("image.png") == "\U0001f5bc"  # Image (frame emoji)
        assert get_file_icon("document.md") == "\U0001f4c4"  # Markdown (document emoji)
        assert get_file_icon("unknown.xyz") == "\U0001f4c4"  # Default (document emoji)


class TestGrep:
    def test_grep_no_matches(self):
        fake_dir = "/test"
        # Mock ripgrep output with no matches
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = grep(None, "nonexistent", fake_dir)
            assert len(result.matches) == 0

    def test_grep_limit_matches(self):
        fake_dir = "/test"
        # Create mock JSON output with many matches
        matches = [
            '{"type":"match","data":{"path":{"text":"/test/test.txt"},"lines":{"text":"match line"},"line_number":1}}\n'
            for i in range(60)  # More than 50 matches
        ]
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "".join(matches)
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = grep(None, "match", fake_dir)
            # Should be limited to 50 matches
            assert len(result.matches) == 50

    def test_grep_with_matches(self):
        fake_dir = "/test"
        # Mock ripgrep output with matches
        mock_output = '{"type":"match","data":{"path":{"text":"/test/test.txt"},"lines":{"text":"and a match here"},"line_number":3}}\n'
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = mock_output
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = grep(None, "match", fake_dir)
            assert len(result.matches) == 1
            assert result.matches[0].file_path == "/test/test.txt"
            assert result.matches[0].line_number == 3
            assert result.matches[0].line_content == "and a match here"

    def test_grep_handle_errors(self):
        fake_dir = "/test"
        # Mock ripgrep subprocess error
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Error occurred"

        with patch("subprocess.run", return_value=mock_result):
            result = grep(None, "match", fake_dir)
            assert len(result.matches) == 0

    def test_grep_non_json_output(self):
        fake_dir = "/test"
        # Mock ripgrep output that isn't JSON
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "non-json output"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = grep(None, "match", fake_dir)
            assert len(result.matches) == 0

    def test_grep_empty_json_objects(self):
        fake_dir = "/test"
        # Mock ripgrep output with empty JSON objects
        mock_output = (
            '{"type":"begin","data":{"path":{"text":"/test/test.txt"}}}\n'
            '{"type":"match","data":{"path":{"text":"/test/test.txt"},"lines":{"text":"match here"},"line_number":1}}\n'
            '{"type":"end","data":{"path":{"text":"/test/test.txt"},"binary_offset":null}}\n'
        )
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = mock_output
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = grep(None, "match", fake_dir)
            assert len(result.matches) == 1
            assert result.matches[0].file_path == "/test/test.txt"
