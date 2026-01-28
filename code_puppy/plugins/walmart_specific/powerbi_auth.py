"""Power BI authentication module for Code Puppy.

Uses MSAL (Microsoft Authentication Library) for OAuth 2.0 authentication
with the Power BI REST API. Supports interactive browser login with
automatic token caching and refresh.

Commands:
    /powerbi_auth - Opens browser for Power BI authentication
    /powerbi_test - Validates saved tokens by listing workspaces

Note:
    Requires msal: ``uv pip install msal``

See Also:
    https://learn.microsoft.com/en-us/rest/api/power-bi/
    https://learn.microsoft.com/en-us/python/api/overview/azure/identity-readme
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from code_puppy.config import CONFIG_DIR
from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

# MSAL is required for authentication
try:
    from msal import PublicClientApplication
except ImportError:
    PublicClientApplication = None  # type: ignore


# =============================================================================
# CONSTANTS
# =============================================================================

# Walmart's Azure AD Tenant ID
WALMART_TENANT_ID: str = "3cbcc3d3-094d-4006-9849-0d11d61f484d"

# Microsoft's well-known public client app ID (Azure PowerShell)
# This is safe for interactive auth - no client secret needed
PUBLIC_CLIENT_ID: str = "1950a258-227b-4e31-a9cf-717495945fc2"

# Power BI API scope
POWERBI_SCOPE: list[str] = ["https://analysis.windows.net/powerbi/api/.default"]

# Power BI API base URL
POWERBI_API_BASE: str = "https://api.powerbi.com/v1.0/myorg"

# Token storage
POWERBI_TOKENS_FILE: Path = Path(CONFIG_DIR) / "powerbi.json"

# Token expiration buffer (refresh 5 minutes before expiry)
TOKEN_EXPIRY_BUFFER: int = 300


# =============================================================================
# TOKEN STORAGE
# =============================================================================


def _save_tokens(tokens: dict[str, Any]) -> None:
    """Save tokens to the tokens file."""
    POWERBI_TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(POWERBI_TOKENS_FILE, "w") as f:
        json.dump(tokens, f, indent=2)


def _load_tokens() -> dict[str, Any] | None:
    """Load tokens from the tokens file."""
    if not POWERBI_TOKENS_FILE.exists():
        return None
    try:
        with open(POWERBI_TOKENS_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _is_token_expired(tokens: dict[str, Any]) -> bool:
    """Check if the access token is expired or about to expire."""
    timestamp = tokens.get("timestamp")
    expires_in = tokens.get("expires_in", 3600)
    
    if not timestamp:
        return True
    
    try:
        issued_at = datetime.fromisoformat(timestamp)
        now = datetime.now()
        elapsed = (now - issued_at).total_seconds()
        return elapsed >= (expires_in - TOKEN_EXPIRY_BUFFER)
    except (ValueError, TypeError):
        return True


# =============================================================================
# MSAL AUTHENTICATION
# =============================================================================


def _get_msal_app() -> PublicClientApplication:
    """Get or create the MSAL public client application."""
    if PublicClientApplication is None:
        raise RuntimeError(
            "MSAL is not installed. Install it with:\n"
            "uv pip install msal --index-url "
            "https://pypi.ci.artifacts.walmart.com/artifactory/api/pypi/external-pypi/simple "
            "--allow-insecure-host pypi.ci.artifacts.walmart.com"
        )
    
    # Use token cache file for persistence
    cache_file = Path(CONFIG_DIR) / "powerbi_msal_cache.json"
    
    return PublicClientApplication(
        client_id=PUBLIC_CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{WALMART_TENANT_ID}",
    )


def _authenticate_interactive() -> dict[str, Any]:
    """Perform interactive browser authentication.
    
    Opens a browser window for the user to log in with their Microsoft account.
    
    Returns:
        Dict with access_token, expires_in, and timestamp.
    
    Raises:
        RuntimeError: If authentication fails.
    """
    app = _get_msal_app()
    
    emit_info("🌐 Opening browser for Power BI authentication...")
    emit_info("   Sign in with your Walmart Microsoft account.")
    
    # Try to get token from cache first
    accounts = app.get_accounts()
    if accounts:
        emit_info(f"📦 Found cached account: {accounts[0].get('username', 'Unknown')}")
        result = app.acquire_token_silent(POWERBI_SCOPE, account=accounts[0])
        if result and "access_token" in result:
            emit_success("✅ Got token from cache (no browser needed!)")
            return {
                "access_token": result["access_token"],
                "expires_in": result.get("expires_in", 3600),
                "timestamp": datetime.now().isoformat(),
                "account": accounts[0].get("username", "Unknown"),
            }
    
    # Interactive browser login
    result = app.acquire_token_interactive(scopes=POWERBI_SCOPE)
    
    if "access_token" not in result:
        error = result.get("error_description", result.get("error", "Unknown error"))
        raise RuntimeError(f"Authentication failed: {error}")
    
    return {
        "access_token": result["access_token"],
        "expires_in": result.get("expires_in", 3600),
        "timestamp": datetime.now().isoformat(),
        "account": result.get("id_token_claims", {}).get("preferred_username", "Unknown"),
    }


def _refresh_token_silent() -> dict[str, Any] | None:
    """Try to refresh the token silently using MSAL cache.
    
    Returns:
        New token dict if successful, None if silent refresh failed.
    """
    try:
        app = _get_msal_app()
        accounts = app.get_accounts()
        
        if not accounts:
            return None
        
        result = app.acquire_token_silent(POWERBI_SCOPE, account=accounts[0])
        
        if result and "access_token" in result:
            return {
                "access_token": result["access_token"],
                "expires_in": result.get("expires_in", 3600),
                "timestamp": datetime.now().isoformat(),
                "account": accounts[0].get("username", "Unknown"),
            }
    except Exception:
        pass
    
    return None


# =============================================================================
# COMMAND HANDLERS
# =============================================================================


def handle_powerbi_auth_command(command: str, name: str) -> str | None:
    """Handle the /powerbi_auth slash command."""
    if name != "powerbi_auth":
        return None
    
    emit_info("🔐 Starting Power BI authentication flow...")
    
    if PublicClientApplication is None:
        emit_error(
            "❌ MSAL is not installed.\n"
            "   Install it with:\n"
            "   uv pip install msal --index-url "
            "https://pypi.ci.artifacts.walmart.com/artifactory/api/pypi/external-pypi/simple "
            "--allow-insecure-host pypi.ci.artifacts.walmart.com"
        )
        return "MSAL is required for Power BI authentication."
    
    try:
        tokens = _authenticate_interactive()
        _save_tokens(tokens)
        
        emit_success(
            f"🎉 Power BI authentication complete!\n"
            f"   Account: {tokens.get('account', 'Unknown')}\n"
            f"   Tokens saved to: {POWERBI_TOKENS_FILE}\n"
            f"   You can now use Power BI API tools."
        )
        return "Power BI authentication successful!"
    
    except KeyboardInterrupt:
        emit_info("\n🛑 Authentication cancelled by user.")
        return "Authentication cancelled."
    
    except Exception as e:
        emit_error(f"❌ Authentication failed: {e!s}")
        return f"Authentication failed: {e!s}"


def handle_powerbi_test_command(command: str, name: str) -> str | None:
    """Handle the /powerbi_test slash command."""
    if name != "powerbi_test":
        return None
    
    emit_info("🔍 Testing Power BI authentication...")
    
    result = validate_powerbi_auth()
    
    if result["success"]:
        workspaces = result.get("workspaces", [])
        emit_success(
            f"✅ Power BI authentication valid!\n"
            f"   Found {len(workspaces)} workspaces:\n" +
            "\n".join(f"      • {ws}" for ws in workspaces[:5]) +
            (f"\n      ... and {len(workspaces) - 5} more" if len(workspaces) > 5 else "")
        )
        return f"Authenticated! Access to {len(workspaces)} workspaces."
    
    emit_error(f"❌ {result['error']}")
    return result["error"]


# =============================================================================
# VALIDATION
# =============================================================================


def validate_powerbi_auth() -> dict[str, Any]:
    """Validate Power BI authentication by listing workspaces."""
    token = get_valid_access_token()
    
    if not token:
        return {
            "success": False,
            "error": "No Power BI tokens found. Run /powerbi_auth to authenticate.",
        }
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                f"{POWERBI_API_BASE}/groups",
                headers={"Authorization": f"Bearer {token}"},
            )
            
            if response.status_code == 200:
                data = response.json()
                workspaces = [ws.get("name", "Unknown") for ws in data.get("value", [])]
                return {
                    "success": True,
                    "workspaces": workspaces,
                }
            
            if response.status_code == 401:
                return {
                    "success": False,
                    "error": "Access token expired. Run /powerbi_auth to re-authenticate.",
                }
            
            return {
                "success": False,
                "error": f"API error: HTTP {response.status_code}",
            }
    
    except Exception as e:
        return {
            "success": False,
            "error": f"Connection error: {e}",
        }


# =============================================================================
# UTILITY FUNCTIONS FOR API CLIENTS
# =============================================================================


def get_valid_access_token() -> str | None:
    """Get a valid access token, attempting refresh if needed.
    
    Returns:
        Access token string, or None if not authenticated.
    """
    # First try to load from our token file
    tokens = _load_tokens()
    
    if tokens and not _is_token_expired(tokens):
        return tokens.get("access_token")
    
    # Try silent refresh via MSAL
    new_tokens = _refresh_token_silent()
    if new_tokens:
        _save_tokens(new_tokens)
        return new_tokens.get("access_token")
    
    # Return expired token anyway - let caller handle the error
    if tokens:
        return tokens.get("access_token")
    
    return None


# =============================================================================
# HELP / AUTOCOMPLETE
# =============================================================================


def get_powerbi_auth_help() -> list[tuple[str, str]]:
    """Return (command_name, description) tuples for autocomplete/help."""
    return [
        ("powerbi_auth", "Authenticate with Power BI"),
        ("powerbi_test", "Test Power BI authentication"),
    ]
