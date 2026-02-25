"""HTTP client for the Agent Marketplace API.

Provides async functions to interact with the Walmart Agent Marketplace backend.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

# Gracefully import is_token_expired from walmart_specific
# This allows the plugin to work even if walmart_specific isn't installed
try:
    from code_puppy.plugins.walmart_specific.auth import is_token_expired

    _HAS_TOKEN_EXPIRY_CHECK = True
except ImportError:
    _HAS_TOKEN_EXPIRY_CHECK = False

    def is_token_expired(token: str, silent: bool = False) -> bool:  # type: ignore[misc]
        """Fallback: assume token is valid if we can't check expiration."""
        return False


def _get_marketplace_base_url() -> str:
    """Get the marketplace API base URL.

    Uses https://puppy-dev.walmart.com for local development when
    CODEPUPPY_LOCAL_AGENT_MARKETPLACE=1 is set, otherwise uses production.

    This is called on each request to allow dynamic switching.
    """
    if os.environ.get("CODEPUPPY_LOCAL_AGENT_MARKETPLACE") == "1":
        return "https://puppy-dev.walmart.com/api/agent-marketplace"
    return "https://puppy.walmart.com/api/agent-marketplace"


DEFAULT_TIMEOUT = 30.0


def _format_response_error(response_text: str, status_code: int) -> str:
    """Format a user-friendly error message from a response.

    Detects HTML error pages, auth redirects, and other common issues.
    """
    text = response_text.strip()

    # Detect HTML error pages (usually from proxy or server errors)
    if (
        text.startswith("<!DOCTYPE")
        or text.startswith("<html")
        or text.startswith("<HTML")
    ):
        if (
            "signin" in text.lower()
            or "login" in text.lower()
            or "auth" in text.lower()
        ):
            return "Authentication required. Try running /puppy_auth first."
        elif "blocked" in text.lower() or "forbidden" in text.lower():
            return "Request blocked by corporate proxy. Check your network connection."
        elif "not found" in text.lower() or "404" in text:
            return "Agent not found in the marketplace."
        elif "error" in text.lower() or "500" in text or "502" in text or "503" in text:
            return f"Server error (HTTP {status_code}). The marketplace may be temporarily unavailable."
        else:
            return f"Received HTML instead of JSON (HTTP {status_code}). This usually means a proxy or firewall issue."

    # Detect auth redirects in response text
    if "signin" in text or "callbackUrl" in text:
        return "Authentication required. Try running /puppy_auth first."

    # Return truncated raw response for other cases
    if len(text) > 100:
        return f"Unexpected response: {text[:100]}..."
    return f"Unexpected response: {text}"


def _get_marketplace_token() -> Optional[str]:
    """Retrieve the marketplace token from config.

    Returns:
        The marketplace token string, or None if not set.
    """
    try:
        from code_puppy.config import get_value

        return get_value("marketplace_token")
    except ImportError:
        return None


def _get_user_groups() -> List[str]:
    """Retrieve the user's AD groups from the saved token file.

    The groups are saved during authentication in marketplace_token.json
    under the 'user.groups' field. These are needed for the server to
    filter AD-group-restricted agents.

    Returns:
        List of AD group names the user belongs to, or empty list if not available.
    """
    try:
        from code_puppy.config import CONFIG_DIR

        token_file = Path(CONFIG_DIR) / "marketplace_token.json"
        if not token_file.exists():
            return []

        with open(token_file, "r") as f:
            data = json.load(f)

        # Groups are stored under user.groups
        user_info = data.get("user", {})
        groups = user_info.get("groups", [])

        if isinstance(groups, list):
            return groups
        return []
    except Exception:
        return []


def is_marketplace_token_valid() -> bool:
    """Check if the marketplace token exists and is not expired.

    This function checks:
    1. Whether a marketplace token exists in config
    2. Whether the token is still valid (not expired)

    Returns:
        True if the token exists and is valid, False otherwise.
    """
    token = _get_marketplace_token()
    if not token:
        return False

    # Check expiration silently to avoid console spam
    return not is_token_expired(token, silent=True)


def get_marketplace_token_status() -> Tuple[bool, bool]:
    """Get the status of the marketplace token.

    This function provides detailed status information that callers
    can use to decide whether to prompt for authentication.

    Returns:
        A tuple of (token_exists, is_valid):
        - token_exists: True if a token is present in config
        - is_valid: True if the token exists AND is not expired
    """
    token = _get_marketplace_token()
    token_exists = token is not None and len(token) > 0

    if not token_exists:
        return (False, False)

    # Check if token is expired (silently)
    is_valid = not is_token_expired(token, silent=True)

    return (token_exists, is_valid)


