#!/usr/bin/env python3
"""Upload a large video (or any big binary) as a GitHub Release asset.

GitHub's drag-and-drop in a PR/issue description caps videos at ~10 MB.
Release assets allow up to 2 GB per file, so this script parks your file on
a release and prints a paste-ready URL that GitHub renders as an inline
video player inside the PR body.

Requires the GitHub CLI (`gh`) to be installed and authenticated:
    gh auth status   # if it errors -> gh auth login

Examples:
    python scripts/upload_pr_video.py demo.mp4
    python scripts/upload_pr_video.py demo.mp4 --tag pr-1234-assets
    python scripts/upload_pr_video.py demo.mp4 --repo owner/name --dry-run
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

# Releases allow up to 2 GB per asset; warn (don't block) above this.
GITHUB_RELEASE_ASSET_LIMIT_BYTES = 2 * 1024 * 1024 * 1024
DEFAULT_TAG = "demo-assets"


def _fail(message: str) -> NoReturn:
    """Print an error and exit non-zero. One place for all hard stops (DRY)."""
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def _run(cmd: list[str], *, dry_run: bool = False) -> subprocess.CompletedProcess:
    """Run a command, echoing it first. Fail gracefully on non-zero exit."""
    printable = " ".join(cmd)
    if dry_run:
        print(f"[dry-run] would run: {printable}")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    print(f"$ {printable}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.returncode != 0:
        _fail(result.stderr.strip() or f"command failed: {printable}")
    return result


def _require_gh() -> None:
    """Make sure the gh CLI exists and is authenticated."""
    if shutil.which("gh") is None:
        _fail(
            "the GitHub CLI (`gh`) is not installed. "
            "Install it from https://cli.github.com/ and run `gh auth login`."
        )
    auth = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
    if auth.returncode != 0:
        _fail("gh is not authenticated. Run `gh auth login` and try again.")


def _detect_repo() -> str:
    """Ask gh for the current repo as owner/name."""
    result = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        capture_output=True,
        text=True,
    )
    repo = result.stdout.strip()
    if result.returncode != 0 or not repo:
        _fail(
            "could not auto-detect the repo. Run this from inside a git repo "
            "or pass --repo owner/name."
        )
    return repo


def _validate_file(path: Path) -> None:
    """Check the asset exists, is a file, and warn if it's over the limit."""
    if not path.exists():
        _fail(f"file not found: {path}")
    if not path.is_file():
        _fail(f"not a file: {path}")
    size = path.stat().st_size
    if size > GITHUB_RELEASE_ASSET_LIMIT_BYTES:
        print(
            f"warning: {path.name} is {size / 1e9:.2f} GB, which exceeds "
            "GitHub's 2 GB release-asset limit. Upload will likely fail.",
            file=sys.stderr,
        )


def _release_exists(tag: str, repo: str) -> bool:
    """True if a release with this tag already exists."""
    result = subprocess.run(
        ["gh", "release", "view", tag, "--repo", repo],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _ensure_release(tag: str, repo: str, target: str, dry_run: bool) -> None:
    """Create the holding release if it doesn't already exist."""
    # Dry-run is side-effect free: don't probe gh, just show the create command.
    if not dry_run and _release_exists(tag, repo):
        print(f"release '{tag}' already exists -- reusing it.")
        return
    _run(
        [
            "gh",
            "release",
            "create",
            tag,
            "--repo",
            repo,
            "--title",
            "Demo assets",
            "--notes",
            "Video/binary assets for PR demos.",
            "--target",
            target,
        ],
        dry_run=dry_run,
    )


def _upload_asset(path: Path, tag: str, repo: str, dry_run: bool) -> None:
    """Upload (or overwrite) the asset on the release."""
    _run(
        ["gh", "release", "upload", tag, str(path), "--repo", repo, "--clobber"],
        dry_run=dry_run,
    )


def _asset_url(repo: str, tag: str, filename: str) -> str:
    return f"https://github.com/{repo}/releases/download/{tag}/{filename}"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload a big video as a GitHub Release asset for a PR.",
    )
    parser.add_argument("file", type=Path, help="Path to the video/binary to upload.")
    parser.add_argument(
        "--repo",
        default=None,
        help="Target repo as owner/name (default: auto-detect from cwd).",
    )
    parser.add_argument(
        "--tag",
        default=DEFAULT_TAG,
        help=f"Release tag to hold the asset (default: {DEFAULT_TAG}).",
    )
    parser.add_argument(
        "--target",
        default="main",
        help="Branch/commit the release points at (default: main).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the commands without executing them.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    # In dry-run we only print intended commands, so skip the live gh checks.
    if not args.dry_run:
        _require_gh()
    _validate_file(args.file)
    repo = args.repo or _detect_repo()

    _ensure_release(args.tag, repo, args.target, args.dry_run)
    _upload_asset(args.file, args.tag, repo, args.dry_run)

    url = _asset_url(repo, args.tag, args.file.name)
    print("\nDone! Paste this on its own line in your PR description:\n")
    print(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
