"""Interactive Meta Muse device-code OAuth flow."""

from __future__ import annotations

import time
import webbrowser
from typing import Any

from code_puppy.i18n import t
from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning
from code_puppy.tools.common import should_suppress_browser

from .config import META_OAUTH_CONFIG
from .utils import (
    discover_models,
    load_credentials,
    mint_api_credentials,
    poll_device_token,
    request_device_authorization,
    save_credentials,
)


def _open_verification_page(url: str) -> None:
    if should_suppress_browser():
        emit_info(t("oauth.meta.browser.headless", url=url))
        return
    try:
        if not webbrowser.open(url):
            emit_warning(t("oauth.meta.browser.manual", url=url))
    except Exception as exc:  # noqa: BLE001
        emit_warning(t("oauth.meta.browser.failed", error=str(exc), url=url))


def _poll_for_access_token(device: dict[str, Any]) -> dict[str, Any] | None:
    interval = max(int(device.get("interval") or 5), 1)
    lifetime = min(
        max(int(device.get("expires_in") or 900), 60),
        int(META_OAUTH_CONFIG["poll_timeout"]),
    )
    deadline = time.monotonic() + lifetime

    while time.monotonic() < deadline:
        state, payload = poll_device_token(str(device["device_code"]))
        if state == "authorized":
            return payload
        if state == "slow_down":
            interval += 5
        elif state == "access_denied":
            emit_error(t("oauth.meta.auth.denied"))
            return None
        elif state == "expired_token":
            break
        elif state != "authorization_pending":
            emit_error(t("oauth.meta.auth.failed", error=state))
            return None
        time.sleep(interval)

    emit_error(t("oauth.meta.auth.expired"))
    return None


def run_oauth_flow() -> bool:
    """Authenticate a Meta account, mint a Model API key, and save it."""
    existing = load_credentials()
    if existing and existing.get("api_key"):
        emit_warning(t("oauth.meta.auth.overwrite"))

    try:
        device = request_device_authorization()
    except Exception as exc:  # noqa: BLE001
        emit_error(t("oauth.meta.auth.start_failed", error=str(exc)))
        return False

    url = str(
        device.get("verification_uri_complete") or device.get("verification_uri") or ""
    )
    code = str(device.get("user_code") or "")
    if not url or not code or not device.get("device_code"):
        emit_error(t("oauth.meta.auth.invalid_response"))
        return False

    emit_info(t("oauth.meta.auth.open", url=url))
    emit_info(t("oauth.meta.auth.code", code=code))
    _open_verification_page(url)
    emit_info(t("oauth.meta.auth.waiting"))

    try:
        token_payload = _poll_for_access_token(device)
        if not token_payload:
            return False
        access_token = str(token_payload.get("access_token") or "")
        if not access_token:
            raise RuntimeError(t("oauth.meta.auth.no_access_token"))

        credentials = mint_api_credentials(access_token)
        credentials["access_token"] = access_token
        credentials["refresh_token"] = token_payload.get("refresh_token", "")
        credentials["obtained_via"] = "device_code"
        credentials["models"] = discover_models(credentials)
        if not save_credentials(credentials):
            emit_error(t("oauth.meta.auth.save_failed"))
            return False
    except Exception as exc:  # noqa: BLE001
        emit_error(t("oauth.meta.auth.failed", error=str(exc)))
        return False

    emit_success(t("oauth.meta.auth.success"))
    return True
