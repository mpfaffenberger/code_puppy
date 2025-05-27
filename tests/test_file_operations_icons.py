from code_puppy.tools.file_operations import list_files
from unittest.mock import patch

all_types = [
    "main.py",
    "frontend.js",
    "component.tsx",
    "layout.html",
    "styles.css",
    "README.md",
    "config.yaml",
    "image.png",
    "music.mp3",
    "movie.mp4",
    "report.pdf",
    "archive.zip",
    "binary.exe",
    "oddfile.unknown",
]


def test_list_files_get_file_icon_full_coverage():
    fake_entries = [("/repo", [], all_types)]
    with (
        patch("os.path.abspath", return_value="/repo"),
        patch("os.path.exists", return_value=True),
        patch("os.path.isdir", return_value=True),
        patch("os.walk", return_value=fake_entries),
        patch(
            "code_puppy.tools.file_operations.should_ignore_path", return_value=False
        ),
        patch("os.path.getsize", return_value=420),
    ):
        results = list_files(None, directory="/repo")
        paths = set(f["path"] for f in results)
        for p in all_types:
            assert p in paths
