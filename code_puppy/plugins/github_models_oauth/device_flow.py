"""GitHub OAuth device flow implementation.

Follows the GitHub device flow (RFC 8628) as used by copilot-sdk.
No local HTTP server required — the user visits github.com/login/device
and enters a short code.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

import requests

from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

from .config import GITHUB_MODELS_OAUTH_CONFIG, get_client_id

logger = logging.getLogger(__name__)


@dataclass
class DeviceFlowResponse:
    """Response from GitHub's device code endpoint."""

    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


def start_device_flow() -> Optional[DeviceFlowResponse]:
    """Initiate the GitHub OAuth device flow.

    POST to ``github.com/login/device/code`` to obtain a device code and
    user code that the user enters at ``github.com/login/device``.
    """
    client_id = get_client_id()
    url = GITHUB_MODELS_OAUTH_CONFIG["device_code_url"]
    scope = GITHUB_MODELS_OAUTH_CONFIG["scope"]

    try:
        response = requests.post(
            url,
            data={"client_id": client_id, "scope": scope},
            headers={
                "Accept": "application/json",
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        return DeviceFlowResponse(
            device_code=data["device_code"],
            user_code=data["user_code"],
            verification_uri=data["verification_uri"],
            expires_in=int(data.get("expires_in", 900)),
            interval=int(data.get("interval", 5)),
        )
    except requests.RequestException as exc:
        logger.error("Failed to start device flow: %s", exc)
        emit_error(f"Failed to start GitHub device flow: {exc}")
        return None
    except (KeyError, ValueError) as exc:
        logger.error("Unexpected device flow response: %s", exc)
        emit_error(f"Unexpected response from GitHub: {exc}")
        return None


def poll_for_access_token(device_code: str, interval: int) -> Optional[str]:
    """Poll GitHub for an access token after the user authorises.

    Handles ``authorization_pending`` (keep trying), ``slow_down``
    (increase interval), and ``expired_token`` (give up).
    """
    client_id = get_client_id()
    url = GITHUB_MODELS_OAUTH_CONFIG["access_token_url"]
    timeout = GITHUB_MODELS_OAUTH_CONFIG["poll_timeout"]

    delay = max(1, int(interval))
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        time.sleep(delay)

        try:
            response = requests.post(
                url,
                data={
                    "client_id": client_id,
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
                headers={
                    "Accept": "application/json",
                },
                timeout=30,
            )
            data = response.json()
        except requests.RequestException as exc:
            logger.warning("Token poll request failed: %s", exc)
            continue
        except ValueError:
            logger.warning("Token poll returned non-JSON response")
            continue

        # Success
        if data.get("access_token"):
            return data["access_token"]

        error = data.get("error", "")

        if error == "authorization_pending":
            continue

        if error == "slow_down":
            delay = int(data.get("interval", delay + 5))
            continue

        if error == "expired_token":
            logger.warning("Device code expired before user authorized")
            return None

        # Unknown error — abort
        desc = data.get("error_description", error)
        logger.error("OAuth polling error: %s", desc)
        emit_error(f"GitHub OAuth error: {desc}")
        return None

    logger.warning("Device flow polling timed out after %ds", timeout)
    return None


def run_device_flow() -> Optional[str]:
    """Run the full GitHub OAuth device flow.

    Returns the access token on success, or ``None`` on failure.
    """
    emit_info("🔐 Starting GitHub OAuth device flow…")

    device = start_device_flow()
    if not device:
        return None

    emit_info(f"\n📋 Open: {device.verification_uri}")
    emit_info(f"📋 Enter code: {device.user_code}\n")

    # Try to open the browser automatically
    try:
        import webbrowser

        from code_puppy.tools.common import should_suppress_browser

        if should_suppress_browser():
            emit_info(f"[HEADLESS MODE] Would normally open: {device.verification_uri}")
        else:
            webbrowser.open(device.verification_uri)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not open browser: %s", exc)

    emit_info("⏳ Waiting for authorization (press Ctrl+C to cancel)…")

    try:
        token = poll_for_access_token(device.device_code, device.interval)
    except KeyboardInterrupt:
        emit_warning("GitHub authentication cancelled by user.")
        return None

    if token:
        emit_success("✅ GitHub authentication successful!")
        return token

    emit_error("❌ GitHub authentication failed or timed out.")
    return None
