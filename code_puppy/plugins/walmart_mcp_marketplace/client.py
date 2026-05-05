"""HTTP client + on-disk cache for the Walmart MCP marketplace registry.

Hits the metaregistry BFF and caches the result for 24 hours so we don't
hammer prod every time someone opens `/mcp install`.

Layout: tiny pure functions, no global state beyond the cache file path.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, List

from code_puppy.config import CONFIG_DIR
from code_puppy.http_utils import create_client

logger = logging.getLogger(__name__)

REGISTRY_URL = (
    "https://dx.walmart.com/proxy/metaregistry/mcp-applications?environment=prod"
)
DETAIL_URL_TMPL = (
    "https://dx.walmart.com/proxy/metaregistry/mcp-applications/{key}?environment=prod"
)
CACHE_PATH = Path(CONFIG_DIR) / "walmart_mcp_marketplace_cache.json"
DETAIL_CACHE_PATH = Path(CONFIG_DIR) / "walmart_mcp_marketplace_detail_cache.json"
CACHE_TTL_SECONDS = 24 * 60 * 60  # 1 day
DEFAULT_TIMEOUT = 15.0


def _read_cache() -> List[dict] | None:
    """Return cached entries if fresh, else None."""
    if not CACHE_PATH.exists():
        return None
    try:
        raw = json.loads(CACHE_PATH.read_text())
        ts = raw.get("fetched_at", 0)
        if time.time() - ts > CACHE_TTL_SECONDS:
            return None
        data = raw.get("data")
        if isinstance(data, list):
            return data
    except Exception as exc:  # noqa: BLE001 — cache should never crash callers
        logger.debug("Walmart MCP marketplace cache unreadable: %s", exc)
    return None


def _read_stale_cache() -> List[dict] | None:
    """Return cached entries even if expired (network fallback)."""
    if not CACHE_PATH.exists():
        return None
    try:
        raw = json.loads(CACHE_PATH.read_text())
        data = raw.get("data")
        if isinstance(data, list):
            return data
    except Exception:
        return None
    return None


def _write_cache(data: List[dict]) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(
            json.dumps({"fetched_at": time.time(), "data": data})
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to write Walmart MCP marketplace cache: %s", exc)


def _fetch_remote() -> List[dict]:
    """Hit the BFF, return raw list. Raises on failure.

    Uses ``code_puppy.http_utils.create_client`` so we get the configured
    proxy/SSL behaviour from the rest of the app (super important on the
    Walmart corporate network).
    """
    with create_client(timeout=int(DEFAULT_TIMEOUT)) as client:
        resp = client.get(REGISTRY_URL, follow_redirects=True)
        resp.raise_for_status()
        body = resp.json()
        if not isinstance(body, list):
            raise ValueError(f"Unexpected response shape: {type(body).__name__}")
        return body


def fetch_marketplace(force_refresh: bool = False) -> List[dict]:
    """Return the marketplace entries, using cache when fresh.

    On network failure, returns stale cache if available, otherwise [].
    Never raises — failures are logged and degrade gracefully.
    """
    if not force_refresh:
        cached = _read_cache()
        if cached is not None:
            return cached

    try:
        data = _fetch_remote()
        _write_cache(data)
        return data
    except Exception as exc:  # noqa: BLE001
        logger.info("Walmart MCP marketplace fetch failed (%s); using stale cache", exc)
        stale = _read_stale_cache()
        return stale or []


def clear_cache() -> bool:
    """Delete the cache file. Returns True if a file was removed."""
    removed = False
    for path in (CACHE_PATH, DETAIL_CACHE_PATH):
        if path.exists():
            try:
                os.unlink(path)
                removed = True
            except Exception:  # noqa: BLE001
                pass
    return removed


# ---------------------------------------------------------------------------
# Per-server detail (used to grab personalization.customHeadersByEditor)
# ---------------------------------------------------------------------------


def _read_detail_cache() -> dict:
    """Return the on-disk detail cache as ``{key: {fetched_at, data}}``."""
    if not DETAIL_CACHE_PATH.exists():
        return {}
    try:
        raw = json.loads(DETAIL_CACHE_PATH.read_text())
        if isinstance(raw, dict):
            return raw
    except Exception as exc:  # noqa: BLE001
        logger.debug("Walmart MCP detail cache unreadable: %s", exc)
    return {}


def _write_detail_cache(cache: dict) -> None:
    try:
        DETAIL_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        DETAIL_CACHE_PATH.write_text(json.dumps(cache))
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to write Walmart MCP detail cache: %s", exc)


def _detail_from_cache(key: str, *, allow_stale: bool = False) -> Any | None:
    cache = _read_detail_cache()
    entry = cache.get(key)
    if not isinstance(entry, dict):
        return None
    data = entry.get("data")
    if data is None:
        return None
    if allow_stale:
        return data
    if time.time() - entry.get("fetched_at", 0) > CACHE_TTL_SECONDS:
        return None
    return data


def _fetch_detail_remote(key: str) -> dict:
    """Hit the BFF detail endpoint for one server. Raises on failure."""
    url = DETAIL_URL_TMPL.format(key=key)
    with create_client(timeout=int(DEFAULT_TIMEOUT)) as client:
        resp = client.get(url, follow_redirects=True)
        resp.raise_for_status()
        body = resp.json()
        if not isinstance(body, dict):
            raise ValueError(f"Unexpected detail shape: {type(body).__name__}")
        return body


def fetch_marketplace_detail(
    key: str, *, force_refresh: bool = False
) -> dict | None:
    """Return the per-server BFF detail (cached 24h).

    Used to look up ``personalization.customHeadersByEditor`` so we can
    register Walmart MCP servers without making the user manually export a
    ``WMT_CONSUMER_ID``. Returns ``None`` on network failure when no cached
    value exists — callers should treat that as "no personalization".
    """
    if not key:
        return None
    if not force_refresh:
        cached = _detail_from_cache(key)
        if cached is not None:
            return cached
    try:
        data = _fetch_detail_remote(key)
    except Exception as exc:  # noqa: BLE001
        logger.info(
            "Walmart MCP detail fetch failed for %s (%s); using stale cache",
            key,
            exc,
        )
        return _detail_from_cache(key, allow_stale=True)

    cache = _read_detail_cache()
    cache[key] = {"fetched_at": time.time(), "data": data}
    _write_detail_cache(cache)
    return data


def extract_personalization_headers(
    detail: dict | None, editor: str = "cursor"
) -> dict[str, str]:
    """Pull the routing headers for ``editor`` out of a detail payload.

    Walmart's metaregistry pre-registers a ``WM_CONSUMER.ID`` per editor
    (vscode/intellij/cursor/windsurf). Code-puppy isn't an officially-listed
    editor, so per DISCOVERY_NOTES.md we impersonate one whose consumer id
    is allow-listed at the Istio layer.

    Returns ``{}`` if the detail is missing personalization or the requested
    editor isn't present — caller is responsible for falling back.
    """
    if not detail:
        return {}
    pers = detail.get("personalization") or {}
    entries = pers.get("customHeadersByEditor") or []
    by_editor = {
        (e.get("editor") or "").lower(): e.get("headers") or {}
        for e in entries
        if isinstance(e, dict)
    }
    headers = by_editor.get(editor.lower()) or {}
    # Anything else if the chosen editor is missing — first non-empty.
    if not headers:
        for ed_headers in by_editor.values():
            if ed_headers:
                headers = ed_headers
                break
    # Coerce all values to strings so they slot straight into request headers.
    return {str(k): str(v) for k, v in headers.items() if v is not None}
