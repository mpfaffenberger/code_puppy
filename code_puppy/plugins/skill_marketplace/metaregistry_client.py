"""HTTP client for the MetaRegistry BFF skill marketplace.

Endpoints (from Confluence INTLTARCH space):
    GET /skill-applications                  → list all skills
    GET /skill-applications/:id              → single skill details
    GET /skill-applications/:id/files        → file tree for a skill
    GET /skill-applications/:id/files/*path  → specific file content
    GET /skill-applications/hybrid-search    → semantic + keyword search

Base URL defaults to stage; override with METAREGISTRY_BFF_URL env var.
"""

import io
import os
import re
import zipfile
from typing import Any, Dict, List, Optional, Tuple

import httpx

DEFAULT_TIMEOUT = 15.0


def _get_base_url() -> str:
    """Get MetaRegistry BFF base URL from env or default to prod."""
    return os.environ.get(
        "METAREGISTRY_BFF_URL",
        "https://metaregistry-bff.walmart.com",
    )


def _normalize(success: bool, data: Any = None, error: Optional[str] = None) -> dict:
    return {"success": success, "data": data, "error": error}


async def fetch_skills() -> Dict[str, Any]:
    """List all skills from MetaRegistry.

    Expected response shape (based on Confluence docs)::

        [
            {
                "id": "abc-123",
                "name": "my-skill",
                "description": "Does things",
                "metadata": {
                    "author": "team-x",
                    "owner": "TeamDL",
                    "version": "1.0"
                }
            },
            ...
        ]

    Returns:
        Normalized response with data as list of skill dicts.
    """
    base = _get_base_url()
    try:
        async with httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT, verify=False, follow_redirects=True
        ) as client:
            resp = await client.get(f"{base}/skill-applications")
            if resp.status_code >= 400:
                return _normalize(False, error=f"HTTP {resp.status_code}")
            body = resp.json()
            # Handle both list and {data: [...]} / {skills: [...]} shapes
            if isinstance(body, list):
                skills = body
            elif isinstance(body, dict):
                skills = body.get("data", body.get("skills", []))
            else:
                skills = []
            return _normalize(True, data=skills)
    except httpx.TimeoutException:
        return _normalize(False, error="MetaRegistry timed out")
    except httpx.ConnectError as e:
        return _normalize(False, error=f"MetaRegistry connection error: {e}")
    except Exception as e:
        return _normalize(False, error=f"MetaRegistry error: {e}")


async def fetch_skill_files(skill_id: str) -> Dict[str, Any]:
    """Get the file tree for a skill.

    Args:
        skill_id: The skill ID (or name, depending on API).

    Returns:
        Normalized response with list of file paths.
    """
    base = _get_base_url()
    try:
        async with httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT, verify=False, follow_redirects=True
        ) as client:
            resp = await client.get(f"{base}/skill-applications/{skill_id}/files")
            if resp.status_code >= 400:
                return _normalize(False, error=f"HTTP {resp.status_code}")
            body = resp.json()
            # Expect list of file objects or strings
            if isinstance(body, list):
                return _normalize(True, data=body)
            elif isinstance(body, dict):
                return _normalize(True, data=body.get("files", body.get("data", [])))
            return _normalize(True, data=[])
    except Exception as e:
        return _normalize(False, error=str(e))


async def fetch_skill_details(skill_id: str) -> Dict[str, Any]:
    """Get full skill metadata including GitHub URL and commit SHA.

    This is needed for the GitHub tree fallback when the BFF doesn't return
    nested directory contents.
    """
    base = _get_base_url()
    try:
        async with httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT, verify=False, follow_redirects=True
        ) as client:
            resp = await client.get(f"{base}/skill-applications/{skill_id}")
            if resp.status_code >= 400:
                return _normalize(False, error=f"HTTP {resp.status_code}")
            return _normalize(True, data=resp.json())
    except Exception as e:
        return _normalize(False, error=str(e))


def _parse_github_url(github_url: str) -> Optional[Dict[str, str]]:
    """Extract owner, repo, branch, and path from a GitHub tree URL.

    Example:
        https://gecgithub01.walmart.com/genaica/ai-registry-marketplace/tree/main/path/to/skill
        -> {"host": "gecgithub01.walmart.com", "owner": "genaica",
            "repo": "ai-registry-marketplace", "branch": "main", "path": "path/to/skill"}
    """
    pattern = r"https?://([^/]+)/([^/]+)/([^/]+)/tree/([^/]+)/(.+)"
    match = re.match(pattern, github_url)
    if not match:
        return None
    return {
        "host": match.group(1),
        "owner": match.group(2),
        "repo": match.group(3),
        "branch": match.group(4),
        "path": match.group(5),
    }


