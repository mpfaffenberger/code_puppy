"""HTTP client for the E2E Open Skills marketplace API.

Endpoints:
    GET /skills              → list all skills
    GET /skills/{name}       → skill metadata
    GET /skills/{name}/SKILL.md → raw SKILL.md content
"""

import asyncio
import concurrent.futures
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

BASE_URL = "https://e2e-open-skills.walmartlabs.com"
DEFAULT_TIMEOUT = 20.0
SKILLS_DIR = Path.home() / ".code_puppy" / "skills"


def _normalize(success: bool, data: Any = None, error: Optional[str] = None) -> dict:
    """Normalize API responses."""
    return {"success": success, "data": data, "error": error}


async def fetch_skills() -> Dict[str, Any]:
    """Fetch the full skill catalog.

    Returns:
        Normalized response with data as list of skill dicts.
    """
    try:
        async with httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT, verify=False, follow_redirects=True
        ) as client:
            resp = await client.get(f"{BASE_URL}/skills")
            if resp.status_code >= 400:
                return _normalize(False, error=f"HTTP {resp.status_code}")
            body = resp.json()
            return _normalize(True, data=body.get("skills", []))
    except httpx.TimeoutException:
        return _normalize(False, error="Request timed out")
    except httpx.ConnectError as e:
        return _normalize(False, error=f"Connection error: {e}")
    except Exception as e:
        return _normalize(False, error=str(e))


async def fetch_skill_detail(name: str) -> Dict[str, Any]:
    """Fetch metadata for a single skill.

    Returns:
        Normalized response with skill detail dict.
    """
    try:
        async with httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT, verify=False, follow_redirects=True
        ) as client:
            resp = await client.get(f"{BASE_URL}/skills/{name}")
            if resp.status_code >= 400:
                return _normalize(False, error=f"HTTP {resp.status_code}")
            return _normalize(True, data=resp.json())
    except Exception as e:
        return _normalize(False, error=str(e))


async def fetch_skill_md(name: str) -> Dict[str, Any]:
    """Download the raw SKILL.md content.

    Returns:
        Normalized response with raw markdown string.
    """
    try:
        async with httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT, verify=False, follow_redirects=True
        ) as client:
            resp = await client.get(f"{BASE_URL}/skills/{name}/SKILL.md")
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
        d.name for d in SKILLS_DIR.iterdir() if d.is_dir() and (d / "SKILL.md").exists()
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
