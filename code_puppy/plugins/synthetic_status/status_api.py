"""HTTP helpers for Synthetic quota status."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import requests

from code_puppy.model_factory import get_api_key

SYNTHETIC_QUOTAS_URL = "https://api.synthetic.new/v2/quotas"


@dataclass
class SyntheticQuota:
    """Parsed Synthetic subscription quota values."""

    limit: float
    requests_used: float
    renews_at_utc: datetime


@dataclass
class SyntheticQuotaResult:
    """Result wrapper for Synthetic quota fetches."""

    quota: SyntheticQuota | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.quota is not None and self.error is None


def resolve_syn_api_key() -> str | None:
    """Resolve SYN_API_KEY from config/environment."""
    value = get_api_key("SYN_API_KEY")
    if not value:
        return None
    value = value.strip()
    return value or None


def _parse_renews_at(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None

    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def fetch_synthetic_quota(
    api_key: str,
    timeout_seconds: float = 15.0,
) -> SyntheticQuotaResult:
    """Fetch and validate Synthetic subscription quota status."""
    if not api_key:
        return SyntheticQuotaResult(error="SYN_API_KEY is not configured.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }

    try:
        response = requests.get(
            SYNTHETIC_QUOTAS_URL,
            headers=headers,
            timeout=timeout_seconds,
        )
    except requests.Timeout:
        return SyntheticQuotaResult(error="Synthetic API request timed out.")
    except requests.ConnectionError:
        return SyntheticQuotaResult(
            error="Could not connect to the Synthetic API endpoint."
        )
    except requests.RequestException as exc:
        return SyntheticQuotaResult(error=f"Synthetic API request failed: {exc}")

    if response.status_code in (401, 403):
        return SyntheticQuotaResult(
            error="Synthetic API authentication failed. Check SYN_API_KEY."
        )
    if response.status_code == 429:
        return SyntheticQuotaResult(
            error="Synthetic API rate limited this request (HTTP 429)."
        )
    if response.status_code >= 500:
        return SyntheticQuotaResult(
            error=f"Synthetic API server error (HTTP {response.status_code})."
        )
    if response.status_code != 200:
        detail = response.text.strip()
        if len(detail) > 200:
            detail = f"{detail[:200]}..."
        suffix = f": {detail}" if detail else ""
        return SyntheticQuotaResult(
            error=f"Synthetic API returned HTTP {response.status_code}{suffix}"
        )

    try:
        payload = response.json()
    except ValueError:
        return SyntheticQuotaResult(
            error="Synthetic API returned invalid JSON for /v2/quotas."
        )

    if not isinstance(payload, dict):
        return SyntheticQuotaResult(
            error="Synthetic API response payload is not an object."
        )

    subscription = payload.get("subscription")
    if not isinstance(subscription, dict):
        return SyntheticQuotaResult(
            error="Synthetic API response is missing 'subscription'."
        )

    try:
        limit = float(subscription.get("limit"))
        requests_used = float(subscription.get("requests"))
    except (TypeError, ValueError):
        return SyntheticQuotaResult(
            error="Synthetic API response has invalid numeric quota values."
        )

    renews_at = _parse_renews_at(subscription.get("renewsAt"))
    if renews_at is None:
        return SyntheticQuotaResult(
            error="Synthetic API response has an invalid 'renewsAt' timestamp."
        )

    return SyntheticQuotaResult(
        quota=SyntheticQuota(
            limit=limit,
            requests_used=requests_used,
            renews_at_utc=renews_at,
        )
    )