def _get_auth_headers() -> dict:
    """Get authentication headers for marketplace API.

    Uses marketplace_token from config (set by /puppy_auth command).
    This is different from puppy_token which is for the backend.

    Also includes the user's AD groups as a custom header so the server
    can filter AD-group-restricted agents appropriately.

    Returns empty headers if the token is missing or expired,
    so callers know authentication is needed.
    """
    token = _get_marketplace_token()

    # No token available
    if not token:
        return {}

    # Check if token is expired (silently to avoid console spam)
    if is_token_expired(token, silent=True):
        return {}

    # Token exists and is valid - build auth headers
    headers = {"Authorization": f"Bearer {token}"}

    # Include user's AD groups for filtering AD-restricted agents
    # The server uses this to determine which restricted agents to show
    groups = _get_user_groups()
    if groups:
        # Send groups as comma-separated header value
        # Limit to first 100 groups to avoid header size issues
        headers["X-User-Groups"] = ",".join(groups[:100])

    return headers


def _normalize_response(
    success: bool, data: Any = None, error: Optional[str] = None, status_code: int = 0
) -> Dict[str, Any]:
    """Normalize API responses to a consistent format."""
    return {
        "success": success,
        "data": data,
        "error": error,
        "status_code": status_code,
    }


async def upload_agent(agent_data: dict) -> dict:
    """Upload an agent definition to the marketplace."""
    base_url = _get_marketplace_base_url()
    try:
        async with httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT, verify=False, follow_redirects=True
        ) as client:
            response = await client.post(
                f"{base_url}/publish",
                json=agent_data,
                headers=_get_auth_headers(),
            )

            if response.status_code >= 400:
                try:
                    body = response.json()
                    error_msg = body.get("error", response.text)
                except Exception:
                    error_msg = response.text
                return _normalize_response(
                    False, error=error_msg, status_code=response.status_code
                )

            # Parse JSON response with better error handling
            try:
                data = response.json()
            except Exception:
                return _normalize_response(
                    False,
                    error=_format_response_error(response.text, response.status_code),
                    status_code=response.status_code,
                )
            return _normalize_response(
                True, data=data, status_code=response.status_code
            )
    except httpx.ConnectError as e:
        return _normalize_response(False, error=f"Connection error: {e}", status_code=0)
    except httpx.TimeoutException:
        return _normalize_response(False, error="Request timed out", status_code=0)
    except Exception as e:
        return _normalize_response(False, error=f"Unexpected error: {e}", status_code=0)


