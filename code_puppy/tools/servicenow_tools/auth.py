"""ServiceNow Authentication tools.

Tools for authenticating with ServiceNow.
"""

from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_error, emit_info, emit_success


# ============================================================================
# Authenticate
# ============================================================================


def servicenow_authenticate(ctx: RunContext) -> dict[str, Any]:
    """Launch ServiceNow authentication flow.

    Opens a browser window for the user to sign in with their Walmart SSO.
    Use this tool when you receive a 401 authentication error, or when the user
    needs to authenticate/re-authenticate with ServiceNow.

    Returns:
        Dict with success=True if authentication completed, or error details.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on green] SERVICENOW [/bold white on green] "
            "🔐 [bold cyan]Launching authentication flow...[/bold cyan]"
        )
    )

    try:
        from code_puppy.plugins.walmart_specific.servicenow_auth import (
            handle_servicenow_auth_command,
        )

        result = handle_servicenow_auth_command("/servicenow_auth", "servicenow_auth")

        if result and "successful" in result.lower():
            emit_success("ServiceNow authentication completed successfully!")
            return {
                "success": True,
                "message": "ServiceNow authentication successful. You can now retry your previous request.",
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


def register_servicenow_authenticate(agent: Any) -> Tool:
    """Register the servicenow_authenticate tool with a PydanticAI agent."""
    return agent.tool(servicenow_authenticate)
