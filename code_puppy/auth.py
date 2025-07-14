import asyncio
import time
import webbrowser
from datetime import datetime
from typing import Optional

import jwt
from rich.console import Console

from code_puppy.config import get_value

console = Console()


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
            console.print("[yellow]JWT token has no expiration claim[/yellow]")
        return True

    # Compare with current time (exp is typically a Unix timestamp)
    current_time = time.time()
    if current_time >= exp:
        if not silent:
            console.print("[yellow]JWT token has expired[/yellow]")
        return True

    # Calculate time until expiration and show it (only if not silent)
    if not silent:
        time_until_exp = exp - current_time
        exp_datetime = datetime.fromtimestamp(exp)
        console.print(
            f"[dim]Token expires at: {exp_datetime.strftime('%Y-%m-%d %H:%M:%S')}[/dim]"
        )

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
        console.print("[yellow]No puppy_token found in config[/yellow]")
        return False

    return not is_token_expired(token)


async def wait_for_token_update(
    initial_token: Optional[str], timeout: int = 120
) -> bool:
    """
    Wait for the puppy_token to be updated (different from initial_token).
    Returns True if token was updated, False if timeout occurred.
    """
    console.print(f"[dim]Waiting for authentication (timeout: {timeout}s)...[/dim]")

    start_time = time.time()
    while time.time() - start_time < timeout:
        current_token = get_puppy_token()

        # Check if token changed from initial state
        if current_token != initial_token:
            if current_token and not is_token_expired(current_token, silent=True):
                console.print("[green]✓ Authentication successful![/green]")
                return True
            else:
                console.print(
                    "[yellow]Received token but it's invalid or expired[/yellow]"
                )

        # Sleep a bit before checking again
        await asyncio.sleep(1)

    console.print(f"[red]Authentication timeout after {timeout}s[/red]")
    return False


async def authenticate_puppy(port: int) -> bool:
    """
    Execute the full authentication flow:
    1. Check if current token is valid
    2. If not, open browser for auth
    3. Wait for token to be received

    Returns True if authentication succeeded, False otherwise.
    """
    # Check if we already have a valid token
    if is_puppy_token_valid():
        console.print("[green]✓ Puppy token is valid![/green]")
        return True

    console.print("[yellow]Puppy needs to authenticate...[/yellow]")

    # Store initial token state (might be None or expired)
    initial_token = get_puppy_token()

    # Open browser for authentication
    auth_url = f"https://puppy.stg.walmart.com/authenticate_puppy?port={port}"
    console.print(f"[blue]Opening browser for authentication: {auth_url}[/blue]")

    try:
        webbrowser.open(auth_url)
        console.print("[dim]Browser opened - please complete authentication[/dim]")
    except Exception as e:
        console.print(f"[red]Failed to open browser: {e}[/red]")
        console.print(f"[yellow]Please manually open: {auth_url}[/yellow]")

    # Wait for the token to be updated
    success = await wait_for_token_update(initial_token, timeout=120)

    if success:
        # Double-check the final token
        final_token = get_puppy_token()
        if final_token and not is_token_expired(final_token, silent=True):
            return True
        else:
            console.print("[red]Final token validation failed[/red]")
            return False

    return False
