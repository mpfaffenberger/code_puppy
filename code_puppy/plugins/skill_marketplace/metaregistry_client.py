"""HTTP client for the MetaRegistry BFF skill marketplace.

Endpoints (from Confluence INTLTARCH space):
    GET /skill-applications                  → list all skills
    GET /skill-applications/:id/files        → file tree for a skill
    GET /skill-applications/:id/files/*path  → specific file content
    GET /skill-applications/hybrid-search    → semantic + keyword search

Base URL defaults to stage; override with METAREGISTRY_BFF_URL env var.
"""

import os
from typing import Any, Dict, List, Optional

import httpx

DEFAULT_TIMEOUT = 15.0


def _get_base_url() -> str:
    """Get MetaRegistry BFF base URL from env or default to stage."""
    return os.environ.get(
        "METAREGISTRY_BFF_URL",
        "http://metaregistry-bff.stage.walmart.com",
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
