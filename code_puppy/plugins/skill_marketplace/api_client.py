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
            timeout=DEFAULT_TIMEOUT, verify=False, follow_redirects=True
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
            timeout=DEFAULT_TIMEOUT, verify=False, follow_redirects=True
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
            timeout=DEFAULT_TIMEOUT, verify=False, follow_redirects=True
        ) as client:
            resp = await client.get(f"{E2E_BASE_URL}/skills/{name}/SKILL.md")
            if resp.status_code >= 400:
                return _normalize(False, error=f"HTTP {resp.status_code}")
            return _normalize(True, data=resp.text)
    except Exception as e:
        return _normalize(False, error=str(e))


def install_skill(name: str, content: str) -> Path:
    """Write SKILL.md to ~/.code_puppy/skills/{name}/SKILL.md.

    Args:
        name: Skill name (directory name).
        content: Raw SKILL.md text.

    Returns:
        Path to the installed SKILL.md.
    """
    skill_dir = SKILLS_DIR / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    dest = skill_dir / "SKILL.md"
    dest.write_text(content, encoding="utf-8")
    return dest


def is_skill_installed(name: str) -> bool:
    """Check if a skill is already installed locally."""
    return (SKILLS_DIR / name / "SKILL.md").exists()


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
