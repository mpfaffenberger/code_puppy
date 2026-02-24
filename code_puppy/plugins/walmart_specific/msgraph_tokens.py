"""Microsoft Graph token lifecycle management.

Handles token storage, expiration checking, refresh, and validation.
Separated from the OAuth flow (msgraph_auth.py) to keep modules focused.

See Also:
    msgraph_auth.py - OAuth 2.0 browser-based authentication flow.
    msgraph_client.py - HTTP client that consumes tokens from this module.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from code_puppy.config import CONFIG_DIR
from code_puppy.messaging import emit_info, emit_warning


# =============================================================================
# CONSTANTS
# =============================================================================

# Graph Explorer's client ID - this is public, registered by Microsoft
GRAPH_EXPLORER_CLIENT_ID: str = "de8bc8b5-d9f9-48b1-a8ad-b748da725064"

# Azure AD token endpoint (using /common for multi-tenant)
AZURE_AD_TOKEN_URL: str = "https://login.microsoftonline.com/common/oauth2/v2.0/token"

# Microsoft Graph API base URL
MSGRAPH_API_BASE: str = "https://graph.microsoft.com/v1.0"

# Token storage path
MSGRAPH_TOKENS_FILE: Path = Path(CONFIG_DIR) / "msgraph.json"

# Refresh proactively 5 minutes before actual expiry to avoid edge-case races
_EXPIRY_BUFFER_SECONDS: int = 300


# =============================================================================
# TOKEN STORAGE
# =============================================================================


def save_tokens(tokens: dict[str, Any]) -> None:
    """Save tokens to the tokens file."""
    emit_info(f"\U0001f4be Saving tokens to {MSGRAPH_TOKENS_FILE}...")
    MSGRAPH_TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(MSGRAPH_TOKENS_FILE, "w") as f:
        json.dump(tokens, f, indent=2)


def load_tokens() -> dict[str, Any]:
    """Load tokens from the tokens file.

    Raises:
        FileNotFoundError: If the tokens file does not exist.
        json.JSONDecodeError: If the tokens file is not valid JSON.
    """
    with open(MSGRAPH_TOKENS_FILE) as f:
        return json.load(f)


# =============================================================================
# TOKEN EXPIRATION
# =============================================================================


def is_token_expired(tokens: dict[str, Any]) -> bool:
    """Check if the access token has expired based on stored metadata.

    Uses the stored timestamp and expires_in to determine expiry locally
    without making a network call.

    Args:
        tokens: Token dict with 'timestamp' and 'expires_in' keys.

    Returns:
        True if the token is expired or expiring within the buffer window.
    """
    timestamp_str = tokens.get("timestamp")
    expires_in = tokens.get("expires_in", 3600)

    if not timestamp_str:
        # No timestamp stored — assume expired to be safe
        return True

    try:
        issued_at = datetime.fromisoformat(timestamp_str)
        expires_at = issued_at + timedelta(seconds=expires_in)
        # Refresh early by the buffer amount
        return datetime.now() >= expires_at - timedelta(seconds=_EXPIRY_BUFFER_SECONDS)
    except (ValueError, TypeError):
        # Malformed timestamp — assume expired
        return True


# =============================================================================
# TOKEN REFRESH
# =============================================================================


def refresh_access_token(refresh_token: str) -> dict[str, Any] | None:
    """Attempt to refresh the access token using refresh token.

    Args:
        refresh_token: The refresh token.

    Returns:
        New token dict if successful, None if refresh failed.
    """
    try:
        token_data = {
            "client_id": GRAPH_EXPLORER_CLIENT_ID,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                AZURE_AD_TOKEN_URL,
                data=token_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code == 200:
                token_response = response.json()
                emit_info("\U0001f504 Token refreshed successfully.")
                return {
                    "access_token": token_response["access_token"],
                    "refresh_token": token_response.get("refresh_token", refresh_token),
                    "expires_in": token_response.get("expires_in", 3600),
                    "timestamp": datetime.now().isoformat(),
                }

            # Log the actual failure reason instead of silently swallowing it
            emit_warning(
                f"\u26a0\ufe0f Token refresh failed (HTTP {response.status_code}): "
                f"{response.text[:200]}"
            )
    except Exception as e:
        emit_warning(f"\u26a0\ufe0f Token refresh request failed: {e}")

    return None


# =============================================================================
# TOKEN VALIDATION & RETRIEVAL
# =============================================================================


def get_valid_access_token() -> str | None:
    """Get a valid access token, attempting refresh if needed.

    Strategy:
        1. Check local expiration first (no network call).
        2. If expired, try refreshing with the refresh token.
        3. If not expired, validate with a quick /me call.
        4. If validation fails (401/403), try refreshing.
        5. If all else fails, return None to force re-auth.

    Returns:
        Access token string, or None if not authenticated.
    """
    if not MSGRAPH_TOKENS_FILE.exists():
        return None

    try:
        tokens = load_tokens()
    except (json.JSONDecodeError, OSError) as e:
        emit_warning(f"\u26a0\ufe0f Failed to load msgraph tokens: {e}")
        return None

    access_token = tokens.get("access_token")
    if not access_token:
        return None

    refresh_token_val = tokens.get("refresh_token")

    # --- Step 1: Local expiration check (avoids unnecessary network call) ---
    if is_token_expired(tokens):
        emit_info("\U0001f550 Access token expired locally, attempting refresh...")
        if refresh_token_val:
            new_tokens = refresh_access_token(refresh_token_val)
            if new_tokens:
                save_tokens(new_tokens)
                return new_tokens["access_token"]
        # Refresh failed or no refresh token — force re-auth
        emit_warning(
            "\u26a0\ufe0f Token expired and refresh failed. "
            "Re-authentication required (/msgraph_auth)."
        )
        return None

    # --- Step 2: Network validation (token not locally expired) ---
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                f"{MSGRAPH_API_BASE}/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if response.status_code == 200:
                return access_token

            # Token rejected (401 expired, 403 scope change) — try refresh
            if response.status_code in (401, 403):
                status_reason = (
                    "expired" if response.status_code == 401 else "insufficient scope"
                )
                emit_warning(
                    f"\u26a0\ufe0f Token validation returned {response.status_code} "
                    f"({status_reason}), attempting refresh..."
                )
                if refresh_token_val:
                    new_tokens = refresh_access_token(refresh_token_val)
                    if new_tokens:
                        save_tokens(new_tokens)
                        return new_tokens["access_token"]
                # Refresh failed — force re-auth
                emit_warning(
                    "\u26a0\ufe0f Token refresh failed after API rejection. "
                    "Re-authentication required (/msgraph_auth)."
                )
                return None

            # Other HTTP errors (5xx, etc.) — don't return stale token
            emit_warning(
                f"\u26a0\ufe0f Token validation returned unexpected "
                f"HTTP {response.status_code}. "
                f"Not returning potentially stale token."
            )
            return None

    except Exception as e:
        # Network error during validation — don't silently return stale token
        emit_warning(f"\u26a0\ufe0f Token validation network error: {e}")
        # Try refresh as a fallback for network issues
        if refresh_token_val:
            emit_info("\U0001f504 Attempting token refresh after validation failure...")
            new_tokens = refresh_access_token(refresh_token_val)
            if new_tokens:
                save_tokens(new_tokens)
                return new_tokens["access_token"]
        emit_warning(
            "\u26a0\ufe0f Could not validate or refresh token. "
            "Re-authentication required (/msgraph_auth)."
        )
        return None
