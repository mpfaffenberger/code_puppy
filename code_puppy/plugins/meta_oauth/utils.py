"""Credential, device-flow, and model-catalog helpers for Meta Muse OAuth."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from .config import (
    FALLBACK_MODELS,
    META_OAUTH_CONFIG,
    get_muse_auth_path,
    get_token_storage_path,
)

logger = logging.getLogger(__name__)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except FileNotFoundError:
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not read Meta credentials from %s: %s", path, exc)
        return None


def _validate_url(url: str, allowed_host: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host != allowed_host:
        raise ValueError(f"Unexpected Meta endpoint: {url}")
    return url.rstrip("/")


def validate_api_base_url(url: str) -> str:
    """Allow only Meta's HTTPS Model API front door."""
    return _validate_url(url, "api.meta.ai")


def validate_verification_url(url: str) -> str:
    """Allow HTTPS verification pages hosted by Meta."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (
        host == "meta.com" or host.endswith(".meta.com")
    ):
        raise ValueError(f"Unexpected Meta verification URL: {url}")
    return url


def _normalize_credentials(data: dict[str, Any], source: str) -> dict[str, Any] | None:
    api_key = data.get("api_key")
    if not isinstance(api_key, str) or not api_key:
        return None
    try:
        base_url = validate_api_base_url(
            str(data.get("api_base_url") or META_OAUTH_CONFIG["api_base_url"])
        )
    except ValueError as exc:
        logger.warning("Ignoring invalid Meta credential endpoint: %s", exc)
        return None
    normalized = dict(data)
    normalized.update({"api_key": api_key, "api_base_url": base_url, "_source": source})
    return normalized


def load_credentials() -> dict[str, Any] | None:
    """Load Meta credentials using env, Code Puppy, then Muse CLI precedence."""
    env_key = os.getenv("META_API_KEY")
    if env_key:
        return {
            "api_key": env_key,
            "api_base_url": META_OAUTH_CONFIG["api_base_url"],
            "_source": "environment",
        }

    own = _read_json(get_token_storage_path())
    if own:
        normalized = _normalize_credentials(own, "code-puppy")
        if normalized:
            return normalized

    muse = _read_json(get_muse_auth_path())
    providers = muse.get("providers") if muse else None
    provider = providers.get("meta") if isinstance(providers, dict) else None
    if isinstance(provider, dict):
        return _normalize_credentials(provider, "muse")
    return None


def save_credentials(credentials: dict[str, Any]) -> bool:
    """Atomically save private Meta credentials with mode 0600."""
    if not credentials.get("api_key"):
        raise ValueError("Meta credentials require an api_key")
    destination = get_token_storage_path()
    payload = {key: value for key, value in credentials.items() if key != "_source"}
    temporary_path: str | None = None
    try:
        fd, temporary_path = tempfile.mkstemp(
            prefix=".meta_oauth.", dir=destination.parent
        )
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        os.replace(temporary_path, destination)
        destination.chmod(0o600)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to save Meta OAuth credentials: %s", exc)
        if temporary_path:
            Path(temporary_path).unlink(missing_ok=True)
        return False


def _problem(response: requests.Response, fallback: str) -> str:
    try:
        payload = response.json()
    except ValueError:
        return fallback
    if not isinstance(payload, dict):
        return fallback
    return str(
        payload.get("detail")
        or payload.get("title")
        or payload.get("error")
        or fallback
    )


def request_device_authorization() -> dict[str, Any]:
    """Start Meta's RFC 8628 device authorization flow."""
    base = _validate_url(str(META_OAUTH_CONFIG["auth_base_url"]), "auth.meta.com")
    response = requests.post(
        base + str(META_OAUTH_CONFIG["device_authorization_path"]),
        data={"client_id": META_OAUTH_CONFIG["client_id"]},
        headers={"Accept": "application/json", "User-Agent": "code-puppy/meta-oauth"},
        timeout=META_OAUTH_CONFIG["request_timeout"],
        allow_redirects=False,
    )
    if not response.ok:
        raise RuntimeError(
            _problem(response, f"Device authorization failed ({response.status_code})")
        )
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Meta device authorization returned invalid JSON")
    verification_url = payload.get("verification_uri_complete") or payload.get(
        "verification_uri"
    )
    if verification_url:
        validate_verification_url(str(verification_url))
    return payload


def poll_device_token(device_code: str) -> tuple[str, dict[str, Any]]:
    """Perform one device-token poll and return its OAuth state and payload."""
    base = _validate_url(str(META_OAUTH_CONFIG["auth_base_url"]), "auth.meta.com")
    response = requests.post(
        base + str(META_OAUTH_CONFIG["device_token_path"]),
        data={
            "grant_type": META_OAUTH_CONFIG["device_code_grant"],
            "device_code": device_code,
            "client_id": META_OAUTH_CONFIG["client_id"],
        },
        headers={"Accept": "application/json", "User-Agent": "code-puppy/meta-oauth"},
        timeout=META_OAUTH_CONFIG["request_timeout"],
        allow_redirects=False,
    )
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("Meta token endpoint returned invalid JSON") from exc
    if response.ok and isinstance(payload, dict) and payload.get("access_token"):
        return "authorized", payload
    if isinstance(payload, dict):
        return str(payload.get("error") or f"http_{response.status_code}"), payload
    return f"http_{response.status_code}", {}


def mint_api_credentials(access_token: str) -> dict[str, Any]:
    """Exchange a Meta account token for a Model API credential."""
    response = requests.post(
        _validate_url(str(META_OAUTH_CONFIG["mint_url"]), "api.meta.ai"),
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "code-puppy/meta-oauth",
            "x-api-version": META_OAUTH_CONFIG["api_version"],
        },
        timeout=META_OAUTH_CONFIG["request_timeout"],
        allow_redirects=False,
    )
    if not response.ok:
        raise RuntimeError(
            _problem(response, f"Meta key mint failed ({response.status_code})")
        )
    payload = response.json()
    if not isinstance(payload, dict) or not payload.get("api_key"):
        raise RuntimeError("Meta key mint returned no API key")
    payload["api_base_url"] = validate_api_base_url(
        str(payload.get("base_url") or payload.get("api_base_url") or "")
    )
    payload.pop("base_url", None)
    return payload


def discover_models(credentials: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Fetch Meta's Muse catalogue and convert it to Code Puppy model specs."""
    response = requests.get(
        _validate_url(str(META_OAUTH_CONFIG["catalog_url"]), "api.meta.ai"),
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {credentials['api_key']}",
            "User-Agent": "code-puppy/meta-oauth",
            "x-api-version": META_OAUTH_CONFIG["api_version"],
        },
        timeout=META_OAUTH_CONFIG["request_timeout"],
    )
    if not response.ok:
        raise RuntimeError(
            _problem(response, f"Meta model discovery failed ({response.status_code})")
        )

    payload = response.json()
    rows = payload.get("data", []) if isinstance(payload, dict) else []
    models: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            continue
        metadata = row.get("metadata")
        details = metadata.get("muse-code") if isinstance(metadata, dict) else None
        if not isinstance(details, dict) or details.get("is_hidden") is True:
            continue
        raw_limits = details.get("limit")
        limits = raw_limits if isinstance(raw_limits, dict) else {}
        models[row["id"]] = {
            "context_length": int(limits.get("context") or 128_000),
            "supported_settings": ["reasoning_effort"]
            if details.get("reasoning")
            else [],
        }
    return models or dict(FALLBACK_MODELS)
