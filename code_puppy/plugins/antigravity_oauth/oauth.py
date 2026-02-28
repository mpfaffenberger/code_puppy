"""Core OAuth flow implementation for Antigravity authentication."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import urlencode

import requests

from .constants import (
    ANTIGRAVITY_CLIENT_ID,
    ANTIGRAVITY_CLIENT_SECRET,
    ANTIGRAVITY_ENDPOINT_FALLBACKS,
    ANTIGRAVITY_HEADERS,
    ANTIGRAVITY_LOAD_ENDPOINTS,
    ANTIGRAVITY_SCOPES,
)

logger = logging.getLogger(__name__)


@dataclass
class OAuthContext:
    """Runtime state for an in-progress OAuth flow."""

    state: str
    code_verifier: str
    code_challenge: str
    redirect_uri: Optional[str] = None


@dataclass
class AntigravityAuthorization:
    """Result returned after constructing an OAuth authorization URL."""

    url: str
    verifier: str
    project_id: str


@dataclass
class TokenExchangeSuccess:
    """Successful token exchange result."""

    refresh_token: str
    access_token: str
    expires_at: float  # Unix timestamp
    email: Optional[str]
    project_id: str


@dataclass
class TokenExchangeFailure:
    """Failed token exchange result."""

    error: str


TokenExchangeResult = TokenExchangeSuccess | TokenExchangeFailure


def _urlsafe_b64encode(data: bytes) -> str:
    """Encode bytes to URL-safe base64 without padding."""
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _generate_code_verifier() -> str:
    """Generate a cryptographically secure code verifier for PKCE."""
    return _urlsafe_b64encode(secrets.token_bytes(64))


def _compute_code_challenge(code_verifier: str) -> str:
    """Compute the S256 code challenge from the verifier."""
    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    return _urlsafe_b64encode(digest)


def _encode_state(verifier: str, project_id: str = "") -> str:
    """Encode OAuth state as URL-safe base64."""
    payload = {"verifier": verifier, "projectId": project_id}
    return (
        base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8"))
        .decode("utf-8")
        .rstrip("=")
    )


def _decode_state(state: str) -> tuple[str, str]:
    """Decode OAuth state back to verifier and project ID."""
    # Normalize base64 encoding
    normalized = state.replace("-", "+").replace("_", "/")
    padding = (4 - len(normalized) % 4) % 4
    padded = normalized + "=" * padding

    try:
        json_str = base64.b64decode(padded).decode("utf-8")
        parsed = json.loads(json_str)

        verifier = parsed.get("verifier", "")
        if not isinstance(verifier, str) or not verifier:
            raise ValueError("Missing PKCE verifier in state")

        project_id = parsed.get("projectId", "")
        if not isinstance(project_id, str):
            project_id = ""

        return verifier, project_id
    except Exception as e:
        logger.error("Failed to decode OAuth state: %s", e)
        raise ValueError(f"Invalid OAuth state: {e}") from e


def prepare_oauth_context() -> OAuthContext:
    """Create a new OAuth PKCE context."""
    state = secrets.token_urlsafe(32)
    code_verifier = _generate_code_verifier()
    code_challenge = _compute_code_challenge(code_verifier)

    return OAuthContext(
        state=state,
        code_verifier=code_verifier,
        code_challenge=code_challenge,
    )


def assign_redirect_uri(context: OAuthContext, port: int) -> str:
    """Assign redirect URI for the given OAuth context."""
    redirect_uri = f"http://localhost:{port}/oauth-callback"
    context.redirect_uri = redirect_uri
    return redirect_uri


def build_authorization_url(context: OAuthContext, project_id: str = "") -> str:
    """Build the Google OAuth authorization URL with PKCE parameters."""
    if not context.redirect_uri:
        raise RuntimeError("Redirect URI has not been assigned")

    # Encode state with verifier for callback verification
    state = _encode_state(context.code_verifier, project_id)

    params = {
        "client_id": ANTIGRAVITY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": context.redirect_uri,
        "scope": " ".join(ANTIGRAVITY_SCOPES),
        "code_challenge": context.code_challenge,
        "code_challenge_method": "S256",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }

    return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"


def _onboard_user(
    access_token: str,
    tier_id: str = "free-tier",
    gcp_project_id: str = "",
) -> str:
    """Onboard user to get a managed project ID.

    Args:
        access_token: OAuth access token
        tier_id: Tier to onboard with ("free-tier" or "standard-tier")
        gcp_project_id: Required for standard-tier - user's GCP project ID
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        **ANTIGRAVITY_HEADERS,
    }

    request_body: dict = {
        "tierId": tier_id,
        "metadata": {
            "ideType": "IDE_UNSPECIFIED",
            "platform": "PLATFORM_UNSPECIFIED",
            "pluginType": "GEMINI",
        },
    }

    # For standard tier, add the user's GCP project ID
    if tier_id == "standard-tier" and gcp_project_id:
        request_body["cloudaicompanionProject"] = {"id": gcp_project_id}

    for base_endpoint in ANTIGRAVITY_ENDPOINT_FALLBACKS:
        for _attempt in range(5):  # Retry up to 5 times
            try:
                url = f"{base_endpoint}/v1internal:onboardUser"
                response = requests.post(
                    url,
                    headers=headers,
                    json=request_body,
                    timeout=30,
                )

                if not response.ok:
                    logger.debug(
                        "onboardUser failed: %d %s",
                        response.status_code,
                        response.text[:200],
                    )
                    break

                data = response.json()

                # Check if onboarding is complete
                if data.get("done"):
                    project_id = (
                        data.get("response", {})
                        .get("cloudaicompanionProject", {})
                        .get("id")
                    )
                    if project_id:
                        logger.debug("Onboarding complete, project_id: %s", project_id)
                        return project_id

                # Wait and retry if not done
                import time

                time.sleep(3)

            except Exception as e:
                logger.debug("onboardUser error: %s", e)
                break

    return ""


