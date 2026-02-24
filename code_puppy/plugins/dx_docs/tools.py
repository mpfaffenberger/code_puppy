"""DX Documentation tools for Code Puppy.

Provides tools for searching and reading documentation from Walmart's
DX developer portal (dx.walmart.com). These tools integrate with the
DX MCP server to provide seamless documentation access.

Tools:
    - dx_search: Search DX documentation (keyword-based)
    - dx_semantic_search: Semantic/vector search using AI embeddings
    - dx_get_page_content: Get full page content by ID
    - dx_get_tags: List all available documentation tags
    - dx_authenticate: Trigger authentication flow

The agent should use a hybrid search strategy:
    1. Use dx_semantic_search for natural language/troubleshooting queries
    2. Use dx_search for specific terms, acronyms, exact matches
"""

import functools
import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional, TypeVar

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning
from code_puppy.plugins.dx_docs.auth import (
    DXAuthError,
    DXTokenExpiredError,
    DXTokenNotFoundError,
    MCP_CLI_INSTALL_URL,
    ensure_mcp_cli_and_authenticate,
    get_token_status,
    is_mcp_cli_installed,
)
from code_puppy.plugins.dx_docs.client import (
    DXAPIError,
    DXError,
    DXNotFoundError,
    DXRateLimitError,
    get_dx_client,
)
from code_puppy.plugins.dx_docs.content_search_client import (
    ContentSearchAPIError,
    ContentSearchError,
    get_content_search_client,
)

# Type variable for the decorated function's return type
F = TypeVar("F", bound=Callable[..., dict])

logger = logging.getLogger(__name__)


# =============================================================================
# ERROR HANDLING
# =============================================================================


@dataclass
class _ErrorConfig:
    """Configuration for handling a specific error type."""

    error_type: str
    emit_func: Callable[[str], None]
    message_prefix: str = ""
    extra_fields: Optional[dict] = None


# Error handler mapping - order matters for subclass matching!
# More specific exceptions should come before their base classes.
_ERROR_HANDLERS: list[tuple[type, _ErrorConfig]] = [
    (
        DXTokenNotFoundError,
        _ErrorConfig(
            error_type="not_authenticated",
            emit_func=emit_warning,
            extra_fields={
                "action": "Call dx_authenticate to authenticate, or run 'mcp-cli auth login' in terminal."
            },
        ),
    ),
    (
        DXTokenExpiredError,
        _ErrorConfig(
            error_type="token_expired",
            emit_func=emit_warning,
            extra_fields={"action": "Call dx_authenticate to re-authenticate."},
        ),
    ),
    (
        DXAuthError,
        _ErrorConfig(
            error_type="authentication",
            emit_func=emit_error,
            message_prefix="Authentication error: ",
        ),
    ),
    (
        DXNotFoundError,
        _ErrorConfig(
            error_type="not_found",
            emit_func=emit_warning,
            message_prefix="Not found: ",
        ),
    ),
    (
        DXRateLimitError,
        _ErrorConfig(
            error_type="rate_limit",
            emit_func=emit_warning,
        ),
    ),
    (
        DXAPIError,
        _ErrorConfig(
            error_type="api_error",
            emit_func=emit_error,
            message_prefix="API error: ",
        ),
    ),
    (
        DXError,
        _ErrorConfig(
            error_type="dx_error",
            emit_func=emit_error,
            message_prefix="DX error: ",
        ),
    ),
    # Content Search errors (SSE-based semantic search)
    (
        ContentSearchAPIError,
        _ErrorConfig(
            error_type="content_search_api_error",
            emit_func=emit_error,
            message_prefix="Content search API error: ",
        ),
    ),
    (
        ContentSearchError,
        _ErrorConfig(
            error_type="content_search_error",
            emit_func=emit_error,
            message_prefix="Content search error: ",
        ),
    ),
]


