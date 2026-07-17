"""Runtime helpers for the Gemini OAuth (Code Assist) plugin.

Reads credentials written by the Gemini CLI from ~/.gemini/oauth_creds.json
and refreshes them automatically when they expire.
"""

from __future__ import annotations

import json
import logging
import os
import time

logger = logging.getLogger(__name__)

_CREDS_PATH = os.path.expanduser("~/.gemini/oauth_creds.json")
_PROJECTS_PATH = os.path.expanduser("~/.gemini/projects.json")

# Public installed-app client_id shipped by the Gemini CLI. Not a secret.
# The client_secret is read from the environment (see config.py / README);
# we don't commit the ``GOCSPX-`` literal so GitHub push protection stays happy.
_CLIENT_ID = os.environ.get(
    "GEMINI_OAUTH_CLIENT_ID",
    "681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j.apps.googleusercontent.com",
)
_CLIENT_SECRET = os.environ.get("GEMINI_OAUTH_CLIENT_SECRET", "")
_TOKEN_URI = "https://oauth2.googleapis.com/token"

# Refresh the token this many seconds before it actually expires
_BUFFER_SECONDS = 300


def _load_creds() -> dict | None:
    if not os.path.exists(_CREDS_PATH):
        logger.warning(
            "Gemini OAuth credentials not found at %s. "
            "Run the Gemini CLI once to authenticate: gemini",
            _CREDS_PATH,
        )
        return None
    try:
        with open(_CREDS_PATH) as f:
            return json.load(f)
    except Exception as exc:
        logger.error("Failed to read Gemini credentials: %s", exc)
        return None


def _save_creds(creds: dict) -> None:
    try:
        with open(_CREDS_PATH, "w") as f:
            json.dump(creds, f)
        os.chmod(_CREDS_PATH, 0o600)
    except Exception as exc:
        logger.warning("Failed to save refreshed Gemini credentials: %s", exc)


def _is_expired(creds: dict) -> bool:
    expiry = creds.get("expiry_date", 0)
    # Gemini CLI stores expiry_date in milliseconds
    if expiry > 1_000_000_000_000:
        return time.time() > (expiry / 1000) - _BUFFER_SECONDS
    # Fallback: treat as seconds
    return time.time() > expiry - _BUFFER_SECONDS


def _refresh_token(refresh_token: str) -> dict | None:
    if not _CLIENT_SECRET:
        logger.error(
            "Cannot refresh the Gemini token: GEMINI_OAUTH_CLIENT_SECRET is not "
            "set. Either export it (see the plugin README for the public "
            "Gemini CLI value) or re-run `gemini` to refresh ~/.gemini/oauth_creds.json."
        )
        return None
    try:
        import httpx

        resp = httpx.post(
            _TOKEN_URI,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": _CLIENT_ID,
                "client_secret": _CLIENT_SECRET,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.error("Gemini token refresh failed: %s", exc)
        return None


def get_valid_access_token() -> str | None:
    """Return a valid Google access token, refreshing from ~/.gemini/oauth_creds.json if needed."""
    creds = _load_creds()
    if not creds:
        return None

    if _is_expired(creds):
        refresh_token = creds.get("refresh_token")
        if not refresh_token:
            logger.error(
                "Gemini OAuth token is expired and no refresh_token is available. "
                "Re-authenticate by running: gemini"
            )
            return None

        logger.info("Gemini OAuth token expired — refreshing...")
        new_tokens = _refresh_token(refresh_token)
        if not new_tokens:
            logger.error(
                "Token refresh failed. Re-authenticate by running: gemini"
            )
            return None

        creds["access_token"] = new_tokens["access_token"]
        if "expires_in" in new_tokens:
            creds["expiry_date"] = int((time.time() + new_tokens["expires_in"]) * 1000)
        if "refresh_token" in new_tokens:
            creds["refresh_token"] = new_tokens["refresh_token"]
        _save_creds(creds)
        logger.info("Gemini OAuth token refreshed successfully")

    token = creds.get("access_token")
    if not token:
        logger.error("Gemini credentials file has no access_token field")
        return None
    return token


_PROJECT_CACHE_PATH = os.path.expanduser("~/.gemini/code_assist_project.json")
_LOAD_CODE_ASSIST_URL = "https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist"


def _fetch_managed_project_id(access_token: str) -> str | None:
    """Call the Code Assist loadCodeAssist endpoint to get the managed project ID."""
    try:
        import httpx

        resp = httpx.post(
            _LOAD_CODE_ASSIST_URL,
            json={
                "metadata": {
                    "ideType": "IDE_UNSPECIFIED",
                    "platform": "PLATFORM_UNSPECIFIED",
                    "pluginType": "GEMINI",
                }
            },
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        project_id = data.get("cloudaicompanionProject")
        if project_id:
            # Cache so we don't call the API on every request
            try:
                with open(_PROJECT_CACHE_PATH, "w") as f:
                    json.dump({"project_id": project_id}, f)
                os.chmod(_PROJECT_CACHE_PATH, 0o600)
            except Exception:
                pass
        return project_id
    except Exception as exc:
        logger.error("Failed to fetch Code Assist project ID: %s", exc)
        return None


def get_project_id() -> str | None:
    """Return the Google Cloud project ID assigned by Code Assist for this account.

    On first call, queries the Code Assist API (loadCodeAssist) to discover the
    managed project, then caches it in ~/.gemini/code_assist_project.json.
    """
    # Try cached value first
    if os.path.exists(_PROJECT_CACHE_PATH):
        try:
            with open(_PROJECT_CACHE_PATH) as f:
                cached = json.load(f)
            project_id = cached.get("project_id")
            if project_id:
                return project_id
        except Exception:
            pass

    # Fetch from the API
    token = get_valid_access_token()
    if not token:
        return None
    return _fetch_managed_project_id(token)
