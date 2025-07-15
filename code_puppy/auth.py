import asyncio
import time
import webbrowser
from datetime import datetime
from typing import Optional

import jwt
from rich.console import Console

from code_puppy.config import get_value

from .urls import get_authentication_url

console = Console()


def _output_message(message: str, style: str, tui_mode: bool) -> None:
    """
    Helper function to output a message either to console or message queue.

    Args:
        message: The message to output
        style: The Rich style to apply (e.g., 'green', 'red', 'dim')
        tui_mode: If True, emit to message queue; otherwise print to console
    """
    if tui_mode:
        # Import here to avoid circular imports
        from code_puppy.messaging import emit_system_message
        emit_system_message(message)
    else:
        console.print(f"[{style}]{message}[/{style}]")


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
        console.print(f"[yellow]Failed to decode JWT: {e}[/yellow]")
        return None


def is_token_expired(token: str, silent: bool = False, tui_mode: bool = False) -> bool:
    """
    Check if a JWT token is expired.
    Returns True if expired or invalid, False if still valid.

    Args:
        token: The JWT token to check
        silent: If True, suppress console output about expiration details
        tui_mode: If True, emit messages to message queue instead of console
    """
    payload = decode_jwt_without_validation(token)
    if not payload:
        return True

    # Check for 'exp' claim (expiration time)
    exp = payload.get("exp")
    if not exp:
        if not silent:
            msg = "JWT token has no expiration claim"
            _output_message(msg, "yellow", tui_mode)
        return True

    # Compare with current time (exp is typically a Unix timestamp)
    current_time = time.time()
    if current_time >= exp:
        if not silent:
            msg = "JWT token has expired"
            _output_message(msg, "yellow", tui_mode)
        return True

    # Calculate time until expiration and show it (only if not silent)
    if not silent:
        exp - current_time
        exp_datetime = datetime.fromtimestamp(exp)
        msg = f"Token expires at: {exp_datetime.strftime('%Y-%m-%d %H:%M:%S')}"
        _output_message(msg, "dim", tui_mode)

    return False


def get_puppy_token() -> Optional[str]:
    """
    Get the puppy_token from config.
    """
    return get_value("puppy_token")


def is_puppy_token_valid(tui_mode: bool = False) -> bool:
    """
    Check if the current puppy_token exists and is not expired.

    Args:
        tui_mode: If True, emit messages to message queue instead of console
    """
    token = get_puppy_token()
    if not token:
        msg = "No puppy_token found in config"
        _output_message(msg, "yellow", tui_mode)
        return False

    return not is_token_expired(token, tui_mode=tui_mode)


async def wait_for_token_update(
    initial_token: Optional[str], timeout: int = 120, tui_mode: bool = False
) -> bool:
    """
    Wait for the puppy_token to be updated (different from initial_token).
    Returns True if token was updated, False if timeout occurred.

    Args:
        initial_token: The initial token value to compare against
        timeout: How long to wait for authentication in seconds
        tui_mode: If True, emit messages to message queue instead of console
    """
    msg = f"Waiting for authentication (timeout: {timeout}s)..."
    _output_message(msg, "dim", tui_mode)

    start_time = time.time()
    while time.time() - start_time < timeout:
        current_token = get_puppy_token()

        # Check if token changed from initial state
        if current_token != initial_token:
            if current_token and not is_token_expired(current_token, silent=True, tui_mode=tui_mode):
                msg = "✓ Authentication successful!"
                _output_message(msg, "green", tui_mode)
                return True
            else:
                msg = "Received token but it's invalid or expired"
                _output_message(msg, "yellow", tui_mode)

        # Sleep a bit before checking again
        await asyncio.sleep(1)

    msg = f"Authentication timeout after {timeout}s"
    _output_message(msg, "red", tui_mode)
    return False


async def authenticate_puppy(port: int, tui_mode: bool = False) -> bool:
    """
    Execute the full authentication flow:
    1. Check if current token is valid
    2. If not, open browser for auth
    3. Wait for token to be received

    Args:
        port: The port number for authentication callback
        tui_mode: If True, emit messages to message queue instead of console

    Returns True if authentication succeeded, False otherwise.
    """
    # Check if we already have a valid token
    if is_puppy_token_valid(tui_mode=tui_mode):
        msg = "✓ Puppy token is valid!"
        _output_message(msg, "green", tui_mode)
        return True

    msg = "Puppy needs to authenticate..."
    _output_message(msg, "yellow", tui_mode)

    # Store initial token state (might be None or expired)
    initial_token = get_puppy_token()

    # Open browser for authentication
    auth_url = get_authentication_url(port=port)
    msg = f"Opening browser for authentication: {auth_url}"
    _output_message(msg, "blue", tui_mode)

    try:
        webbrowser.open(auth_url)
        msg = "Browser opened - please complete authentication"
        _output_message(msg, "dim", tui_mode)
    except Exception as e:
        msg = f"Failed to open browser: {e}"
        _output_message(msg, "red", tui_mode)
        msg = f"Please manually open: {auth_url}"
        _output_message(msg, "yellow", tui_mode)

    # Wait for the token to be updated
    success = await wait_for_token_update(initial_token, timeout=120, tui_mode=tui_mode)

    if success:
        # Double-check the final token
        final_token = get_puppy_token()
        if final_token and not is_token_expired(final_token, silent=True, tui_mode=tui_mode):
            return True
        else:
            msg = "Final token validation failed"
            _output_message(msg, "red", tui_mode)
            return False

    return False