def _handle_dx_error(e: Exception) -> dict:
    """Convert DX exceptions to structured error responses.

    Uses a configuration-driven approach for cleaner, more maintainable
    error handling.

    Args:
        e: Exception raised by DX client.

    Returns:
        Dict with success=False and error details.
    """
    # Find matching handler
    for error_class, config in _ERROR_HANDLERS:
        if isinstance(e, error_class):
            error_msg = f"{config.message_prefix}{e}"
            config.emit_func(error_msg)

            result = {
                "success": False,
                "error": error_msg,
                "error_type": config.error_type,
            }

            # Add extra fields if configured
            if config.extra_fields:
                result.update(config.extra_fields)

            # Add status_code for API errors
            if hasattr(e, "status_code") and e.status_code is not None:
                result["status_code"] = e.status_code

            return result

    # Fallback for unknown errors
    error_msg = f"Unexpected error: {e}"
    logger.exception(error_msg)  # Log full traceback for debugging
    emit_error(error_msg)
    return {
        "success": False,
        "error": error_msg,
        "error_type": "unknown",
    }


# =============================================================================
# AUTO-RETRY WITH AUTHENTICATION
# =============================================================================


def _with_auto_auth_retry(func: F) -> F:
    """Decorator that auto-retries on auth failure after triggering authentication.

    When a tool encounters a DXTokenNotFoundError or DXTokenExpiredError,
    this decorator will:
    1. Emit a warning about the auth issue
    2. Automatically trigger the mcp-cli authentication flow
    3. Retry the original request on successful auth
    4. Return the error response if auth fails

    Args:
        func: The tool function to wrap.

    Returns:
        Wrapped function with auto-retry behavior.
    """

    @functools.wraps(func)
    def wrapper(ctx: RunContext, *args, **kwargs) -> dict:
        try:
            return func(ctx, *args, **kwargs)
        except (DXTokenNotFoundError, DXTokenExpiredError) as e:
            # Auth failed - attempt automatic authentication
            emit_warning(f"Authentication required: {e}")
            emit_info(
                Text.from_markup(
                    "\n[bold white on blue] DX AUTO-AUTH [/bold white on blue] "
                    "\U0001f510 [bold cyan]Attempting automatic authentication...[/bold cyan]"
                )
            )

            # Trigger auth flow (includes mcp-cli installation if needed)
            success, message = ensure_mcp_cli_and_authenticate(auto_install=True)

            if success:
                emit_success("Authentication successful! Retrying request...")
                try:
                    # Retry the original call
                    return func(ctx, *args, **kwargs)
                except Exception as retry_error:
                    # If retry also fails, handle normally
                    return _handle_dx_error(retry_error)
            else:
                # Auth failed, return structured error
                emit_error(f"Authentication failed: {message}")
                return {
                    "success": False,
                    "error": f"Authentication failed: {message}",
                    "error_type": "authentication_failed",
                    "action": "Try running 'mcp-cli auth login' manually in your terminal.",
                }

    return wrapper  # type: ignore[return-value]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _format_search_result(result) -> dict:
    """Format a search result for display.

    Args:
        result: DXSearchResult object.

    Returns:
        Dict with formatted result.
    """
    return {
        "page_id": result.page_id,
        "title": result.title,
        "url": result.url,
        "excerpt": result.highlighted or "",
    }


# =============================================================================
# DX SEARCH TOOL
# =============================================================================


