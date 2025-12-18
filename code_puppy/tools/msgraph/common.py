"""Common utilities for Microsoft Graph tools.

Provides shared helpers for all msgraph tools including:
- Client instantiation
- Error handling and response formatting
- Shared Pydantic models (if needed)
"""

from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning
from code_puppy.plugins.walmart_specific.msgraph_client import (
    MSGraphClient,
    MSGraphError,
    MSGraphAuthError,
    MSGraphNotFoundError,
    MSGraphAPIError,
    MSGraphThrottledError,
)


# =============================================================================
# CLIENT HELPER
# =============================================================================


def get_msgraph_client() -> MSGraphClient:
    """Get a Microsoft Graph client instance.

    Returns:
        MSGraphClient: A configured Microsoft Graph client.

    Raises:
        MSGraphAuthError: If no valid tokens are available.
    """
    return MSGraphClient()


# =============================================================================
# ERROR HANDLING
# =============================================================================


def _handle_msgraph_error(e: Exception) -> dict:
    """Convert Microsoft Graph exceptions to structured error responses.

    Args:
        e: Exception raised by MSGraphClient.

    Returns:
        Dict with success=False and error details.
    """
    if isinstance(e, MSGraphAuthError):
        error_msg = f"Authentication failed: {e!s}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "authentication",
        }
    elif isinstance(e, MSGraphNotFoundError):
        error_msg = f"Resource not found: {e!s}"
        emit_warning(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "not_found",
        }
    elif isinstance(e, MSGraphThrottledError):
        retry_after = getattr(e, "retry_after", None)
        error_msg = f"Rate limited: {e!s}"
        if retry_after:
            error_msg += f" (retry after {retry_after}s)"
        emit_warning(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "throttled",
            "retry_after": retry_after,
        }
    elif isinstance(e, MSGraphAPIError):
        error_msg = f"API error: {e!s}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "api_error",
            "status_code": getattr(e, "status_code", None),
            "error_code": getattr(e, "error_code", None),
        }
    elif isinstance(e, MSGraphError):
        error_msg = f"Microsoft Graph error: {e!s}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "msgraph",
        }
    else:
        error_msg = f"Unexpected error: {e!s}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "unknown",
        }


# =============================================================================
# GENERIC API REQUEST TOOL
# =============================================================================


def msgraph_api_request(
    ctx: RunContext,
    method: str,
    endpoint: str,
    params: dict | None = None,
    body: dict | None = None,
) -> dict:
    """Make a generic Microsoft Graph API request.

    This is a fallback tool for calling any MS Graph endpoint that doesn't
    have a dedicated tool. Use this for less common operations.

    Args:
        method: HTTP method - "GET", "POST", "PATCH", "DELETE", "PUT".
        endpoint: API endpoint path (e.g., "/me/profile", "/users/{id}/manager").
        params: Optional query parameters as a dict (e.g., {"$top": 10}).
        body: Optional request body as a dict (for POST/PATCH/PUT requests).

    Returns:
        Dict with success=True and response data, or success=False and error.

    Examples:
        # GET request with query params
        msgraph_api_request(
            method="GET",
            endpoint="/me/memberOf",
            params={"$top": 5}
        )

        # POST request with body
        msgraph_api_request(
            method="POST",
            endpoint="/me/sendMail",
            body={"message": {"subject": "Hello"}}
        )
    """
    # Validate method
    method = method.upper()
    valid_methods = {"GET", "POST", "PATCH", "DELETE", "PUT"}
    if method not in valid_methods:
        error_msg = (
            f"Invalid HTTP method: {method}. "
            f"Must be one of: {', '.join(sorted(valid_methods))}"
        )
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "invalid_method",
        }

    # Validate endpoint
    if not endpoint:
        error_msg = "Endpoint cannot be empty"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "invalid_endpoint",
        }

    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"🔗 [bold cyan]{method} {endpoint}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        # Call the appropriate client method based on HTTP method
        # Note: The client expects `json=` not `body=` for JSON payloads
        if method == "GET":
            response = client.get(endpoint, params=params)
        elif method == "POST":
            response = client.post(endpoint, json=body, params=params)
        elif method == "PATCH":
            response = client.patch(endpoint, json=body, params=params)
        elif method == "DELETE":
            response = client.delete(endpoint, params=params)
        elif method == "PUT":
            response = client.put(endpoint, json=body, params=params)
        else:
            # This should never happen due to validation above
            raise ValueError(f"Unsupported method: {method}")

        emit_success(f"API request completed: {method} {endpoint}")

        return {
            "success": True,
            "method": method,
            "endpoint": endpoint,
            "response": response,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_api_request(agent: Any) -> Tool:
    """Register the msgraph_api_request tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_api_request)
