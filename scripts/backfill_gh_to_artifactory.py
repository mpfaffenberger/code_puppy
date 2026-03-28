#!/usr/bin/env python3
"""Backfill GitHub releases → Artifactory generic repo.

Downloads every code-puppy wheel release from GitHub Enterprise and uploads
it to the Artifactory generic repo, skipping versions that are already there.

Required env vars:
  GITHUB_ACCESS_KEY or GHE_TOKEN  — GHE personal access token
  TWINE_USERNAME                  — Artifactory user (reposolns in Looper)
  TWINE_PASSWORD                  — Artifactory password / API key
  REPOSOLNS_GENERIC_RELEASE_REPO  — Artifactory base URL, e.g.
                                    https://generic.ci.artifacts.walmart.com/artifactory/genaica-generic-prod-local

Usage:
  python scripts/backfill_gh_to_artifactory.py          # live run
  python scripts/backfill_gh_to_artifactory.py --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import httpx

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_GH_API = "https://gecgithub01.walmart.com/api/v3"
_GH_REPO = "genaica/code-puppy"
_AF_STORAGE = (
    "https://generic.ci.artifacts.walmart.com"
    "/artifactory/api/storage/genaica-generic-prod-local/code-puppy"
)

_GH_TOKEN = (
    os.getenv("GITHUB_ACCESS_KEY")
    or os.getenv("GHE_TOKEN")
    or os.getenv("GITHUB_TOKEN")
    or os.getenv("GITHUB_ACCESS_TOKEN")
)
_AF_USER = os.getenv("TWINE_USERNAME")
_AF_PASS = os.getenv("TWINE_PASSWORD")
_AF_BASE = os.getenv(
    "REPOSOLNS_GENERIC_RELEASE_REPO",
    "https://generic.ci.artifacts.walmart.com/artifactory/genaica-generic-prod-local",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gh_headers() -> dict:
    return {
        "Authorization": f"token {_GH_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "code-puppy-backfill",
    }


def _af_auth() -> tuple[str, str]:
    return (_AF_USER, _AF_PASS)


def _strip_v(version: str) -> str:
    return version.lstrip("v")


def _semver_key(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in _strip_v(v).split("."))
    except ValueError:
        return (0,)


def _check_env() -> None:
    missing = []
    if not _GH_TOKEN:
        missing.append("GITHUB_ACCESS_KEY (or GHE_TOKEN)")
    if not _AF_USER:
        missing.append("TWINE_USERNAME")
    if not _AF_PASS:
        missing.append("TWINE_PASSWORD")
    if missing:
        print("❌ Missing required env vars:")
        for m in missing:
            print(f"   {m}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# GitHub
# ---------------------------------------------------------------------------


def fetch_github_releases(client: httpx.Client) -> list[dict]:
    """Fetch all non-draft GHE releases that have a .whl asset."""
    releases: list[dict] = []
    page = 1
    while True:
        resp = client.get(
            f"{_GH_API}/repos/{_GH_REPO}/releases",
            headers=_gh_headers(),
            params={"per_page": 100, "page": page},
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        releases.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    # Keep only non-draft releases that have a .whl asset
    valid = [
        r for r in releases
        if not r.get("draft")
        and any(a["name"].endswith(".whl") and "code_puppy" in a["name"]
                for a in r.get("assets", []))
    ]
    valid.sort(key=lambda r: _semver_key(r["tag_name"]))
    return valid


def download_asset(client: httpx.Client, asset: dict) -> bytes:
    """Download a GHE release asset (follows redirect to blob storage)."""
    resp = client.get(
        asset["url"],  # API URL — requires auth + Accept: octet-stream
        headers={**_gh_headers(), "Accept": "application/octet-stream"},
        follow_redirects=True,
        timeout=120.0,
    )
    resp.raise_for_status()
    return resp.content


# ---------------------------------------------------------------------------
# Artifactory
# ---------------------------------------------------------------------------


def list_artifactory_versions(client: httpx.Client) -> set[str]:
    """Return the set of versions already in Artifactory (no leading v)."""
    resp = client.get(f"{_AF_STORAGE}/", timeout=15.0)
    if resp.status_code == 404:
        return set()
    resp.raise_for_status()
    children = resp.json().get("children", [])
    return {c["uri"].strip("/") for c in children if c.get("folder")}


def upload_to_artifactory(
    client: httpx.Client,
    version: str,
    filename: str,
    content: bytes,
    dry_run: bool,
) -> None:
    """PUT a file into the Artifactory generic repo."""
    url = f"{_AF_BASE}/code-puppy/{version}/{filename}"
    if dry_run:
        print(f"    [dry-run] PUT {url}  ({len(content):,} bytes)")
        return
    resp = client.put(
        url,
        content=content,
        auth=_af_auth(),
        timeout=120.0,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(
            f"Upload failed: HTTP {resp.status_code}\n{resp.text[:400]}"
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(dry_run: bool) -> None:
    _check_env()

    if dry_run:
        print("🐶 DRY-RUN mode — nothing will be uploaded\n")

    with httpx.Client(verify=False) as client:
        print("📋 Fetching existing Artifactory versions...")
        af_versions = list_artifactory_versions(client)
        print(f"   Already in Artifactory: {sorted(af_versions, key=_semver_key)}\n")

        print("📋 Fetching GitHub releases...")
        gh_releases = fetch_github_releases(client)
        print(f"   Found {len(gh_releases)} releases on GitHub\n")

        to_upload = [
            r for r in gh_releases
            if _strip_v(r["tag_name"]) not in af_versions
        ]
        already_done = len(gh_releases) - len(to_upload)

        print(f"✅ Already uploaded: {already_done}")
        print(f"⬆️  To upload:       {len(to_upload)}")

        if not to_upload:
            print("\n🎉 Nothing to do — Artifactory is fully up to date!")
            return

        print()
        errors: list[str] = []

        for i, release in enumerate(to_upload, 1):
            tag = release["tag_name"]
            ver = _strip_v(tag)
            assets = [
                a for a in release.get("assets", [])
                if a["name"].endswith((".whl", ".tar.gz"))
                and "code_puppy" in a["name"]
            ]
            print(f"[{i}/{len(to_upload)}] {tag}  ({len(assets)} file(s))")

            for asset in assets:
                fname = asset["name"]
                size = asset.get("size", 0)
                print(f"  ↓ Downloading {fname}  ({size:,} bytes)...")
                try:
                    content = download_asset(client, asset)
                    print(f"  ↑ Uploading   {fname}...")
                    upload_to_artifactory(client, ver, fname, content, dry_run)
                    print(f"  ✅ {fname}")
                except Exception as exc:
                    msg = f"{tag}/{fname}: {exc}"
                    print(f"  ❌ FAILED — {msg}")
                    errors.append(msg)

                # Be polite — don't hammer GHE with 100 rapid downloads
                if not dry_run:
                    time.sleep(0.5)

        print()
        if errors:
            print(f"⚠️  Completed with {len(errors)} error(s):")
            for e in errors:
                print(f"   {e}")
            sys.exit(1)
        else:
            print("🎉 Backfill complete! All releases are now in Artifactory.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be uploaded without actually uploading",
    )
    args = parser.parse_args()
    main(dry_run=args.dry_run)