@_with_auto_auth_retry
def dx_search(
    ctx: RunContext,
    query: str,
    limit: int = 20,
) -> dict:
    """Search DX documentation for pages matching the query.

    This is a KEYWORD-BASED search, NOT semantic search. For best results:
    - Try multiple keyword variations
    - Use both singular and plural forms
    - Try acronyms AND full names (e.g., 'WCNP' AND 'Walmart Cloud Native Platform')

    Authentication is handled automatically - if your token is missing or expired,
    the tool will trigger the authentication flow and retry.

    Args:
        ctx: PydanticAI run context.
        query: Search query string (keyword-based).
        limit: Maximum number of results to return (default: 20).

    Returns:
        Dict containing:
            - success (bool): Whether the search succeeded
            - results (list): List of search results with page_id, title, url, excerpt
            - total_count (int): Number of results returned
            - query (str): The query that was searched
            - error (str, optional): Error message if search failed
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] DX SEARCH [/bold white on blue] "
            f"\U0001f50d [bold cyan]'{query}'[/bold cyan]"
        )
    )

    try:
        client = get_dx_client()
        results = client.search(query)

        # Apply limit
        limited_results = results[:limit]

        # Format results
        formatted_results = [_format_search_result(r) for r in limited_results]

        emit_success(f"Found {len(formatted_results)} result(s)")

        return {
            "success": True,
            "results": formatted_results,
            "total_count": len(formatted_results),
            "query": query,
        }

    except (DXTokenNotFoundError, DXTokenExpiredError):
        # Let the decorator handle auth errors for auto-retry
        raise
    except (DXError, DXAuthError) as e:
        return _handle_dx_error(e)
    except Exception as e:
        logger.exception(f"Unexpected error in dx_search: {e}")
        return _handle_dx_error(e)


# =============================================================================
# DX SEMANTIC SEARCH TOOL
# =============================================================================


def _format_semantic_search_result(result) -> dict:
    """Format a semantic search result for display.

    Args:
        result: ContentSearchResult object.

    Returns:
        Dict with formatted result.
    """
    formatted = {
        "title": result.title,
        "content": result.content,
    }
    if result.url:
        formatted["url"] = result.url
    if result.source:
        formatted["source"] = result.source
    if result.score is not None:
        formatted["score"] = result.score
    if result.product:
        formatted["product"] = result.product
    return formatted


@_with_auto_auth_retry
def dx_semantic_search(
    ctx: RunContext,
    query: str,
    product: str = "",
) -> dict:
    """Semantic vector search of Walmart internal tech documentation.

    Uses AI embeddings to find semantically similar content - better for
    natural language troubleshooting questions like "Why is my Kafka
    consumer lagging?" even without exact keyword matches.

    Searches: DX docs, internal Stack Overflow, Kafka, WCNP, Looper,
    Concord, Azure, ElementAI documentation.

    Use this tool for:
    - Natural language questions ("How do I configure X?")
    - Troubleshooting queries ("Why is my service timing out?")
    - Conceptual questions ("What is the best practice for Y?")

    Use dx_search (keyword search) instead for:
    - Specific acronyms or exact terms (e.g., "KITT pipeline")
    - Looking up specific page titles
    - When you know exact terminology

    Authentication is handled automatically - if your token is missing or expired,
    the tool will trigger the authentication flow and retry.

    Args:
        ctx: PydanticAI run context.
        query: Natural language search query.
        product: Optional filter - kafka, wcnp, looper, concord, azure, elementai.
            Leave empty to search all documentation.

    Returns:
        Dict containing:
            - success (bool): Whether the search succeeded
            - results (list): List of results with title, content, url, source, score
            - total_count (int): Number of results returned
            - query (str): The query that was searched
            - product (str): The product filter applied (if any)
            - error (str, optional): Error message if search failed
    """
    # Validate query
    if not query or not query.strip():
        emit_warning("Empty query provided")
        return {
            "success": False,
            "error": "Query cannot be empty",
            "error_type": "validation_error",
        }

    product_display = f" (product: {product})" if product else ""
    emit_info(
        Text.from_markup(
            f"\n[bold white on #0053e2] DX SEMANTIC SEARCH [/bold white on #0053e2] "
            f"\U0001f9e0 [bold cyan]'{query}'{product_display}[/bold cyan]"
        )
    )

    try:
        client = get_content_search_client()
        results = client.search_tech_content(
            query=query,
            product=product if product else None,
        )

        # Format results
        formatted_results = [_format_semantic_search_result(r) for r in results]

        emit_success(f"Found {len(formatted_results)} result(s)")

        response = {
            "success": True,
            "results": formatted_results,
            "total_count": len(formatted_results),
            "query": query,
        }
        if product:
            response["product"] = product

        return response

    except (DXTokenNotFoundError, DXTokenExpiredError):
        # Let the decorator handle auth errors for auto-retry
        raise
    except (ContentSearchError, DXAuthError) as e:
        return _handle_dx_error(e)
    except Exception as e:
        return _handle_dx_error(e)


# =============================================================================
# DX GET PAGE CONTENT TOOL
# =============================================================================


# Maximum character limit to prevent context blowout
MAX_CHARACTER_LIMIT = 50000


@_with_auto_auth_retry
def dx_get_page_content(
    ctx: RunContext,
    page_id: str,
    character_limit: int = 0,
    character_offset: int = 0,
) -> dict:
    """Get the full content of a DX documentation page.

    Use character_limit and character_offset to paginate through large pages
    and avoid blowing out the LLM context window.

    Authentication is handled automatically - if your token is missing or expired,
    the tool will trigger the authentication flow and retry.

    Args:
        ctx: PydanticAI run context.
        page_id: The page ID from search results.
        character_limit: Maximum characters to return (0 = use default max of 50000).
            Values above 50000 are clamped to 50000.
        character_offset: Starting character position for reading (default: 0).
            Use this to paginate through large content.

    Returns:
        Dict containing:
            - success (bool): Whether the read succeeded
            - page_id (str): The page ID
            - content (str): Page content (possibly truncated)
            - total_content_length (int): Total length of the full content
            - content_truncated (bool): Whether the content was truncated
            - remaining_content_length (int): Characters remaining after this chunk
            - character_offset (int): The offset used for this read
            - character_limit (int): The limit used for this read
            - error (str, optional): Error message if read failed
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] DX READ PAGE [/bold white on blue] "
            f"\U0001f4c4 [bold cyan]{page_id}[/bold cyan]"
        )
    )

    try:
        client = get_dx_client()
        page = client.get_page_content(page_id)

        full_content = page.content
        total_content_length = len(full_content)

        # Determine effective limit
        effective_limit = (
            MAX_CHARACTER_LIMIT
            if character_limit <= 0
            else min(character_limit, MAX_CHARACTER_LIMIT)
        )

        # Ensure offset is non-negative
        effective_offset = max(0, character_offset)

        # Slice the content
        content_end = effective_offset + effective_limit
        sliced_content = full_content[effective_offset:content_end]

        # Calculate truncation metadata
        content_truncated = content_end < total_content_length
        remaining_content_length = max(0, total_content_length - content_end)

        if content_truncated:
            emit_success(
                f"Read page (chars {effective_offset}-{content_end} of {total_content_length}, "
                f"{remaining_content_length} remaining)"
            )
        else:
            emit_success(f"Read page ({total_content_length} chars)")

        return {
            "success": True,
            "page_id": page_id,
            "content": sliced_content,
            "total_content_length": total_content_length,
            "content_truncated": content_truncated,
            "remaining_content_length": remaining_content_length,
            "character_offset": effective_offset,
            "character_limit": effective_limit,
        }

    except (DXTokenNotFoundError, DXTokenExpiredError):
        # Let the decorator handle auth errors for auto-retry
        raise
    except (DXError, DXAuthError) as e:
        return _handle_dx_error(e)
    except Exception as e:
        logger.exception(f"Unexpected error in dx_get_page_content: {e}")
        return _handle_dx_error(e)


