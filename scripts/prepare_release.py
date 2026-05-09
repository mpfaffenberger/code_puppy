#!/usr/bin/env python3
"""Prepare package metadata for a PyPI release."""

from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path


PACKAGE_NAME = "fast-puppy"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"
LOCK_PATH = PROJECT_ROOT / "uv.lock"
VERSION_RE = re.compile(
    r"""
    v?
    (?P<version>
      (?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)
      (?:
        (?:a|b|rc)(?:0|[1-9]\d*) |
        \.post(?:0|[1-9]\d*) |
        \.dev(?:0|[1-9]\d*)
      )?
    )
    """,
    re.VERBOSE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Update pyproject.toml and uv.lock for a new release."
    )
    parser.add_argument("version", help="Release version, for example 0.1.2 or v0.1.2")
    parser.add_argument(
        "--skip-pypi-check",
        action="store_true",
        help="Do not check whether this version already exists on PyPI.",
    )
    return parser.parse_args()


def normalize_version(raw_version: str) -> str:
    match = VERSION_RE.fullmatch(raw_version.strip())
    if not match:
        raise SystemExit(
            "Version must look like 0.1.2, v0.1.2, 0.1.2rc1, "
            "0.1.2.post1, or 0.1.2.dev1."
        )
    return match.group("version")


def ensure_version_available(version: str) -> None:
    url = f"https://pypi.org/pypi/{PACKAGE_NAME}/{version}/json"
    request = urllib.request.Request(url, headers={"User-Agent": "fast-puppy-release"})

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            status = response.status
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return
        raise SystemExit(
            f"Unexpected PyPI response for {version}: HTTP {exc.code}"
        ) from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Could not check PyPI for {version}: {exc.reason}") from exc

    if status == 200:
        raise SystemExit(f"{PACKAGE_NAME} {version} already exists on PyPI.")
    raise SystemExit(f"Unexpected PyPI response for {version}: HTTP {status}")


def update_pyproject(version: str) -> None:
    lines = PYPROJECT_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
    in_project = False

    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "[project]":
            in_project = True
            continue
        if in_project and stripped.startswith("[") and stripped.endswith("]"):
            break
        if in_project and stripped.startswith("version"):
            newline = "\n" if line.endswith("\n") else ""
            lines[index] = f'version = "{version}"{newline}'
            PYPROJECT_PATH.write_text("".join(lines), encoding="utf-8")
            return

    raise SystemExit("Could not find [project] version in pyproject.toml.")


def update_lock(version: str) -> None:
    lines = LOCK_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
    in_package = False
    package_name: str | None = None

    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "[[package]]":
            in_package = True
            package_name = None
            continue
        if in_package and stripped.startswith("[") and stripped != "[[package]]":
            in_package = False
            package_name = None
            continue
        if in_package and stripped.startswith("name = "):
            package_name = stripped.partition("=")[2].strip().strip('"')
            continue
        if (
            in_package
            and package_name == PACKAGE_NAME
            and stripped.startswith("version = ")
        ):
            newline = "\n" if line.endswith("\n") else ""
            lines[index] = f'version = "{version}"{newline}'
            LOCK_PATH.write_text("".join(lines), encoding="utf-8")
            return

    raise SystemExit(f"Could not find {PACKAGE_NAME} version in uv.lock.")


def main() -> int:
    args = parse_args()
    version = normalize_version(args.version)

    if not args.skip_pypi_check:
        ensure_version_available(version)

    update_pyproject(version)
    update_lock(version)

    print(f"Prepared {PACKAGE_NAME} {version}.")
    print()
    print("Next steps:")
    print("  uv lock --check")
    print("  uv run ruff check --fix")
    print("  uv run ruff format .")
    print("  uv build")
    print(f'  git add pyproject.toml uv.lock && git commit -m "Release {version}"')
    print("  git push origin main")
    print(f"  git tag v{version}")
    print(f"  git push origin v{version}")
    print(f"  Publish a GitHub Release for tag v{version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
