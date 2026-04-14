"""HTTP clients for skill marketplaces.

Supports two sources:
    1. E2E Open Skills  — e2e-open-skills.walmartlabs.com
    2. MetaRegistry BFF — metaregistry-bff.stage.walmart.com

Each skill dict carries a `_source` key ("e2e" or "metaregistry") so
downstream code (TUI, install) knows which API to hit.
"""

import asyncio
import concurrent.futures
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from code_puppy.http_utils import get_cert_bundle_path

from . import metaregistry_client

E2E_BASE_URL = "https://e2e-open-skills.walmartlabs.com"
DEFAULT_TIMEOUT = 20.0
SKILLS_DIR = Path.home() / ".code_puppy" / "skills"

SOURCE_E2E = "e2e"
SOURCE_METAREGISTRY = "metaregistry"


def _normalize(success: bool, data: Any = None, error: Optional[str] = None) -> dict:
    """Normalize API responses."""
    return {"success": success, "data": data, "error": error}


async def fetch_e2e_skills() -> Dict[str, Any]:
    """Fetch skills from E2E Open Skills marketplace.

    Each skill gets ``_source = "e2e"`` injected.
    """
    try:
        async with httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT, verify=get_cert_bundle_path(), follow_redirects=True
        ) as client:
            resp = await client.get(f"{E2E_BASE_URL}/skills")
            if resp.status_code >= 400:
                return _normalize(False, error=f"HTTP {resp.status_code}")
            body = resp.json()
            skills = body.get("skills", [])
            for s in skills:
                s["_source"] = SOURCE_E2E
            return _normalize(True, data=skills)
    except httpx.TimeoutException:
        return _normalize(False, error="E2E request timed out")
    except httpx.ConnectError as e:
        return _normalize(False, error=f"E2E connection error: {e}")
    except Exception as e:
        return _normalize(False, error=str(e))


async def fetch_metaregistry_skills() -> Dict[str, Any]:
    """Fetch skills from MetaRegistry BFF.

    Normalizes the response so every skill has:
    - ``name``, ``description``, ``tags`` (comma-string), ``_source``
    - Raw content available via ``content.raw`` for direct install
    """
    resp = await metaregistry_client.fetch_skills()
    if not resp.get("success"):
        return resp
    skills = resp.get("data", [])
    for s in skills:
        s["_source"] = SOURCE_METAREGISTRY
        # Ensure name field exists (API uses 'key' or 'name')
        if "name" not in s:
            s["name"] = s.get("key", s.get("appKey", "unknown"))
        # Normalize tags: API returns list, TUI expects comma-string
        raw_tags = s.get("tags", [])
        if isinstance(raw_tags, list):
            s["tags"] = ", ".join(raw_tags)
    return _normalize(True, data=skills)


async def fetch_all_skills() -> Dict[str, Any]:
    """Fetch skills from ALL sources, merged into one list.

    Errors from individual sources are swallowed gracefully
    so the TUI always shows whatever is available.
    """
    import asyncio

    results = await asyncio.gather(
        fetch_e2e_skills(),
        fetch_metaregistry_skills(),
        return_exceptions=True,
    )

    all_skills: List[dict] = []
    errors: List[str] = []

    for result in results:
        if isinstance(result, Exception):
            errors.append(str(result))
        elif isinstance(result, dict):
            if result.get("success"):
                all_skills.extend(result.get("data", []))
            elif result.get("error"):
                errors.append(result["error"])

    if all_skills:
        return _normalize(True, data=all_skills)
    # Nothing from either source
    return _normalize(False, error="; ".join(errors) if errors else "No skills found")


# Backward compat alias
fetch_skills = fetch_all_skills


async def fetch_skill_detail(name: str) -> Dict[str, Any]:
    """Fetch metadata for a single skill (E2E only)."""
    try:
        async with httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT, verify=get_cert_bundle_path(), follow_redirects=True
        ) as client:
            resp = await client.get(f"{E2E_BASE_URL}/skills/{name}")
            if resp.status_code >= 400:
                return _normalize(False, error=f"HTTP {resp.status_code}")
            return _normalize(True, data=resp.json())
    except Exception as e:
        return _normalize(False, error=str(e))


async def fetch_skill_md(
    name: str,
    source: str = SOURCE_E2E,
    skill_id: Optional[str] = None,
    cached_content: Optional[str] = None,
) -> Dict[str, Any]:
    """Download the raw SKILL.md content from the correct source.

    Args:
        name: Skill name.
        source: Which marketplace ("e2e" or "metaregistry").
        skill_id: MetaRegistry skill ID (if different from name).
        cached_content: If the caller already has the raw content
            (MetaRegistry embeds it in content.raw), skip the fetch.
    """
    # Fast path: content already available from the listing response
    if cached_content:
        return _normalize(True, data=cached_content)

    if source == SOURCE_METAREGISTRY:
        return await metaregistry_client.fetch_skill_file_content(
            skill_id or name, "SKILL.md"
        )
    # Default: E2E
    try:
        async with httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT, verify=get_cert_bundle_path(), follow_redirects=True
        ) as client:
            resp = await client.get(f"{E2E_BASE_URL}/skills/{name}/SKILL.md")
            if resp.status_code >= 400:
                return _normalize(False, error=f"HTTP {resp.status_code}")
            return _normalize(True, data=resp.text)
    except Exception as e:
        return _normalize(False, error=str(e))