# =============================================================================
# DX GET TAGS TOOL
# =============================================================================


@_with_auto_auth_retry
def dx_get_tags(ctx: RunContext) -> dict:
    """Get all available tags in the DX documentation system.

    Tags can be used to filter and categorize documentation.

    Authentication is handled automatically - if your token is missing or expired,
    the tool will trigger the authentication flow and retry.

    Args:
        ctx: PydanticAI run context.

    Returns:
        Dict containing:
            - success (bool): Whether the request succeeded
            - tags (list): List of available tag names
            - count (int): Number of tags
            - error (str, optional): Error message if request failed
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] DX TAGS [/bold white on blue] "
            "\U0001f3f7\ufe0f [bold cyan]Fetching available tags...[/bold cyan]"
        )
    )

    try:
        client = get_dx_client()
        tags = client.get_tags()

        emit_success(f"Found {len(tags)} tags")

        return {
            "success": True,
            "tags": tags,
            "count": len(tags),
        }

    except (DXTokenNotFoundError, DXTokenExpiredError):
        # Let the decorator handle auth errors for auto-retry
        raise
    except (DXError, DXAuthError) as e:
        return _handle_dx_error(e)
    except Exception as e:
        logger.exception(f"Unexpected error in dx_get_tags: {e}")
        return _handle_dx_error(e)


# =============================================================================
# DX AUTHENTICATE TOOL
# =============================================================================


def dx_authenticate(ctx: RunContext, auto_install: bool = True) -> dict:
    """Trigger DX documentation authentication flow.

    This uses mcp-cli to authenticate with PingFed SSO. A browser window
    will open for the user to sign in with their Walmart credentials.

    If mcp-cli is not installed and auto_install is True (default),
    it will automatically download and install mcp-cli first.

    Use this tool when:
    - You receive a "not_authenticated" or "token_expired" error
    - The user explicitly asks to authenticate
    - mcp-cli needs to be installed

    Args:
        ctx: PydanticAI run context.
        auto_install: If True (default), automatically install mcp-cli if not present.

    Returns:
        Dict containing:
            - success (bool): Whether authentication completed
            - message (str): Status message
            - installed_mcp_cli (bool, optional): True if mcp-cli was installed
            - error (str, optional): Error message if authentication failed
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] DX AUTH [/bold white on blue] "
            "\U0001f510 [bold cyan]Checking authentication status...[/bold cyan]"
        )
    )

    # Track if we need to install mcp-cli
    mcp_cli_was_installed = False

    # Check if mcp-cli is installed
    if not is_mcp_cli_installed():
        if auto_install:
            emit_warning(
                "\u26a0\ufe0f mcp-cli is not installed. Will attempt automatic installation..."
            )
            mcp_cli_was_installed = True
        else:
            error_msg = (
                f"mcp-cli is not installed. Install with:\n"
                f"curl -sL {MCP_CLI_INSTALL_URL} | sh -"
            )
            emit_error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "action": "Install mcp-cli first, then try again.",
            }

    # Check current token status (only if mcp-cli is already installed)
    if not mcp_cli_was_installed:
        is_valid, status_msg = get_token_status()
        if is_valid:
            emit_success(f"Already authenticated: {status_msg}")
            return {
                "success": True,
                "message": f"Already authenticated. {status_msg}",
                "already_authenticated": True,
            }

    # Use the full authentication flow (includes auto-install if needed)
    success, message = ensure_mcp_cli_and_authenticate(auto_install=auto_install)

    if success:
        emit_success(message)
        result = {
            "success": True,
            "message": message,
        }
        if mcp_cli_was_installed:
            result["installed_mcp_cli"] = True
        return result
    else:
        emit_error(message)
        return {
            "success": False,
            "error": message,
        }


