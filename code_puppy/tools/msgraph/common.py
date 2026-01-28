"""Common utilities for Microsoft Graph tools.

Provides shared helpers for all msgraph tools including:
- Client instantiation
- Error handling and response formatting
- Markdown to HTML conversion for rich email/message formatting
- Shared Pydantic models (if needed)
"""

import re
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
# MARKDOWN TO HTML CONVERSION
# =============================================================================


def markdown_to_html(text: str) -> str:
    """Convert markdown text to HTML for Outlook/Teams rendering.

    Supports common markdown patterns:
    - **bold** and __bold__
    - *italic* and _italic_
    - `inline code`
    - ```code blocks```
    - # Headers (h1-h6)
    - --- horizontal rules
    - - bullet lists
    - 1. numbered lists
    - [links](url)
    - Paragraphs (double newlines)

    Args:
        text: Markdown-formatted text.

    Returns:
        HTML-formatted string suitable for Outlook/Teams.
    """
    if not text:
        return text

    html = text

    # Escape HTML special characters first (except in code blocks)
    # We'll handle code blocks separately to preserve their content

    # Extract and placeholder code blocks first
    code_blocks: list[str] = []

    def save_code_block(match: re.Match) -> str:
        code_blocks.append(match.group(1))
        return f"\x00CODEBLOCK{len(code_blocks) - 1}\x00"

    html = re.sub(r"```(?:\w+)?\n?(.*?)```", save_code_block, html, flags=re.DOTALL)

    # Extract inline code
    inline_codes: list[str] = []

    def save_inline_code(match: re.Match) -> str:
        inline_codes.append(match.group(1))
        return f"\x00INLINECODE{len(inline_codes) - 1}\x00"

    html = re.sub(r"`([^`]+)`", save_inline_code, html)

    # Now escape HTML in the remaining text
    html = html.replace("&", "&amp;")
    html = html.replace("<", "&lt;")
    html = html.replace(">", "&gt;")

    # Headers (must be at start of line)
    html = re.sub(r"^###### (.+)$", r"<h6>\1</h6>", html, flags=re.MULTILINE)
    html = re.sub(r"^##### (.+)$", r"<h5>\1</h5>", html, flags=re.MULTILINE)
    html = re.sub(r"^#### (.+)$", r"<h4>\1</h4>", html, flags=re.MULTILINE)
    html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
    html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
    html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)

    # Horizontal rules
    html = re.sub(r"^---+$", r"<hr>", html, flags=re.MULTILINE)

    # Bold (** or __)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"__(.+?)__", r"<strong>\1</strong>", html)

    # Italic (* or _) - be careful not to match inside words
    html = re.sub(r"(?<!\w)\*([^*]+)\*(?!\w)", r"<em>\1</em>", html)
    html = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"<em>\1</em>", html)

    # Links [text](url)
    html = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', html)

    # Bullet lists (simple - just the items, not nested)
    # Convert lines starting with - or * to list items
    def convert_bullet_list(text: str) -> str:
        lines = text.split("\n")
        result = []
        in_list = False
        for line in lines:
            stripped = line.strip()
            if re.match(r"^[-*] ", stripped):
                if not in_list:
                    result.append("<ul>")
                    in_list = True
                item_content = re.sub(r"^[-*] ", "", stripped)
                result.append(f"<li>{item_content}</li>")
            else:
                if in_list:
                    result.append("</ul>")
                    in_list = False
                result.append(line)
        if in_list:
            result.append("</ul>")
        return "\n".join(result)

    html = convert_bullet_list(html)

    # Numbered lists
    def convert_numbered_list(text: str) -> str:
        lines = text.split("\n")
        result = []
        in_list = False
        for line in lines:
            stripped = line.strip()
            if re.match(r"^\d+\. ", stripped):
                if not in_list:
                    result.append("<ol>")
                    in_list = True
                item_content = re.sub(r"^\d+\. ", "", stripped)
                result.append(f"<li>{item_content}</li>")
            else:
                if in_list:
                    result.append("</ol>")
                    in_list = False
                result.append(line)
        if in_list:
            result.append("</ol>")
        return "\n".join(result)

    html = convert_numbered_list(html)

    # Restore code blocks with styling
    for i, code in enumerate(code_blocks):
        escaped_code = (
            code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        styled_block = (
            f'<pre style="background-color: #f4f4f4; padding: 10px; '
            f'border-radius: 4px; font-family: monospace; overflow-x: auto;">'
            f"{escaped_code}</pre>"
        )
        html = html.replace(f"\x00CODEBLOCK{i}\x00", styled_block)

    # Restore inline code with styling
    for i, code in enumerate(inline_codes):
        escaped_code = (
            code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        styled_inline = (
            f'<code style="background-color: #f4f4f4; padding: 2px 6px; '
            f'border-radius: 3px; font-family: monospace;">{escaped_code}</code>'
        )
        html = html.replace(f"\x00INLINECODE{i}\x00", styled_inline)

    # Convert double newlines to paragraph breaks
    # But not inside pre/code blocks (already handled)
    html = re.sub(r"\n\n+", "</p><p>", html)

    # Convert single newlines to <br> (for line breaks within paragraphs)
    html = re.sub(r"(?<!>)\n(?!<)", "<br>\n", html)

    # Wrap in paragraph tags if not already wrapped in block elements
    if not html.startswith(("<h", "<p", "<ul", "<ol", "<pre", "<hr")):
        html = f"<p>{html}</p>"

    return html


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


# =============================================================================
# AUTHENTICATION TOOL
# =============================================================================


def msgraph_authenticate(ctx: RunContext) -> dict:
    """Launch Microsoft Graph authentication flow.

    Opens a browser window for the user to sign in with their Microsoft account.
    Use this tool when you receive a 401 authentication error, or when the user
    needs to authenticate/re-authenticate with Microsoft Graph.

    Returns:
        Dict with success=True if authentication completed, or error details.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "🔐 [bold cyan]Launching authentication flow...[/bold cyan]"
        )
    )

    try:
        # Import the auth module and run the auth flow
        from code_puppy.plugins.walmart_specific.msgraph_auth import (
            handle_msgraph_auth_command,
        )

        result = handle_msgraph_auth_command("/msgraph_auth", "msgraph_auth")

        if result and "successful" in result.lower():
            emit_success("Authentication completed successfully!")
            return {
                "success": True,
                "message": "Microsoft Graph authentication successful. You can now retry your previous request.",
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


def register_msgraph_authenticate(agent: Any) -> Tool:
    """Register the msgraph_authenticate tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_authenticate)
