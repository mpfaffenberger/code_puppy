"""Tests for scripts/upload_pr_video.py.

The script lives under scripts/ (a dev tool, not part of the shipped
code_puppy package), so we load it by path via importlib.
"""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "upload_pr_video.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("upload_pr_video", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


upload_pr_video = _load_module()


# --- parse_args ------------------------------------------------------------


def test_parse_args_defaults():
    args = upload_pr_video.parse_args(["demo.mp4"])
    assert args.file == Path("demo.mp4")
    assert args.repo is None
    assert args.tag == upload_pr_video.DEFAULT_TAG
    assert args.target == "main"
    assert args.dry_run is False


def test_parse_args_overrides():
    args = upload_pr_video.parse_args(
        [
            "clip.mov",
            "--repo",
            "owner/name",
            "--tag",
            "pr-42",
            "--target",
            "dev",
            "--dry-run",
        ]
    )
    assert args.file == Path("clip.mov")
    assert args.repo == "owner/name"
    assert args.tag == "pr-42"
    assert args.target == "dev"
    assert args.dry_run is True


def test_parse_args_requires_file():
    with pytest.raises(SystemExit):
        upload_pr_video.parse_args([])


# --- _asset_url ------------------------------------------------------------


def test_asset_url_builds_release_download_link():
    url = upload_pr_video._asset_url("owner/name", "demo-assets", "demo.mp4")
    assert url == "https://github.com/owner/name/releases/download/demo-assets/demo.mp4"


# --- _validate_file --------------------------------------------------------


def test_validate_file_missing_exits(tmp_path):
    with pytest.raises(SystemExit):
        upload_pr_video._validate_file(tmp_path / "nope.mp4")


def test_validate_file_directory_exits(tmp_path):
    with pytest.raises(SystemExit):
        upload_pr_video._validate_file(tmp_path)


def test_validate_file_ok(tmp_path):
    f = tmp_path / "ok.mp4"
    f.write_bytes(b"data")
    # Should not raise for a normal, existing file.
    upload_pr_video._validate_file(f)


def test_validate_file_oversize_warns(tmp_path, monkeypatch, capsys):
    f = tmp_path / "big.mp4"
    f.write_bytes(b"x")

    # Shrink the limit so any non-empty file trips the oversize warning.
    monkeypatch.setattr(upload_pr_video, "GITHUB_RELEASE_ASSET_LIMIT_BYTES", 0)
    upload_pr_video._validate_file(f)  # warns, does not raise
    assert "exceeds" in capsys.readouterr().err


# --- main (dry-run) --------------------------------------------------------


def test_main_dry_run_prints_url(tmp_path, capsys):
    f = tmp_path / "demo.mp4"
    f.write_bytes(b"data")

    rc = upload_pr_video.main(
        [str(f), "--repo", "owner/name", "--tag", "pr-7", "--dry-run"]
    )
    out = capsys.readouterr().out

    assert rc == 0
    assert "[dry-run] would run" in out
    assert "https://github.com/owner/name/releases/download/pr-7/demo.mp4" in out
