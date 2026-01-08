"""HTTP client for the Agent Marketplace API.

Provides async functions to interact with the Walmart Agent Marketplace backend.
"""

import os
from typing import Any, Dict, List, Optional

import httpx


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
    if text.startswith('<!DOCTYPE') or text.startswith('<html') or text.startswith('<HTML'):
        if 'signin' in text.lower() or 'login' in text.lower() or 'auth' in text.lower():
            return "Authentication required. Try running /puppy_auth first."
        elif 'blocked' in text.lower() or 'forbidden' in text.lower():
            return "Request blocked by corporate proxy. Check your network connection."
        elif 'not found' in text.lower() or '404' in text:
            return "Agent not found in the marketplace."
        elif 'error' in text.lower() or '500' in text or '502' in text or '503' in text:
            return f"Server error (HTTP {status_code}). The marketplace may be temporarily unavailable."
        else:
            return f"Received HTML instead of JSON (HTTP {status_code}). This usually means a proxy or firewall issue."
    
    # Detect auth redirects in response text
    if 'signin' in text or 'callbackUrl' in text:
        return "Authentication required. Try running /puppy_auth first."
    
    # Return truncated raw response for other cases
    if len(text) > 100:
        return f"Unexpected response: {text[:100]}..."
    return f"Unexpected response: {text}"


def _get_auth_headers() -> dict:
    """Get authentication headers for marketplace API.
    
    Uses marketplace_token from config (set by /puppy_auth command).
    This is different from puppy_token which is for the backend.
    """
    headers = {}
    try:
        from code_puppy.config import get_value

        token = get_value("marketplace_token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
    except ImportError:
        # config not available
        pass
    return headers


def _normalize_response(
    success: bool,
    data: Any = None,
    error: Optional[str] = None,
    status_code: int = 0
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
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, verify=False, follow_redirects=True) as client:
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
                return _normalize_response(False, error=error_msg, status_code=response.status_code)
            
            # Parse JSON response with better error handling
            try:
                data = response.json()
            except Exception as json_err:
                return _normalize_response(
                    False, 
                    error=_format_response_error(response.text, response.status_code),
                    status_code=response.status_code
                )
            return _normalize_response(True, data=data, status_code=response.status_code)
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
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, verify=False, follow_redirects=True) as client:
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
                return _normalize_response(False, error=error_msg, status_code=response.status_code)
            
            # Parse JSON response with better error handling
            try:
                data = response.json()
            except Exception as json_err:
                return _normalize_response(
                    False, 
                    error=_format_response_error(response.text, response.status_code),
                    status_code=response.status_code
                )
            return _normalize_response(True, data=data, status_code=response.status_code)
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
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, verify=False, follow_redirects=True) as client:
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
                return _normalize_response(False, error=error_msg, status_code=response.status_code)
            
            # Parse JSON response with better error handling
            try:
                data = response.json()
            except Exception as json_err:
                return _normalize_response(
                    False, 
                    error=_format_response_error(response.text, response.status_code),
                    status_code=response.status_code
                )
            return _normalize_response(True, data=data, status_code=response.status_code)
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
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, verify=False, follow_redirects=True) as client:
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
                return _normalize_response(False, error=error_msg, status_code=response.status_code)
            
            data = response.json()
            # Handle both {data: [...]} and direct list responses
            if isinstance(data, dict) and "data" in data:
                return _normalize_response(True, data=data["data"], status_code=response.status_code)
            return _normalize_response(True, data=data, status_code=response.status_code)
    except httpx.ConnectError as e:
        return _normalize_response(False, error=f"Connection error: {e}", status_code=0)
    except httpx.TimeoutException:
        return _normalize_response(False, error="Request timed out", status_code=0)
    except Exception as e:
        return _normalize_response(False, error=f"Unexpected error: {e}", status_code=0)


async def check_update(name: str, local_hash: str) -> dict:
    """Check if an update is available for an agent."""
    base_url = _get_marketplace_base_url()
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, verify=False, follow_redirects=True) as client:
            response = await client.get(
                f"{base_url}/check-update",
                params={"name": name, "hash": local_hash},
                headers=_get_auth_headers(),
            )
            
            if response.status_code >= 400:
                try:
                    body = response.json()
                    error_msg = body.get("error", response.text)
                except Exception:
                    error_msg = response.text
                return _normalize_response(False, error=error_msg, status_code=response.status_code)
            
            # Parse JSON response with better error handling
            try:
                data = response.json()
            except Exception as json_err:
                return _normalize_response(
                    False, 
                    error=_format_response_error(response.text, response.status_code),
                    status_code=response.status_code
                )
            return _normalize_response(True, data=data, status_code=response.status_code)
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
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, verify=False, follow_redirects=True) as client:
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
                return _normalize_response(False, error=error_msg, status_code=response.status_code)
            
            # Parse JSON response with better error handling
            try:
                data = response.json()
            except Exception as json_err:
                return _normalize_response(
                    False, 
                    error=_format_response_error(response.text, response.status_code),
                    status_code=response.status_code
                )
            return _normalize_response(True, data=data, status_code=response.status_code)
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
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, verify=False, follow_redirects=True) as client:
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
                return _normalize_response(False, error=error_msg, status_code=response.status_code)
            
            try:
                data = response.json()
            except Exception:
                return _normalize_response(
                    False, 
                    error=_format_response_error(response.text, response.status_code),
                    status_code=response.status_code
                )
            return _normalize_response(True, data=data, status_code=response.status_code)
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
