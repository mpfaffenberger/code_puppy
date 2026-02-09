"""DX Documentation authentication using mcp-cli tokens.

This module provides authentication handling for the DX documentation
MCP server by reusing tokens from the mcp-cli tool. Users authenticate
via `mcp-cli auth login` which stores tokens in ~/.mcp-cli/tokens.json.

The module also supports:
- Automatic mcp-cli installation if not present
- Triggering re-authentication when tokens expire
- Token validation and status checking
"""

import json
import logging
import os
import platform
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Tuple

# Token expiry buffer to avoid edge cases where token expires during use
EXPIRY_BUFFER = timedelta(minutes=5)

from rich.text import Text

from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

# Configure logging
logger = logging.getLogger(__name__)

# MCP CLI token storage location
MCP_CLI_DIR = Path.home() / ".mcp-cli"
MCP_CLI_TOKENS_FILE = MCP_CLI_DIR / "tokens.json"


# =============================================================================
# EXCEPTION CLASSES
# =============================================================================


class DXAuthError(Exception):
    """Base exception for DX authentication errors."""

    pass


class DXTokenNotFoundError(DXAuthError):
    """Raised when no token is found (user hasn't authenticated)."""

    def __init__(self, message: str = "No DX token found. Run 'mcp-cli auth login' to authenticate."):
        super().__init__(message)


class DXTokenExpiredError(DXAuthError):
    """Raised when the token has expired."""

    def __init__(self, message: str = "DX token has expired. Run 'mcp-cli auth login' to re-authenticate."):
        super().__init__(message)


class DXMCPCLINotInstalledError(DXAuthError):
    """Raised when mcp-cli is not installed."""

    def __init__(self, message: str = "mcp-cli is not installed. Install with: curl -sL https://wmlink.wal-mart.com/mcp-cli-install | sh -"):
        super().__init__(message)


# =============================================================================
# TOKEN MANAGEMENT
# =============================================================================


def get_dx_tokens() -> Optional[dict]:
    """Load tokens from mcp-cli tokens file.

    Returns:
        Dict containing access_token, refresh_token, and expiry info,
        or None if the file doesn't exist or is invalid.
    """
    if not MCP_CLI_TOKENS_FILE.exists():
        logger.debug(f"Token file not found: {MCP_CLI_TOKENS_FILE}")
        return None

    try:
        content = MCP_CLI_TOKENS_FILE.read_text()
        tokens = json.loads(content)
        return tokens
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Failed to read tokens file: {e}")
        return None


def get_dx_access_token() -> Optional[str]:
    """Get the access token from mcp-cli tokens file.

    Returns:
        The access token string, or None if not available.
    """
    tokens = get_dx_tokens()
    if not tokens:
        return None
    return tokens.get("access_token")


def get_token_expiry() -> Optional[datetime]:
    """Get the expiry time of the access token.

    Returns:
        datetime of token expiry, or None if not available.
    """
    tokens = get_dx_tokens()
    if not tokens:
        return None

    # Try different expiry field names that mcp-cli might use
    expiry_str = tokens.get("expires_at") or tokens.get("expiry") or tokens.get("exp")
    if not expiry_str:
        return None

    try:
        # Handle both ISO format and Unix timestamp
        if isinstance(expiry_str, (int, float)):
            return datetime.fromtimestamp(expiry_str, tz=timezone.utc)
        else:
            # Try ISO format parsing
            return datetime.fromisoformat(expiry_str.replace("Z", "+00:00"))
    except (ValueError, TypeError) as e:
        logger.warning(f"Failed to parse token expiry: {e}")
        return None


def is_token_valid() -> bool:
    """Check if the current token is valid and not expired.

    Uses a 5-minute buffer to avoid edge cases where the token
    expires between validation and actual use.

    Returns:
        True if token exists and won't expire within EXPIRY_BUFFER, False otherwise.
    """
    token = get_dx_access_token()
    if not token:
        return False

    expiry = get_token_expiry()
    if expiry:
        now = datetime.now(timezone.utc)
        # Apply buffer to ensure token won't expire during use
        return expiry > (now + EXPIRY_BUFFER)

    # If we can't determine expiry, assume it's valid
    # (the API will return 401 if it's not)
    return True


