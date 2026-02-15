"""Remote skills catalog client.

Fetches the remote skills catalog JSON and exposes a cached, parsed view.

Design goals:
- Never crash the app (defensive parsing + broad error handling).
- Local caching with TTL for fast startup and offline use.
- Synchronous networking only (httpx.Client).

Schema source:
https://www.llmspec.dev/skills/skills.json
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin

import httpx

logger = logging.getLogger(__name__)

SKILLS_JSON_URL = "https://www.llmspec.dev/skills/skills.json"

_CACHE_DIR = Path.home() / ".code_puppy" / "cache"
_CACHE_PATH = _CACHE_DIR / "skills_catalog.json"
_CACHE_TTL_SECONDS = 30 * 60


@dataclass(frozen=True, slots=True)
class RemoteSkillEntry:
    """Flattened remote skill entry."""

    name: str
    description: str
    group: str
    download_url: str
    zip_size_bytes: int
    file_count: int
    has_scripts: bool
    has_references: bool
    has_license: bool


@dataclass(frozen=True, slots=True)
class RemoteCatalogData:
    """Parsed remote catalog.

    Attributes:
        version: Catalog version string.
        base_url: Base URL used to build absolute download_url values.
        total_skills: Total number of skills in the remote catalog.
        groups: Raw group objects from the JSON (kept as dicts for flexibility).
        entries: Flattened list of all skills across all groups.
    """

    version: str
    base_url: str
    total_skills: int
    groups: list[dict[str, Any]]
    entries: list[RemoteSkillEntry]


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _safe_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return bool(value)


def _cache_is_fresh(cache_path: Path, ttl_seconds: int) -> bool:
    try:
        if not cache_path.exists():
            return False
        age_seconds = time.time() - cache_path.stat().st_mtime
        return age_seconds <= ttl_seconds
    except Exception as e:
        logger.debug(f"Failed to check cache age for {cache_path}: {e}")
        return False


def _read_cache(cache_path: Path) -> Optional[dict[str, Any]]:
    try:
        if not cache_path.exists():
            return None
        raw = cache_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            logger.warning(f"Cache JSON is not an object: {cache_path}")
            return None
        return data
    except Exception as e:
        logger.warning(f"Failed to read cache {cache_path}: {e}")
        return None


def _write_cache(cache_path: Path, data: dict[str, Any]) -> bool:
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        # Stable formatting so diffs are readable when debugging.
        cache_path.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return True
    except Exception as e:
        logger.warning(f"Failed to write cache {cache_path}: {e}")
        return False


def _fetch_remote_json(url: str) -> Optional[dict[str, Any]]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "code-puppy/remote-catalog",
    }

    try:
        with httpx.Client(timeout=15, headers=headers) as client:
            response = client.get(url)
            response.raise_for_status()
            data = response.json()

        if not isinstance(data, dict):
            logger.error(f"Remote catalog JSON was not an object. Got: {type(data)}")
            return None

        return data

    except httpx.HTTPStatusError as e:
        logger.warning(
            "Remote catalog request returned bad status: "
            f"{e.response.status_code} {e.response.reason_phrase}"
        )
        return None
    except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as e:
        logger.warning(f"Remote catalog network failure: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.warning(f"Remote catalog returned invalid JSON: {e}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error fetching remote catalog: {e}")
        return None


def _parse_catalog(raw: dict[str, Any]) -> Optional[RemoteCatalogData]:
    try:
        version = str(raw.get("version") or "")
        base_url = str(raw.get("base_url") or "")
        total_skills = _safe_int(raw.get("total_skills"), default=0)

        raw_groups = raw.get("groups")
        if not isinstance(raw_groups, list):
            logger.warning("Remote catalog 'groups' missing or not a list")
            raw_groups = []

        groups: list[dict[str, Any]] = []
        entries: list[RemoteSkillEntry] = []

        # Ensure urljoin behaves (needs trailing slash on base).
        base_for_join = base_url.rstrip("/") + "/" if base_url else ""

        for group_obj in raw_groups:
            if not isinstance(group_obj, dict):
                continue
            groups.append(group_obj)

            group_slug = str(group_obj.get("slug") or group_obj.get("name") or "")
            skills = group_obj.get("skills")
            if not isinstance(skills, list):
                continue

            for skill in skills:
                if not isinstance(skill, dict):
                    continue

                name = str(skill.get("name") or "").strip()
                if not name:
                    # If name is missing, it can't be indexed/activated anyway.
                    continue

                description = str(skill.get("description") or "")
                group = str(skill.get("group") or group_slug or "")

                download_path = str(skill.get("download_url") or "")
                download_url = (
                    urljoin(base_for_join, download_path)
                    if base_for_join
                    else download_path
                )

                contents = skill.get("contents")
                if not isinstance(contents, dict):
                    contents = {}

                entries.append(
                    RemoteSkillEntry(
                        name=name,
                        description=description,
                        group=group,
                        download_url=download_url,
                        zip_size_bytes=_safe_int(
                            skill.get("zip_size_bytes"), default=0
                        ),
                        file_count=_safe_int(skill.get("file_count"), default=0),
                        has_scripts=_safe_bool(
                            contents.get("has_scripts"), default=False
                        ),
                        has_references=_safe_bool(
                            contents.get("has_references"), default=False
                        ),
                        has_license=_safe_bool(
                            contents.get("has_license"), default=False
                        ),
                    )
                )

        if not version:
            logger.debug("Remote catalog 'version' is missing/empty")
        if not base_url:
            logger.debug("Remote catalog 'base_url' is missing/empty")

        return RemoteCatalogData(
            version=version,
            base_url=base_url,
            total_skills=total_skills,
            groups=groups,
            entries=entries,
        )

    except Exception as e:
        logger.exception(f"Failed to parse remote catalog JSON: {e}")
        return None


def fetch_remote_catalog(force_refresh: bool = False) -> Optional[RemoteCatalogData]:
    """Fetch the remote skills catalog with caching and offline fallback.

    Cache behavior:
    - Cache file: ~/.code_puppy/cache/skills_catalog.json
    - TTL: 30 minutes (based on file mtime)
    - Offline fallback: if network fetch fails, use cache if present (even if expired)

    Args:
        force_refresh: If True, always attempt a network fetch.

    Returns:
        Parsed RemoteCatalogData on success, otherwise None.
    """

    cache_fresh = _cache_is_fresh(_CACHE_PATH, _CACHE_TTL_SECONDS)

    # Use fresh cache unless forced.
    if not force_refresh and cache_fresh:
        logger.info(f"Using fresh remote catalog cache: {_CACHE_PATH}")
        cached = _read_cache(_CACHE_PATH)
        if cached is None:
            logger.warning("Fresh cache exists but could not be read; refetching")
        else:
            parsed = _parse_catalog(cached)
            if parsed is not None:
                return parsed
            logger.warning("Fresh cache exists but could not be parsed; refetching")

    if force_refresh:
        logger.info("Force refresh enabled; fetching remote skills catalog")
    elif _CACHE_PATH.exists():
        logger.info(
            "Cache is missing or stale; fetching remote skills catalog "
            f"(cache_path={_CACHE_PATH}, fresh={cache_fresh})"
        )
    else:
        logger.info("No cache present; fetching remote skills catalog")

    remote_raw = _fetch_remote_json(SKILLS_JSON_URL)
    if remote_raw is not None:
        logger.info("Fetched remote skills catalog successfully")
        _write_cache(_CACHE_PATH, remote_raw)
        parsed = _parse_catalog(remote_raw)
        if parsed is not None:
            return parsed
        logger.warning("Remote catalog fetched but failed to parse")

    # Offline fallback: use cache even if expired.
    if _CACHE_PATH.exists():
        logger.warning(
            "Remote fetch failed; falling back to cached skills catalog "
            f"(even if expired): {_CACHE_PATH}"
        )
        cached = _read_cache(_CACHE_PATH)
        if cached is None:
            return None
        return _parse_catalog(cached)

    logger.error("Remote fetch failed and no cache is available")
    return None