async def fetch_github_tree_recursive(
    skill_id: str, github_url: str, commit_sha: Optional[str] = None
) -> Dict[str, Any]:
    """Fetch complete file tree from GitHub using the Git Trees API.

    This works around MetaRegistry BFF not returning nested directory contents.
    Uses recursive=1 to get all files in one call.

    Args:
        skill_id: Skill name (for error messages).
        github_url: Full GitHub tree URL from skill metadata.
        commit_sha: Optional commit SHA for precise tree lookup.

    Returns:
        Normalized response with list of file paths relative to skill root.
    """
    parsed = _parse_github_url(github_url)
    if not parsed:
        return _normalize(False, error=f"Could not parse GitHub URL: {github_url}")

    host = parsed["host"]
    owner = parsed["owner"]
    repo = parsed["repo"]
    branch = commit_sha or parsed["branch"]
    skill_path = parsed["path"]

    # GitHub API: Get tree with recursive flag
    # First we need the tree SHA for the skill subdirectory
    api_base = f"https://{host}/api/v3"

    try:
        async with httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT, verify=False, follow_redirects=True
        ) as client:
            # Get the tree for the branch/commit
            tree_url = f"{api_base}/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
            resp = await client.get(tree_url)

            if resp.status_code == 401:
                return _normalize(False, error="GitHub requires auth")
            if resp.status_code >= 400:
                return _normalize(False, error=f"GitHub HTTP {resp.status_code}")

            body = resp.json()
            tree = body.get("tree", [])

            # Filter to only files under our skill path, and make paths relative
            prefix = skill_path + "/"
            files = []
            for item in tree:
                if item.get("type") != "blob":
                    continue
                path = item.get("path", "")
                if path.startswith(prefix):
                    relative_path = path[len(prefix):]
                    if relative_path:  # Skip empty paths
                        files.append(relative_path)

            return _normalize(True, data=files)
    except Exception as e:
        return _normalize(False, error=str(e))


async def fetch_skill_file_content(
    skill_id: str, file_path: str = "SKILL.md"
) -> Dict[str, Any]:
    """Download a specific file from a skill.

    Args:
        skill_id: The skill ID.
        file_path: Relative path within the skill (default: SKILL.md).

    Returns:
        Normalized response with raw file content string.
    """
    base = _get_base_url()
    try:
        async with httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT, verify=False, follow_redirects=True
        ) as client:
            resp = await client.get(
                f"{base}/skill-applications/{skill_id}/files/{file_path}"
            )
            if resp.status_code >= 400:
                return _normalize(False, error=f"HTTP {resp.status_code}")
            # Check if response is JSON-wrapped or raw text
            content_type = resp.headers.get("content-type", "")
            if "application/json" in content_type:
                body = resp.json()
                # Handle {content: "..."} wrapper
                if isinstance(body, dict) and "content" in body:
                    return _normalize(True, data=body["content"])
                return _normalize(True, data=str(body))
            return _normalize(True, data=resp.text)
    except Exception as e:
        return _normalize(False, error=str(e))


async def search_skills(query: str) -> Dict[str, Any]:
    """Hybrid semantic + keyword search across skills.

    Args:
        query: Search string.

    Returns:
        Normalized response with matching skills.
    """
    base = _get_base_url()
    try:
        async with httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT, verify=False, follow_redirects=True
        ) as client:
            resp = await client.get(
                f"{base}/skill-applications/hybrid-search",
                params={"q": query},
            )
            if resp.status_code >= 400:
                return _normalize(False, error=f"HTTP {resp.status_code}")
            body = resp.json()
            if isinstance(body, list):
                return _normalize(True, data=body)
            elif isinstance(body, dict):
                return _normalize(True, data=body.get("data", body.get("results", [])))
            return _normalize(True, data=[])
    except Exception as e:
        return _normalize(False, error=str(e))


async def download_skill_zip(skill_id: str) -> Dict[str, Any]:
    """Download skill as a ZIP archive containing ALL files.

    This is the most reliable way to get nested subdirectories since the
    /files endpoint doesn't fully populate children for nested dirs.

    Args:
        skill_id: The skill ID/key.

    Returns:
        Normalized response with data as dict mapping relative paths to content:
        {"SKILL.md": "# My Skill...", "references/foo.md": "...", ...}
    """
    base = _get_base_url()
    try:
        async with httpx.AsyncClient(
            timeout=30.0,  # Longer timeout for zip download
            verify=False,
            follow_redirects=True,
        ) as client:
            resp = await client.get(f"{base}/skill-applications/{skill_id}/download")
            if resp.status_code >= 400:
                return _normalize(False, error=f"HTTP {resp.status_code}")

            # Verify it's a ZIP file
            content = resp.content
            if not content.startswith(b"PK"):
                return _normalize(False, error="Response is not a ZIP file")

            # Extract all files from the ZIP
            files: Dict[str, str] = {}
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                for name in zf.namelist():
                    # Skip directories (they end with /)
                    if name.endswith("/"):
                        continue
                    try:
                        # Read and decode as UTF-8 text
                        file_content = zf.read(name).decode("utf-8")
                        files[name] = file_content
                    except UnicodeDecodeError:
                        # Binary file - skip or store as placeholder
                        files[name] = f"[binary file: {len(zf.read(name))} bytes]"

            return _normalize(True, data=files)
    except zipfile.BadZipFile:
        return _normalize(False, error="Invalid ZIP file")
    except Exception as e:
        return _normalize(False, error=str(e))