def get_token_status() -> Tuple[bool, str]:
    """Get detailed status of the current token.

    Returns:
        Tuple of (is_valid, status_message)
    """
    tokens = get_dx_tokens()
    if not tokens:
        return (False, "No token found. Run 'mcp-cli auth login' to authenticate.")

    token = tokens.get("access_token")
    if not token:
        return (False, "Token file exists but access_token is missing.")

    expiry = get_token_expiry()
    if expiry:
        now = datetime.now(timezone.utc)
        if expiry <= now:
            return (False, f"Token expired at {expiry.isoformat()}. Run 'mcp-cli auth login' to refresh.")
        else:
            time_remaining = expiry - now
            hours = int(time_remaining.total_seconds() // 3600)
            minutes = int((time_remaining.total_seconds() % 3600) // 60)
            return (True, f"Token valid. Expires in {hours}h {minutes}m.")

    return (True, "Token present (expiry unknown).")


# =============================================================================
# MCP CLI INSTALLATION
# =============================================================================

# Installation URL for mcp-cli
MCP_CLI_INSTALL_URL = "https://wmlink.wal-mart.com/mcp-cli-install"


def _get_mcp_cli_bin_path() -> Path:
    """Get the expected path to mcp-cli binary.

    Returns:
        Path to the mcp-cli binary location.
    """
    return MCP_CLI_DIR / "bin" / "mcp-cli"


def _is_walmart_network() -> bool:
    """Check if running on Walmart network.

    Returns:
        True if on Walmart network, False otherwise.
    """
    return (
        "wal-mart.com" in os.environ.get("HOSTNAME", "").lower()
        or os.environ.get("WALMART_NETWORK") is not None
    )


def _install_mcp_cli() -> Tuple[bool, str]:
    """Attempt to install mcp-cli using the official installer script.

    This downloads and runs the mcp-cli installer from Walmart's internal URL.
    The installer handles platform detection and sets up the binary in ~/.mcp-cli/bin/.

    Returns:
        Tuple of (success, message)
    """
    system = platform.system()

    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MCP-CLI INSTALL [/bold white on blue] "
            "📦 [bold cyan]Installing mcp-cli...[/bold cyan]"
        )
    )

    # Set up environment with proxy if on Walmart network
    env = os.environ.copy()
    if _is_walmart_network():
        env["HTTP_PROXY"] = "http://sysproxy.wal-mart.com:8080"
        env["HTTPS_PROXY"] = "http://sysproxy.wal-mart.com:8080"
        emit_info("🌐 Detected Walmart network, using corporate proxy")

    if system == "Windows":
        # Windows installation using PowerShell
        emit_info("🪟 Detected Windows, using PowerShell installer...")

        proxy_cmd = ""
        if _is_walmart_network():
            proxy_cmd = "[System.Net.WebRequest]::DefaultWebProxy = New-Object System.Net.WebProxy('http://sysproxy.wal-mart.com:8080'); "

        install_cmd = [
            "powershell",
            "-ExecutionPolicy", "Bypass",
            "-Command",
            f"{proxy_cmd}"
            f"$ErrorActionPreference='Stop'; "
            f"Write-Host 'Downloading mcp-cli installer...'; "
            f"$script = (New-Object Net.WebClient).DownloadString('{MCP_CLI_INSTALL_URL}'); "
            f"Write-Host 'Running installer...'; "
            f"$script | sh"
        ]

        try:
            result = subprocess.run(
                install_cmd,
                capture_output=False,  # Show progress to user
                timeout=300,  # 5 minutes
                env=env,
            )

            if result.returncode == 0:
                # Update PATH for current session
                mcp_bin = str(_get_mcp_cli_bin_path().parent)
                if mcp_bin not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = f"{mcp_bin};{os.environ['PATH']}"

                emit_success("✅ mcp-cli installed successfully!")
                return (True, "mcp-cli installed successfully.")
            else:
                return (False, "Installation failed. Check the output above for details.")

        except subprocess.TimeoutExpired:
            return (False, "Installation timed out after 5 minutes.")
        except Exception as e:
            return (False, f"Installation failed: {e}")

    else:
        # macOS/Linux installation using curl | sh
        emit_info("🐧 Detected Unix-like system, using curl installer...")
        emit_info(f"Running: curl -sL {MCP_CLI_INSTALL_URL} | sh -")

        try:
            # Download the installer script
            curl_result = subprocess.run(
                ["curl", "-sL", MCP_CLI_INSTALL_URL],
                capture_output=True,
                text=True,
                timeout=60,
                env=env,
            )

            if curl_result.returncode != 0:
                return (False, f"Failed to download installer: {curl_result.stderr}")

            installer_script = curl_result.stdout

            if not installer_script:
                return (False, "Downloaded installer script is empty.")

            # Run the installer script
            emit_info("📥 Running installer script...")
            sh_result = subprocess.run(
                ["sh"],
                input=installer_script,
                capture_output=False,  # Show progress to user
                text=True,
                timeout=300,  # 5 minutes
                env=env,
            )

            if sh_result.returncode == 0:
                # Update PATH for current session
                mcp_bin = str(_get_mcp_cli_bin_path().parent)
                if mcp_bin not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = f"{mcp_bin}:{os.environ['PATH']}"

                emit_success("✅ mcp-cli installed successfully!")
                emit_info(f"📍 Installed to: {mcp_bin}")

                # Remind user to update shell config
                shell = os.environ.get("SHELL", "")
                if "zsh" in shell:
                    emit_info("💡 Add to ~/.zshrc: export PATH=\"$HOME/.mcp-cli/bin:$PATH\"")
                elif "bash" in shell:
                    emit_info("💡 Add to ~/.bashrc: export PATH=\"$HOME/.mcp-cli/bin:$PATH\"")

                return (True, "mcp-cli installed successfully.")
            else:
                return (False, "Installation failed. Check the output above for details.")

        except subprocess.TimeoutExpired:
            return (False, "Installation timed out after 5 minutes.")
        except FileNotFoundError:
            return (False, "curl is not installed. Please install curl first.")
        except Exception as e:
            return (False, f"Installation failed: {e}")


