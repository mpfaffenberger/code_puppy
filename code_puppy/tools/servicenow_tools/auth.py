"""ServiceNow Authentication tools.

Tools for authenticating with ServiceNow.
"""

import webbrowser
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success
from code_puppy.plugins.walmart_specific.servicenow_auth import (
    handle_servicenow_auth_command,
)

from ._common import SERVICENOW_BASE_URL


# ============================================================================
# Authenticate
# ============================================================================


def servicenow_authenticate(
    ctx: RunContext,
) -> dict:
    """Launch browser-based SSO login for ServiceNow.

    Use this tool when you get a 401 authentication error.

    Args:
        ctx: PydanticAI run context

    Returns:
        Dict with authentication status.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] SERVICENOW AUTHENTICATE [/bold white on blue] "
            f"\U0001F511 [bold cyan]Launching browser...[/bold cyan]"
        )
    )

    try:
        # Use the existing auth command handler
        result = handle_servicenow_auth_command("login", "servicenow")
        
        if result:
            emit_success("ServiceNow authentication initiated")
            return {
                "success": True,
                "message": "ServiceNow SSO login initiated. Please complete the login in your browser, then retry your request.",
            }
        else:
            # If command handler doesn't work, open the portal directly
            login_url = f"{SERVICENOW_BASE_URL}/sp"
            webbrowser.open(login_url)
            emit_success("Browser opened for ServiceNow login")
            return {
                "success": True,
                "message": "Browser opened for ServiceNow login. Please complete the login in your browser, then retry your request.",
                "login_url": login_url,
            }

    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to launch authentication: {str(e)}",
            "error_type": "authentication",
            "manual_url": f"{SERVICENOW_BASE_URL}/login.do",
        }


def register_servicenow_authenticate(agent: Any) -> Tool:
    """Register the servicenow_authenticate tool with a PydanticAI agent."""
    return agent.tool(servicenow_authenticate)