def install_skill(
    name: str,
    content: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Path:
    """Write SKILL.md to ~/.code_puppy/skills/{name}/SKILL.md.

    If content lacks YAML frontmatter (---), we inject it from metadata.
    This handles MetaRegistry skills which may not have frontmatter.

    Args:
        name: Skill name (directory name).
        content: Raw SKILL.md text.
        metadata: Optional dict with name, description, tags, author, version.

    Returns:
        Path to the installed SKILL.md.
    """
    skill_dir = SKILLS_DIR / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    dest = skill_dir / "SKILL.md"

    # Check if content already has frontmatter
    final_content = content
    if not content.strip().startswith("---"):
        # Inject frontmatter from metadata
        final_content = _build_frontmatter(name, metadata) + content

    dest.write_text(final_content, encoding="utf-8")
    return dest


def _build_frontmatter(name: str, metadata: Optional[Dict[str, Any]] = None) -> str:
    """Build YAML frontmatter block for a skill."""
    meta = metadata or {}
    lines = ["---"]
    lines.append(f"name: {name}")

    desc = meta.get("description", "")
    if desc:
        # Escape quotes and truncate for YAML
        desc = desc.replace('"', '\\"')[:200]
        lines.append(f'description: "{desc}"')

    # Tags
    raw_tags = meta.get("tags", [])
    if isinstance(raw_tags, str):
        raw_tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
    if raw_tags:
        lines.append(f"tags: [{', '.join(raw_tags)}]")

    # Author/version from nested metadata or top-level
    nested = meta.get("metadata", {})
    if isinstance(nested, dict):
        if nested.get("author"):
            lines.append(f"author: {nested['author']}")
        if nested.get("version"):
            lines.append(f'version: "{nested["version"]}"')

    lines.append("---\n")
    return "\n".join(lines)


def is_skill_installed(name: str) -> bool:
    """Check if a skill is already installed locally."""
    return (SKILLS_DIR / name / "SKILL.md").exists()


def _flatten_file_tree(
    entries: List[Any], shallow_dirs: Optional[List[str]] = None
) -> tuple[List[str], List[str]]:
    """Recursively flatten a nested file tree into a list of file paths.

    Handles the MetaRegistry tree structure:
        {"name": "foo.md", "path": "references/foo.md", "type": "file"}
        {"name": "subdir", "path": "references/subdir", "type": "directory", "children": [...]}

    Also tracks "shallow" directories (type=directory but no children populated)
    so we can try the GitHub fallback for those.

    Returns:
        Tuple of (file_paths, shallow_directory_paths)
    """
    if shallow_dirs is None:
        shallow_dirs = []

    paths: List[str] = []
    for entry in entries:
        if isinstance(entry, str):
            # Simple string path
            if entry and entry != "SKILL.md":
                paths.append(entry)
        elif isinstance(entry, dict):
            entry_type = entry.get("type", "file")
            entry_path = entry.get("path", "")

            if entry_type == "file" and entry_path and entry_path != "SKILL.md":
                paths.append(entry_path)
            elif entry_type == "directory":
                children = entry.get("children", [])
                if children:
                    # Recurse into children
                    child_paths, _ = _flatten_file_tree(children, shallow_dirs)
                    paths.extend(child_paths)
                elif entry_path:
                    # Directory with no children - MetaRegistry didn't populate it
                    shallow_dirs.append(entry_path)

    return paths, shallow_dirs


async def _discover_extra_files(
    skill_key: str, skill_metadata: Optional[Dict[str, Any]] = None
) -> List[str]:
    """Fetch the file tree from MetaRegistry and return non-SKILL.md paths.

    Handles nested directory structures by recursively flattening the tree.
    If MetaRegistry returns "shallow" directories (without children), falls
    back to the GitHub Git Trees API for a complete recursive listing.

    Args:
        skill_key: Skill name/key for API calls.
        skill_metadata: Optional skill metadata containing githubUrl/sourceCommitId.

    Returns:
        List of file paths (empty on error - install proceeds with just SKILL.md).
    """
    try:
        resp = await metaregistry_client.fetch_skill_files(skill_key)
        if not resp.get("success"):
            return []

        raw_data = resp.get("data", [])
        if isinstance(raw_data, dict):
            raw_data = raw_data.get("files", [])

        paths, shallow_dirs = _flatten_file_tree(raw_data)

        # If we found shallow directories, try GitHub fallback for complete listing
        if shallow_dirs and skill_metadata:
            github_url = skill_metadata.get("githubUrl", "")
            commit_sha = skill_metadata.get("sourceCommitId")

            if github_url:
                github_resp = await metaregistry_client.fetch_github_tree_recursive(
                    skill_key, github_url, commit_sha
                )
                if github_resp.get("success"):
                    # GitHub gives us complete list - use it instead
                    github_files = github_resp.get("data", [])
                    # Filter out SKILL.md
                    return [f for f in github_files if f != "SKILL.md"]

        return paths
    except Exception:
        return []


async def install_skill_full(
    name: str,
    skill_metadata: Dict[str, Any],
) -> Dict[str, Any]:
    """Download and install ALL files for a skill.

    For MetaRegistry skills, downloads a ZIP archive containing everything.
    For E2E skills (SKILL.md only), downloads just the markdown.

    Args:
        name: Skill name (directory name).
        skill_metadata: Full skill dict from the marketplace API.

    Returns:
        Normalized response with installed file count.
    """
    source = skill_metadata.get("_source", SOURCE_E2E)
    skill_key = skill_metadata.get("key", skill_metadata.get("name", name))
    skill_dir = SKILLS_DIR / name
    skill_dir.mkdir(parents=True, exist_ok=True)

    installed_files: List[str] = []
    errors: List[str] = []

    # MetaRegistry: Use ZIP download for complete skill (includes nested dirs)
    if source == SOURCE_METAREGISTRY:
        zip_resp = await metaregistry_client.download_skill_zip(skill_key)
        if zip_resp.get("success"):
            files_dict = zip_resp.get("data", {})
            for file_path, content in files_dict.items():
                try:
                    dest = skill_dir / file_path
                    dest.parent.mkdir(parents=True, exist_ok=True)

                    # Handle SKILL.md frontmatter injection
                    if file_path == "SKILL.md" and not content.strip().startswith("---"):
                        content = _build_frontmatter(name, skill_metadata) + content

                    dest.write_text(content, encoding="utf-8")

                    # Make shell/ts scripts executable
                    if dest.suffix in (".sh", ".ts"):
                        dest.chmod(dest.stat().st_mode | 0o111)

                    installed_files.append(file_path)
                except Exception as e:
                    errors.append(f"{file_path}: {e}")

            result = {
                "installed_files": installed_files,
                "file_count": len(installed_files),
                "skill_dir": str(skill_dir),
            }
            if errors:
                result["warnings"] = errors
            return _normalize(True, data=result)
        else:
            # ZIP failed - fall back to piecemeal download
            errors.append(f"ZIP download failed: {zip_resp.get('error')}")

    # E2E skills or MetaRegistry ZIP fallback: fetch files individually
    # 1. Install SKILL.md first
    cached_content = None
    content_obj = skill_metadata.get("content")
    if isinstance(content_obj, dict) and content_obj.get("raw"):
        cached_content = content_obj["raw"]

    if cached_content:
        md_content = cached_content
    else:
        if source == SOURCE_METAREGISTRY:
            resp = await metaregistry_client.fetch_skill_file_content(skill_key, "SKILL.md")
        else:
            try:
                async with httpx.AsyncClient(
                    timeout=DEFAULT_TIMEOUT, verify=get_cert_bundle_path(), follow_redirects=True
                ) as client:
                    r = await client.get(f"{E2E_BASE_URL}/skills/{name}/SKILL.md")
                    if r.status_code >= 400:
                        return _normalize(False, error=f"Failed to fetch SKILL.md: HTTP {r.status_code}")
                    resp = _normalize(True, data=r.text)
            except Exception as e:
                return _normalize(False, error=f"Failed to fetch SKILL.md: {e}")

        if not resp.get("success"):
            return resp
        md_content = resp.get("data", "")

    # Write SKILL.md with frontmatter injection if needed
    final_content = md_content
    if not md_content.strip().startswith("---"):
        final_content = _build_frontmatter(name, skill_metadata) + md_content

    (skill_dir / "SKILL.md").write_text(final_content, encoding="utf-8")
    installed_files.append("SKILL.md")

    # 2. For MetaRegistry fallback, try to get extra files via file tree
    if source == SOURCE_METAREGISTRY:
        extra_files = await _discover_extra_files(skill_key, skill_metadata)
        for file_path in extra_files:
            try:
                resp = await metaregistry_client.fetch_skill_file_content(
                    skill_key, file_path
                )
                if resp.get("success"):
                    dest = skill_dir / file_path
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(resp.get("data", ""), encoding="utf-8")
                    if dest.suffix in (".sh", ".ts"):
                        dest.chmod(dest.stat().st_mode | 0o111)
                    installed_files.append(file_path)
                else:
                    errors.append(f"{file_path}: {resp.get('error', 'unknown')}")
            except Exception as e:
                errors.append(f"{file_path}: {e}")

    result = {
        "installed_files": installed_files,
        "file_count": len(installed_files),
        "skill_dir": str(skill_dir),
    }
    if errors:
        result["warnings"] = errors

    return _normalize(True, data=result)


def get_installed_skills() -> List[str]:
    """Return list of locally installed skill names."""
    if not SKILLS_DIR.exists():
        return []
    return [
        d.name
        for d in SKILLS_DIR.iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    ]


def run_async(coro):
    """Run an async coroutine from a sync context safely."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)
