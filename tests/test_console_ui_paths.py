from code_puppy.tools.command_runner import share_your_reasoning
from code_puppy.tools.file_operations import list_files
from unittest.mock import patch

# This test calls share_your_reasoning with reasoning only


def test_share_your_reasoning_plain():
    out = share_your_reasoning({}, reasoning="I reason with gusto!")
    assert out["success"]


# This triggers tree output for multi-depth directories


def test_list_files_multi_level_tree():
    with (
        patch("os.path.abspath", return_value="/foo"),
        patch("os.path.exists", return_value=True),
        patch("os.path.isdir", return_value=True),
        patch("os.walk") as mwalk,
        patch(
            "code_puppy.tools.file_operations.should_ignore_path", return_value=False
        ),
        patch("os.path.getsize", return_value=99),
    ):
        mwalk.return_value = [
            ("/foo", ["dir1"], ["a.py"]),
            ("/foo/dir1", [], ["b.md", "c.txt"]),
        ]
        results = list_files(None, directory="/foo")
        assert len(results) >= 3  # At least a.py, b.md, c.txt