@dataclass
class AntigravityStatus:
    """Status information from Antigravity API."""

    project_id: str = ""
    current_tier: str = ""
    allowed_tiers: List[str] = field(default_factory=list)
    is_onboarded: bool = False
    error: Optional[str] = None


def fetch_antigravity_status(access_token: str) -> AntigravityStatus:
    """Fetch full status from Antigravity loadCodeAssist API."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "User-Agent": "google-api-nodejs-client/9.15.1",
        "X-Goog-Api-Client": "google-cloud-sdk vscode_cloudshelleditor/0.1",
        "Client-Metadata": ANTIGRAVITY_HEADERS["Client-Metadata"],
    }

    endpoints = list(
        dict.fromkeys(ANTIGRAVITY_LOAD_ENDPOINTS + list(ANTIGRAVITY_ENDPOINT_FALLBACKS))
    )

    for base_endpoint in endpoints:
        try:
            url = f"{base_endpoint}/v1internal:loadCodeAssist"
            response = requests.post(
                url,
                headers=headers,
                json={
                    "metadata": {
                        "ideType": "IDE_UNSPECIFIED",
                        "platform": "PLATFORM_UNSPECIFIED",
                        "pluginType": "GEMINI",
                    }
                },
                timeout=30,
            )

            if not response.ok:
                continue

            data = response.json()

            # Extract project info
            project_id = ""
            project = data.get("cloudaicompanionProject")
            if isinstance(project, str) and project:
                project_id = project
            elif isinstance(project, dict) and project.get("id"):
                project_id = project["id"]

            # Extract tier info
            allowed_tiers_data = data.get("allowedTiers", [])
            allowed_tier_ids = [
                t.get("id", "") for t in allowed_tiers_data if t.get("id")
            ]

            # Find current tier (the one marked as default or the one with project)
            current_tier = ""
            for tier in allowed_tiers_data:
                if tier.get("isDefault"):
                    current_tier = tier.get("id", "")
                    break
                # If project exists and tier doesn't require user-defined project, it's likely current
                if project_id and not tier.get("userDefinedCloudaicompanionProject"):
                    current_tier = tier.get("id", "")

            return AntigravityStatus(
                project_id=project_id,
                current_tier=current_tier,
                allowed_tiers=allowed_tier_ids,
                is_onboarded=bool(project_id),
            )

        except Exception:
            continue

    return AntigravityStatus(error="Could not reach Antigravity API")


def _fetch_project_id(access_token: str) -> str:
    """Fetch project ID from Antigravity loadCodeAssist API."""
    errors: List[str] = []

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "User-Agent": "google-api-nodejs-client/9.15.1",
        "X-Goog-Api-Client": "google-cloud-sdk vscode_cloudshelleditor/0.1",
        "Client-Metadata": ANTIGRAVITY_HEADERS["Client-Metadata"],
    }

    # Try each endpoint in order (deduplicated)
    endpoints = list(
        dict.fromkeys(ANTIGRAVITY_LOAD_ENDPOINTS + list(ANTIGRAVITY_ENDPOINT_FALLBACKS))
    )

    # First, try to get existing project from loadCodeAssist
    allowed_tiers: List[dict] = []

    for base_endpoint in endpoints:
        try:
            url = f"{base_endpoint}/v1internal:loadCodeAssist"
            response = requests.post(
                url,
                headers=headers,
                json={
                    "metadata": {
                        "ideType": "IDE_UNSPECIFIED",
                        "platform": "PLATFORM_UNSPECIFIED",
                        "pluginType": "GEMINI",
                    }
                },
                timeout=30,
            )

            if not response.ok:
                errors.append(
                    f"loadCodeAssist {response.status_code} at {base_endpoint}: "
                    f"{response.text[:200]}"
                )
                continue

            data = response.json()

            # Try to extract project ID from response
            project = data.get("cloudaicompanionProject")

            if isinstance(project, str) and project:
                return project
            if isinstance(project, dict) and project.get("id"):
                return project["id"]

            # Store allowed tiers for potential onboarding
            if data.get("allowedTiers"):
                allowed_tiers = data.get("allowedTiers", [])

            errors.append(f"loadCodeAssist missing project id at {base_endpoint}")

        except Exception as e:
            errors.append(f"loadCodeAssist error at {base_endpoint}: {e}")

    # No project found - try to onboard with free tier if available
    if allowed_tiers:
        # Find the default tier or free tier
        default_tier = None
        for tier in allowed_tiers:
            if tier.get("isDefault"):
                default_tier = tier
                break
            if tier.get("id") == "free-tier":
                default_tier = tier

        if default_tier and not default_tier.get("userDefinedCloudaicompanionProject"):
            tier_id = default_tier.get("id", "free-tier")
            logger.debug(
                "No project found, attempting onboarding with tier: %s", tier_id
            )
            project_id = _onboard_user(access_token, tier_id)
            if project_id:
                return project_id

    if errors:
        logger.debug(
            "Could not resolve Antigravity project (non-fatal): %s", "; ".join(errors)
        )

    return ""


def exchange_code_for_tokens(
    code: str,
    state: str,
    redirect_uri: str,
) -> TokenExchangeResult:
    """Exchange an authorization code for Antigravity OAuth tokens."""
    try:
        # Decode and verify state
        verifier, project_id = _decode_state(state)

        # Exchange code for tokens
        response = requests.post(
            "https://oauth2.googleapis.com/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "client_id": ANTIGRAVITY_CLIENT_ID,
                "client_secret": ANTIGRAVITY_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
                "code_verifier": verifier,
            },
            timeout=30,
        )

        if not response.ok:
            return TokenExchangeFailure(error=response.text)

        token_data = response.json()
        access_token = token_data.get("access_token", "")
        refresh_token = token_data.get("refresh_token", "")
        expires_in = token_data.get("expires_in", 3600)

        if not refresh_token:
            return TokenExchangeFailure(error="Missing refresh token in response")

        # Fetch user email
        email: Optional[str] = None
        try:
            user_response = requests.get(
                "https://www.googleapis.com/oauth2/v1/userinfo?alt=json",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
            if user_response.ok:
                email = user_response.json().get("email")
        except Exception as e:
            logger.warning("Failed to fetch user email: %s", e)

        # Try to get project ID if not provided
        effective_project_id = project_id
        if not effective_project_id:
            effective_project_id = _fetch_project_id(access_token)

        # Format refresh token with project ID
        stored_refresh = f"{refresh_token}|{effective_project_id or ''}"

        return TokenExchangeSuccess(
            refresh_token=stored_refresh,
            access_token=access_token,
            expires_at=time.time() + expires_in,
            email=email,
            project_id=effective_project_id or "",
        )

    except Exception as e:
        logger.exception("Token exchange failed")
        return TokenExchangeFailure(error=str(e))
