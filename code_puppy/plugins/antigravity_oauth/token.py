"""Token management for Antigravity OAuth."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

import requests

from .constants import ANTIGRAVITY_CLIENT_ID, ANTIGRAVITY_CLIENT_SECRET

logger = logging.getLogger(__name__)

# Buffer before expiry to trigger refresh (60 seconds)
ACCESS_TOKEN_EXPIRY_BUFFER_MS = 60 * 1000


@dataclass
class RefreshParts:
    """Parsed components of a stored refresh token string."""

    refresh_token: str
    project_id: Optional[str] = None
    managed_project_id: Optional[str] = None


@dataclass
class OAuthTokens:
    """OAuth token data."""

    access_token: str
    refresh_token: str  # Composite: "token|projectId|managedProjectId"
    expires_at: float  # Unix timestamp
    email: Optional[str] = None


class TokenRefreshError(Exception):
    """Error during token refresh."""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        status: Optional[int] = None,
    ):
        super().__init__(message)
        self.code = code
        self.status = status


def parse_refresh_parts(refresh: str) -> RefreshParts:
    """Split a packed refresh string into its components."""
    parts = (refresh or "").split("|")
    return RefreshParts(
        refresh_token=parts[0] if len(parts) > 0 else "",
        project_id=parts[1] if len(parts) > 1 and parts[1] else None,
        managed_project_id=parts[2] if len(parts) > 2 and parts[2] else None,
    )


def format_refresh_parts(parts: RefreshParts) -> str:
    """Serialize refresh token parts into the stored string format."""
    project_segment = parts.project_id or ""
    base = f"{parts.refresh_token}|{project_segment}"
    if parts.managed_project_id:
        return f"{base}|{parts.managed_project_id}"
    return base


def is_token_expired(expires_at: Optional[float]) -> bool:
    """Check if a token is expired or missing, with buffer for clock skew."""
    if expires_at is None:
        return True
    # Convert buffer to seconds
    buffer_seconds = ACCESS_TOKEN_EXPIRY_BUFFER_MS / 1000
    return expires_at <= time.time() + buffer_seconds


def refresh_access_token(
    refresh_token_composite: str,
    current_access: Optional[str] = None,
    current_expires: Optional[float] = None,
) -> Optional[OAuthTokens]:
    """Refresh an Antigravity OAuth access token.

    Args:
        refresh_token_composite: The stored refresh token (may include project IDs)
        current_access: Current access token (for returning if refresh fails non-fatally)
        current_expires: Current expiry time

    Returns:
        Updated OAuthTokens or None if refresh failed

    Raises:
        TokenRefreshError: If refresh fails due to revoked token
    """
    parts = parse_refresh_parts(refresh_token_composite)

    if not parts.refresh_token:
        return None

    try:
        response = requests.post(
            "https://oauth2.googleapis.com/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "refresh_token",
                "refresh_token": parts.refresh_token,
                "client_id": ANTIGRAVITY_CLIENT_ID,
                "client_secret": ANTIGRAVITY_CLIENT_SECRET,
            },
            timeout=30,
        )

        if not response.ok:
            error_data = {}
            try:
                error_data = response.json()
            except Exception:
                pass

            error_code = error_data.get("error", "")
            error_desc = error_data.get("error_description", response.text)

            if error_code == "invalid_grant":
                logger.warning(
                    "Google revoked the stored refresh token - reauthentication required"
                )
                raise TokenRefreshError(
                    f"Token revoked: {error_desc}",
                    code="invalid_grant",
                    status=response.status_code,
                )

            logger.warning(
                "Token refresh failed: %s %s - %s",
                response.status_code,
                error_code,
                error_desc,
            )
            return None

        payload = response.json()
        new_access = payload.get("access_token", "")
        expires_in = payload.get("expires_in", 3600)
        new_refresh = payload.get("refresh_token", parts.refresh_token)

        # Rebuild composite refresh token
        updated_parts = RefreshParts(
            refresh_token=new_refresh,
            project_id=parts.project_id,
            managed_project_id=parts.managed_project_id,
        )

        return OAuthTokens(
            access_token=new_access,
            refresh_token=format_refresh_parts(updated_parts),
            expires_at=time.time() + expires_in,
        )

    except TokenRefreshError:
        raise
    except Exception as e:
        logger.exception("Unexpected token refresh error: %s", e)
        return None
