"""Version checking utilities for Code Puppy."""

import httpx

from code_puppy.messaging import emit_info, emit_success, emit_warning, get_message_bus
from code_puppy.messaging.messages import VersionCheckMessage


def normalize_version(version_str):
    if not version_str:
        return version_str
    return version_str.lstrip("v")


def versions_are_equal(current, latest):
    return normalize_version(current) == normalize_version(latest)


def fetch_latest_version(package_name):
    try:
        response = httpx.get(f"https://pypi.org/pypi/{package_name}/json", timeout=5.0)
        response.raise_for_status()
        data = response.json()
        return data["info"]["version"]
    except Exception as e:
        emit_warning(f"Error fetching version: {e}")
        return None


def default_version_mismatch_behavior(current_version):
    # Defensive: ensure current_version is never None
    if current_version is None:
        current_version = "0.0.0-unknown"
        emit_warning("Could not detect current version, using fallback")

    latest_version = fetch_latest_version("code-puppy")

    update_available = bool(latest_version and latest_version != current_version)

    # Emit structured version check message
    version_msg = VersionCheckMessage(
        current_version=current_version,
        latest_version=latest_version or current_version,
        update_available=update_available,
    )
    get_message_bus().emit(version_msg)

    # Also emit plain text for legacy renderer
    emit_info(f"Current version: {current_version}")

    if update_available:
        emit_info(f"Latest version: {latest_version}")
        emit_warning(f"A new version of code puppy is available: {latest_version}")
        emit_success("Please consider updating!")