# =============================================================================
# MCP CLI DETECTION
# =============================================================================


def is_mcp_cli_installed(log_version: bool = False) -> bool:
    """Check if mcp-cli is installed and accessible.

    Checks both the expected installation path (~/.mcp-cli/bin/mcp-cli)
    and the system PATH.

    Args:
        log_version: If True, emit the version info when found (for verification).

    Returns:
        True if mcp-cli is installed, False otherwise.
    """
    # Commands to try: first the expected path, then system PATH
    mcp_cli_path = _get_mcp_cli_bin_path()
    commands_to_try = []

    if mcp_cli_path.exists():
        commands_to_try.append([str(mcp_cli_path), "version"])
    commands_to_try.append(["mcp-cli", "version"])

    for cmd in commands_to_try:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                if log_version:
                    emit_info(f"✅ Verified: {result.stdout.strip()}")
                return True
        except (subprocess.SubprocessError, FileNotFoundError):
            continue

    return False


def _verify_mcp_cli_installation() -> bool:
    """Verify that mcp-cli was installed correctly (with version logging).

    Returns:
        True if mcp-cli is working, False otherwise.
    """
    return is_mcp_cli_installed(log_version=True)


def check_mcp_cli_auth_status() -> Tuple[bool, str]:
    """Check authentication status via mcp-cli.

    Returns:
        Tuple of (is_authenticated, status_message)
    """
    if not is_mcp_cli_installed():
        return (False, "mcp-cli is not installed.")

    try:
        result = subprocess.run(
            ["mcp-cli", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout + result.stderr

        if "Authenticated" in output or "✅" in output:
            return (True, output.strip())
        else:
            return (False, output.strip() or "Not authenticated.")
    except subprocess.SubprocessError as e:
        return (False, f"Failed to check auth status: {e}")


def trigger_mcp_cli_auth(auto_install: bool = True) -> Tuple[bool, str]:
    """Trigger mcp-cli authentication flow.

    This opens a browser for PingFed SSO authentication.
    If mcp-cli is not installed and auto_install is True, it will
    attempt to install it first.

    Args:
        auto_install: If True, attempt to install mcp-cli if not present.

    Returns:
        Tuple of (success, message)
    """
    # Check if mcp-cli is installed
    if not is_mcp_cli_installed():
        if auto_install:
            emit_warning("⚠️ mcp-cli is not installed. Attempting automatic installation...")
            install_success, install_msg = _install_mcp_cli()

            if not install_success:
                emit_error(f"❌ Failed to install mcp-cli: {install_msg}")
                return (False, f"mcp-cli installation failed: {install_msg}")

            # Verify installation
            if not _verify_mcp_cli_installation():
                emit_error("❌ mcp-cli installation completed but verification failed.")
                return (False, "mcp-cli installed but not working. Please restart your terminal and try again.")
        else:
            return (False, f"mcp-cli is not installed. Install with: curl -sL {MCP_CLI_INSTALL_URL} | sh -")

    emit_info(
        Text.from_markup(
            "\n[bold white on blue] DX AUTH [/bold white on blue] "
            "🔐 [bold cyan]Launching mcp-cli authentication...[/bold cyan]"
        )
    )

    # Determine which mcp-cli to use
    mcp_cli_cmd = "mcp-cli"
    mcp_cli_path = _get_mcp_cli_bin_path()
    if mcp_cli_path.exists():
        mcp_cli_cmd = str(mcp_cli_path)

    try:
        emit_info("🌐 Opening browser for PingFed SSO authentication...")
        emit_info("⏳ Please complete authentication in the browser window...")

        # Run mcp-cli auth login - this will open a browser
        result = subprocess.run(
            [mcp_cli_cmd, "auth", "login"],
            capture_output=False,  # Let it interact with terminal
            timeout=120,  # 2 minute timeout for user to complete auth
        )

        if result.returncode == 0:
            emit_success("🎉 Authentication completed successfully!")
            return (True, "Authentication successful. You can now use DX documentation tools.")
        else:
            return (False, "Authentication was cancelled or failed.")

    except subprocess.TimeoutExpired:
        return (False, "Authentication timed out. Please try again.")
    except subprocess.SubprocessError as e:
        return (False, f"Authentication failed: {e}")


def ensure_mcp_cli_and_authenticate(auto_install: bool = True) -> Tuple[bool, str]:
    """Full authentication flow: install mcp-cli if needed and authenticate.

    This is the main entry point for DX authentication. It handles:
    1. Checking if mcp-cli is installed (installing if needed)
    2. Checking if user is already authenticated
    3. Triggering authentication if needed

    Args:
        auto_install: If True, attempt to install mcp-cli if not present.

    Returns:
        Tuple of (success, message)
    """
    # Check current token status first
    is_valid, status_msg = get_token_status()
    if is_valid:
        emit_success(f"✅ Already authenticated: {status_msg}")
        return (True, f"Already authenticated. {status_msg}")

    # Need to authenticate
    return trigger_mcp_cli_auth(auto_install=auto_install)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def ensure_authenticated() -> str:
    """Ensure we have a valid token, raising an exception if not.

    Uses is_token_valid() which includes the 5-minute expiry buffer.

    Returns:
        The access token string.

    Raises:
        DXTokenNotFoundError: If no token is found.
        DXTokenExpiredError: If the token has expired or will expire soon.
    """
    token = get_dx_access_token()
    if not token:
        raise DXTokenNotFoundError()

    if not is_token_valid():
        raise DXTokenExpiredError()

    return token


def get_auth_headers() -> dict:
    """Get the authentication headers for DX API calls.

    Returns:
        Dict with Authorization header.

    Raises:
        DXAuthError: If authentication is not available.
    """
    token = ensure_authenticated()
    return {
        "Authorization": f"Bearer {token}",
    }
