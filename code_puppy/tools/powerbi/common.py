"""Common utilities for Power BI tools.

Provides shared helpers for all Power BI tools including:
- Client instantiation
- Error handling and response formatting
- Pydantic models for structured responses
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning
from code_puppy.plugins.walmart_specific.powerbi_client import (
    PowerBIClient,
    PowerBIError,
    PowerBIAuthError,
    PowerBINotFoundError,
    PowerBIAPIError,
    PowerBIThrottledError,
)


# =============================================================================
# PYDANTIC MODELS
# =============================================================================


class Workspace(BaseModel):
    """Power BI Workspace (Group)."""
    id: str
    name: str
    type: str | None = None
    is_read_only: bool = Field(default=False, alias="isReadOnly")
    capacity_id: str | None = Field(default=None, alias="capacityId")


class Report(BaseModel):
    """Power BI Report."""
    id: str
    name: str
    report_type: str | None = Field(default=None, alias="reportType")
    web_url: str | None = Field(default=None, alias="webUrl")
    dataset_id: str | None = Field(default=None, alias="datasetId")
    is_owned_by_me: bool = Field(default=False, alias="isOwnedByMe")


class Dataset(BaseModel):
    """Power BI Dataset."""
    id: str
    name: str
    configured_by: str | None = Field(default=None, alias="configuredBy")
    is_refreshable: bool = Field(default=False, alias="isRefreshable")
    web_url: str | None = Field(default=None, alias="webUrl")
    created_date: str | None = Field(default=None, alias="createdDate")


class TableInfo(BaseModel):
    """Power BI Dataset Table Info."""
    id: int = Field(alias="[ID]")
    name: str = Field(alias="[Name]")
    is_hidden: bool = Field(default=False, alias="[IsHidden]")


class ColumnInfo(BaseModel):
    """Power BI Dataset Column Info."""
    table_id: int = Field(alias="[TableID]")
    name: str | None = Field(default=None)
    data_type: int | None = Field(default=None)


# =============================================================================
# CLIENT HELPER
# =============================================================================


def get_powerbi_client() -> PowerBIClient:
    """Get a Power BI client instance.

    Returns:
        PowerBIClient: A configured Power BI client.

    Raises:
        PowerBIAuthError: If no valid tokens are available.
    """
    return PowerBIClient()


# =============================================================================
# ERROR HANDLING
# =============================================================================


def handle_powerbi_error(e: Exception) -> dict:
    """Convert Power BI exceptions to structured error responses.

    Args:
        e: Exception raised by PowerBIClient.

    Returns:
        Dict with success=False and error details.
    """
    if isinstance(e, PowerBIAuthError):
        error_msg = f"Authentication failed: {e!s}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "authentication",
            "suggestion": "Use the powerbi_authenticate tool to log in.",
        }
    elif isinstance(e, PowerBINotFoundError):
        error_msg = f"Resource not found: {e!s}"
        emit_warning(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "not_found",
        }
    elif isinstance(e, PowerBIThrottledError):
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
    elif isinstance(e, PowerBIAPIError):
        error_msg = f"API error: {e!s}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "api_error",
            "status_code": getattr(e, "status_code", None),
            "error_code": getattr(e, "error_code", None),
        }
    elif isinstance(e, PowerBIError):
        error_msg = f"Power BI error: {e!s}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "powerbi",
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


def powerbi_api_request(
    ctx: RunContext,
    method: str,
    endpoint: str,
    params: dict | None = None,
    body: dict | None = None,
) -> dict:
    """Make a generic Power BI API request.

    This is a fallback tool for calling any Power BI endpoint that doesn't
    have a dedicated tool. Use this for less common operations.

    Args:
        method: HTTP method - "GET", "POST", "PATCH", "DELETE".
        endpoint: API endpoint path (e.g., "/groups", "/reports/{id}").
        params: Optional query parameters as a dict.
        body: Optional request body as a dict (for POST/PATCH requests).

    Returns:
        Dict with success=True and response data, or success=False and error.

    Examples:
        # GET request
        powerbi_api_request(method="GET", endpoint="/groups")

        # POST request with body
        powerbi_api_request(
            method="POST",
            endpoint="/datasets/{id}/refreshes",
            body={}
        )
    """
    method = method.upper()
    valid_methods = {"GET", "POST", "PATCH", "DELETE", "PUT"}
    
    if method not in valid_methods:
        error_msg = f"Invalid HTTP method: {method}. Must be one of: {', '.join(sorted(valid_methods))}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "invalid_method",
        }

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
            f"\n[bold white on #0053e2] POWER BI [/bold white on #0053e2] "
            f"🔗 [bold cyan]{method} {endpoint}[/bold cyan]"
        )
    )

    try:
        client = get_powerbi_client()

        if method == "GET":
            response = client.get(endpoint, params=params)
        elif method == "POST":
            response = client.post(endpoint, json=body, params=params)
        elif method == "PATCH":
            response = client.patch(endpoint, json=body, params=params)
        elif method == "DELETE":
            response = client.delete(endpoint, params=params)
        elif method == "PUT":
            response = client.post(endpoint, json=body, params=params)  # PUT via POST
        else:
            raise ValueError(f"Unsupported method: {method}")

        emit_success(f"API request completed: {method} {endpoint}")

        return {
            "success": True,
            "method": method,
            "endpoint": endpoint,
            "response": response,
        }

    except Exception as e:
        return handle_powerbi_error(e)


def register_powerbi_api_request(agent: Any) -> Tool:
    """Register the powerbi_api_request tool with a PydanticAI agent."""
    return agent.tool(powerbi_api_request)


# =============================================================================
# AUTHENTICATION TOOL
# =============================================================================


def powerbi_authenticate(ctx: RunContext) -> dict:
    """Launch Power BI authentication flow.

    Opens a browser window for the user to sign in with their Microsoft account.
    Use this tool when you receive a 401 authentication error, or when the user
    needs to authenticate/re-authenticate with Power BI.

    Returns:
        Dict with success=True if authentication completed, or error details.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on #0053e2] POWER BI [/bold white on #0053e2] "
            "🔐 [bold cyan]Launching authentication flow...[/bold cyan]"
        )
    )

    try:
        from code_puppy.plugins.walmart_specific.powerbi_auth import (
            handle_powerbi_auth_command,
        )

        result = handle_powerbi_auth_command("/powerbi_auth", "powerbi_auth")

        if result and "successful" in result.lower():
            emit_success("Authentication completed successfully!")
            return {
                "success": True,
                "message": "Power BI authentication successful. You can now retry your previous request.",
            }
        else:
            return {
                "success": False,
                "error": result or "Authentication did not complete",
            }

    except Exception as e:
        error_msg = f"Authentication failed: {e!s}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
        }


def register_powerbi_authenticate(agent: Any) -> Tool:
    """Register the powerbi_authenticate tool with a PydanticAI agent."""
    return agent.tool(powerbi_authenticate)