async def search_agents(
    query: Optional[str] = None,
    category: Optional[str] = None,
    tags: Optional[List[str]] = None,
    sort: str = "downloads",
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Search for agents in the marketplace."""
    base_url = _get_marketplace_base_url()
    params: Dict[str, Any] = {"limit": limit, "sort": sort, "offset": offset}
    if query:
        params["q"] = query
    if category:
        params["category"] = category
    if tags:
        params["tags"] = ",".join(tags)

    try:
        async with httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT, verify=False, follow_redirects=True
        ) as client:
            response = await client.get(
                f"{base_url}/search",
                params=params,
                headers=_get_auth_headers(),
            )

            if response.status_code >= 400:
                try:
                    body = response.json()
                    error_msg = body.get("error", response.text)
                except Exception:
                    error_msg = response.text
                return _normalize_response(
                    False, error=error_msg, status_code=response.status_code
                )

            # Parse JSON response with better error handling
            try:
                data = response.json()
            except Exception:
                return _normalize_response(
                    False,
                    error=_format_response_error(response.text, response.status_code),
                    status_code=response.status_code,
                )
            return _normalize_response(
                True, data=data, status_code=response.status_code
            )
    except httpx.ConnectError as e:
        return _normalize_response(False, error=f"Connection error: {e}", status_code=0)
    except httpx.TimeoutException:
        return _normalize_response(False, error="Request timed out", status_code=0)
    except Exception as e:
        return _normalize_response(False, error=f"Unexpected error: {e}", status_code=0)


async def download_agent(name: str) -> dict:
    """Download an agent definition from the marketplace."""
    base_url = _get_marketplace_base_url()
    try:
        # Use a longer timeout (60s) for downloads as agents can be large
        async with httpx.AsyncClient(
            timeout=60.0, verify=False, follow_redirects=True
        ) as client:
            response = await client.get(
                f"{base_url}/download",
                params={"name": name},
                headers=_get_auth_headers(),
            )

            if response.status_code >= 400:
                try:
                    body = response.json()
                    error_msg = body.get("error", response.text)
                except Exception:
                    error_msg = response.text
                return _normalize_response(
                    False, error=error_msg, status_code=response.status_code
                )

            # Parse JSON response with better error handling
            try:
                data = response.json()
            except Exception:
                return _normalize_response(
                    False,
                    error=_format_response_error(response.text, response.status_code),
                    status_code=response.status_code,
                )
            return _normalize_response(
                True, data=data, status_code=response.status_code
            )
    except httpx.ConnectError as e:
        return _normalize_response(False, error=f"Connection error: {e}", status_code=0)
    except httpx.TimeoutException:
        return _normalize_response(False, error="Request timed out", status_code=0)
    except Exception as e:
        return _normalize_response(False, error=f"Unexpected error: {e}", status_code=0)


async def get_my_agents() -> dict:
    """Get list of agents published by the current user."""
    base_url = _get_marketplace_base_url()
    try:
        async with httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT, verify=False, follow_redirects=True
        ) as client:
            response = await client.get(
                f"{base_url}/my-agents",
                headers=_get_auth_headers(),
            )

            if response.status_code >= 400:
                try:
                    body = response.json()
                    error_msg = body.get("error", response.text)
                except Exception:
                    error_msg = response.text
                return _normalize_response(
                    False, error=error_msg, status_code=response.status_code
                )

            data = response.json()
            # Handle both {data: [...]} and direct list responses
            if isinstance(data, dict) and "data" in data:
                return _normalize_response(
                    True, data=data["data"], status_code=response.status_code
                )
            return _normalize_response(
                True, data=data, status_code=response.status_code
            )
    except httpx.ConnectError as e:
        return _normalize_response(False, error=f"Connection error: {e}", status_code=0)
    except httpx.TimeoutException:
        return _normalize_response(False, error="Request timed out", status_code=0)
    except Exception as e:
        return _normalize_response(False, error=f"Unexpected error: {e}", status_code=0)


async def check_update(name: str, local_hash: str, version: int = None) -> dict:
    """Check if an update is available for an agent."""
    base_url = _get_marketplace_base_url()
    params = {"name": name, "hash": local_hash}
    if version is not None:
        params["version"] = str(version)

    try:
        async with httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT, verify=False, follow_redirects=True
        ) as client:
            response = await client.get(
                f"{base_url}/check-update",
                params=params,
                headers=_get_auth_headers(),
            )

            if response.status_code >= 400:
                try:
                    body = response.json()
                    error_msg = body.get("error", response.text)
                except Exception:
                    error_msg = response.text
                return _normalize_response(
                    False, error=error_msg, status_code=response.status_code
                )

            # Parse JSON response with better error handling
            try:
                data = response.json()
            except Exception:
                return _normalize_response(
                    False,
                    error=_format_response_error(response.text, response.status_code),
                    status_code=response.status_code,
                )
            return _normalize_response(
                True, data=data, status_code=response.status_code
            )
    except httpx.ConnectError as e:
        return _normalize_response(False, error=f"Connection error: {e}", status_code=0)
    except httpx.TimeoutException:
        return _normalize_response(False, error="Request timed out", status_code=0)
    except Exception as e:
        return _normalize_response(False, error=f"Unexpected error: {e}", status_code=0)


async def get_agent_by_name(name: str) -> dict:
    """Get detailed information about an agent by name."""
    base_url = _get_marketplace_base_url()
    try:
        async with httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT, verify=False, follow_redirects=True
        ) as client:
            response = await client.get(
                f"{base_url}/{name}",
                headers=_get_auth_headers(),
            )

            if response.status_code >= 400:
                try:
                    body = response.json()
                    error_msg = body.get("error", response.text)
                except Exception:
                    error_msg = response.text
                return _normalize_response(
                    False, error=error_msg, status_code=response.status_code
                )

            # Parse JSON response with better error handling
            try:
                data = response.json()
            except Exception:
                return _normalize_response(
                    False,
                    error=_format_response_error(response.text, response.status_code),
                    status_code=response.status_code,
                )
            return _normalize_response(
                True, data=data, status_code=response.status_code
            )
    except httpx.ConnectError as e:
        return _normalize_response(False, error=f"Connection error: {e}", status_code=0)
    except httpx.TimeoutException:
        return _normalize_response(False, error="Request timed out", status_code=0)
    except Exception as e:
        return _normalize_response(False, error=f"Unexpected error: {e}", status_code=0)


async def delete_agent(name: str) -> dict:
    """Delete an agent from the marketplace (soft delete).

    Args:
        name: The agent name to delete.

    Returns:
        Response dict with success status.
    """
    base_url = _get_marketplace_base_url()
    try:
        async with httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT, verify=False, follow_redirects=True
        ) as client:
            response = await client.delete(
                f"{base_url}/{name}",
                headers=_get_auth_headers(),
            )

            if response.status_code >= 400:
                try:
                    body = response.json()
                    error_msg = body.get("error", response.text)
                except Exception:
                    error_msg = response.text
                return _normalize_response(
                    False, error=error_msg, status_code=response.status_code
                )

            try:
                data = response.json()
            except Exception:
                return _normalize_response(
                    False,
                    error=_format_response_error(response.text, response.status_code),
                    status_code=response.status_code,
                )
            return _normalize_response(
                True, data=data, status_code=response.status_code
            )
    except httpx.ConnectError as e:
        return _normalize_response(False, error=f"Connection error: {e}", status_code=0)
    except httpx.TimeoutException:
        return _normalize_response(False, error="Request timed out", status_code=0)
    except Exception as e:
        return _normalize_response(False, error=f"Unexpected error: {e}", status_code=0)


def run_async(coro):
    """Run async function from sync context."""
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # We're already in an async context, create a new loop in a thread
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)