# =============================================================================
# TOOL REGISTRATION
# =============================================================================


def register_dx_search(agent: Any) -> Tool:
    """Register the dx_search tool with a PydanticAI agent."""
    return agent.tool(dx_search)


def register_dx_get_page_content(agent: Any) -> Tool:
    """Register the dx_get_page_content tool with a PydanticAI agent."""
    return agent.tool(dx_get_page_content)


def register_dx_get_tags(agent: Any) -> Tool:
    """Register the dx_get_tags tool with a PydanticAI agent."""
    return agent.tool(dx_get_tags)


def register_dx_authenticate(agent: Any) -> Tool:
    """Register the dx_authenticate tool with a PydanticAI agent."""
    return agent.tool(dx_authenticate)


def register_dx_semantic_search(agent: Any) -> Tool:
    """Register the dx_semantic_search tool with a PydanticAI agent."""
    return agent.tool(dx_semantic_search)


# All DX tool functions - can be registered directly with agent.tool()
DX_TOOL_FUNCTIONS = [
    dx_search,
    dx_semantic_search,
    dx_get_page_content,
    dx_get_tags,
    dx_authenticate,
]


def register_all_dx_tools(agent: Any) -> list[Tool]:
    """Register all DX tools with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        List of registered Tool instances.
    """
    return [agent.tool(tool_func) for tool_func in DX_TOOL_FUNCTIONS]


# Dict mapping tool names to registration functions for TOOL_REGISTRY compatibility
DX_TOOLS = {
    "dx_search": register_dx_search,
    "dx_semantic_search": register_dx_semantic_search,
    "dx_get_page_content": register_dx_get_page_content,
    "dx_get_tags": register_dx_get_tags,
    "dx_authenticate": register_dx_authenticate,
}
