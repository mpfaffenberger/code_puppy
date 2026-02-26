import asyncio
import subprocess
import sys
import time
import webbrowser
from typing import Optional

import jwt

from code_puppy.config import get_value
from code_puppy.messaging import (
    emit_error,
    emit_info,
    emit_success,
    emit_system_message,
    emit_warning,
)
from code_puppy.plugins.walmart_specific.urls import get_authentication_url

# =============================================================================
# Auth callback port + re-auth helpers
# =============================================================================

# The Walmart plugin starts a local HTTP server that accepts the new token.
# We store the chosen port so other modules (telemetry, safety validator, etc.)
# can re-trigger auth later without guessing.
_AUTH_CALLBACK_PORT: int | None = None

# Cooldown to avoid repeatedly launching browser windows if multiple requests
# hit 401 in quick succession.
_REAUTH_COOLDOWN_SECONDS = 30
_last_reauth_attempt_ts: float = 0.0


def set_auth_callback_port(port: int) -> None:
    """Set the local auth callback port used by authenticate_puppy()."""
    global _AUTH_CALLBACK_PORT
    _AUTH_CALLBACK_PORT = int(port)


def get_auth_callback_port() -> int | None:
    """Get the configured local auth callback port (if known)."""
    return _AUTH_CALLBACK_PORT


def reauthenticate_puppy_sync(*, reason: str = "") -> bool:
    """Synchronously re-run the puppy auth flow.

    This is designed for callers that are *not* async (e.g. telemetry thread,
    safety validator), and is safe to call on a 401.

    Returns:
        True if a new valid token is available, False otherwise.
    """
    global _last_reauth_attempt_ts

    now = time.time()
    if now - _last_reauth_attempt_ts < _REAUTH_COOLDOWN_SECONDS:
        # Don't spam the user with auth browser popups.
        return is_puppy_token_valid()

    _last_reauth_attempt_ts = now

    port = get_auth_callback_port()
    if port is None:
        emit_warning(
            "Cannot re-authenticate automatically: auth callback port unknown. "
            "Restart Code Puppy or run the auth flow again."
        )
        return False

    if reason:
        emit_warning(f"Authentication required ({reason}). Re-authenticating...")
    else:
        emit_warning("Authentication required. Re-authenticating...")

    try:
        return asyncio.run(authenticate_puppy(port))
    except RuntimeError:
        # Event loop already running somewhere (rare in sync callers).
        # Fall back to spinning a fresh loop.
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(authenticate_puppy(port))
        finally:
            loop.close()


def open_browser(url: str) -> None:
    """
    Open a URL in the browser.
    On macOS, explicitly use Chrome to avoid Safari.
    On other platforms, use the system default browser.
    """
    if sys.platform == "darwin":
        # macOS: Use Chrome explicitly to avoid Safari
        try:
            subprocess.run(
                ["open", "-a", "Google Chrome", url],
                check=True,
                capture_output=True,
            )
            return
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Chrome not available, fall back to default
            emit_warning("Chrome not found, falling back to default browser")

    # Default behavior for non-macOS or if Chrome failed
    webbrowser.open(url)


def decode_jwt_without_validation(token: str) -> Optional[dict]:
    """
    Decode a JWT token without validation to check its contents.
    Returns the payload dict or None if decoding fails.
    """
    try:
        # Decode without verification - we just want to read the expiration
        decoded = jwt.decode(token, options={"verify_signature": False})
        return decoded
    except Exception as e:
        emit_warning(f"Failed to decode JWT: {e}")
        return None


def is_token_expired(token: str, silent: bool = False) -> bool:
    """
    Check if a JWT token is expired.
    Returns True if expired or invalid, False if still valid.

    Args:
        token: The JWT token to check
        silent: If True, suppress console output about expiration details
    """
    payload = decode_jwt_without_validation(token)
    if not payload:
        return True

    # Check for 'exp' claim (expiration time)
    exp = payload.get("exp")
    if not exp:
        if not silent:
            msg = "JWT token has no expiration claim"
            emit_warning(msg)
        return True

    # Compare with current time (exp is typically a Unix timestamp)
    current_time = time.time()
    if current_time >= exp:
        if not silent:
            msg = "JWT token has expired"
            emit_warning(msg)
        return True

    return False


def get_puppy_token() -> Optional[str]:
    """
    Get the puppy_token from config.
    """
    return get_value("puppy_token")


def is_puppy_token_valid() -> bool:
    """
    Check if the current puppy_token exists and is not expired.
    """
    token = get_puppy_token()
    if not token:
        msg = "No puppy_token found in config"
        emit_warning(msg)
        return False

    return not is_token_expired(token)


async def wait_for_token_update(
    initial_token: Optional[str], timeout: int = 120
) -> bool:
    """
    Wait for the puppy_token to be updated (different from initial_token).
    Returns True if token was updated, False if timeout occurred.

    Args:
        initial_token: The initial token value to compare against
        timeout: How long to wait for authentication in seconds
    """
    msg = f"Waiting for authentication (timeout: {timeout}s)..."
    emit_system_message(msg)

    start_time = time.time()
    while time.time() - start_time < timeout:
        current_token = get_puppy_token()

        # Check if token changed from initial state
        if current_token != initial_token:
            if current_token and not is_token_expired(current_token, silent=True):
                msg = "✓ Authentication successful!"
                emit_success(msg)
                return True
            else:
                msg = "Received token but it's invalid or expired"
                emit_warning(msg)

        # Sleep a bit before checking again
        await asyncio.sleep(1)

    msg = f"Authentication timeout after {timeout}s"
    emit_error(msg)
    return False


async def authenticate_puppy(port: int) -> bool:
    """
    Execute the full authentication flow:
    1. Check if current token is valid
    2. If not, open browser for auth
    3. Wait for token to be received

    Args:
        port: The port number for authentication callback

    Returns True if authentication succeeded, False otherwise.
    """
    # Check if we already have a valid token
    if is_puppy_token_valid():
        return True

    msg = "Puppy needs to authenticate..."
    emit_warning(msg)

    # Store initial token state (might be None or expired)
    initial_token = get_puppy_token()

    # Open browser for authentication
    auth_url = get_authentication_url(port=port)
    msg = f"Opening browser for authentication: {auth_url}"
    emit_info(msg)

    try:
        open_browser(auth_url)
        msg = "Browser opened - please complete authentication"
        emit_system_message(msg)
    except Exception as e:
        msg = f"Failed to open browser: {e}"
        emit_error(msg)
        msg = f"Please manually open: {auth_url}"
        emit_warning(msg)

    # Wait for the token to be updated
    success = await wait_for_token_update(initial_token, timeout=120)

    if success:
        # Double-check the final token
        final_token = get_puppy_token()
        if final_token and not is_token_expired(final_token, silent=True):
            return True
        else:
            msg = "Final token validation failed"
            emit_error(msg)
            return False

    return False
