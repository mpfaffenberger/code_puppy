"""Terminal connection tools for managing terminal browser connections.

This module provides tools for:
- Checking if the Code Puppy API server is running
- Opening the terminal browser interface
- Closing the terminal browser

These tools use the ChromiumTerminalManager to manage the browser instance
and connect to the Code Puppy API server's terminal endpoint.
"""

import logging
from typing import Any, Dict

import httpx
from pydantic_ai import RunContext

from code_puppy.messaging import emit_error, emit_info, emit_success
from code_puppy.tools.common import generate_group_id

from .chromium_terminal_manager import get_chromium_terminal_manager

logger = logging.getLogger(__name__)

# Default timeout for health check requests (seconds)
HEALTH_CHECK_TIMEOUT = 5.0

# How long to wait for xterm.js to load in the terminal page (ms)
TERMINAL_LOAD_TIMEOUT = 10000


async def check_terminal_server(
    host: str = "localhost", port: int = 8765
) -> Dict[str, Any]:
    """Check if the Code Puppy API server is running.

    Attempts to connect to the /health endpoint of the API server to verify
    it is running and responsive.

    Args:
        host: The hostname where the server is running. Defaults to "localhost".
        port: The port number for the server. Defaults to 8765.

    Returns:
        A dictionary containing:
            - success (bool): True if server is healthy, False otherwise.
            - server_url (str): The full URL of the server (if successful).
            - status (str): "healthy" if server is running (if successful).
            - error (str): Error message describing the failure (if unsuccessful).

    Example:
        >>> result = await check_terminal_server()
        >>> if result["success"]:
        ...     print(f"Server running at {result['server_url']}")
        ... else:
        ...     print(f"Error: {result['error']}")
    """
    group_id = generate_group_id("terminal_check_server", f"{host}:{port}")
    emit_info(
        f"TERMINAL CHECK SERVER 🔍 {host}:{port}",
        message_group=group_id,
    )

    server_url = f"http://{host}:{port}"
    health_url = f"{server_url}/health"

    try:
        async with httpx.AsyncClient(timeout=HEALTH_CHECK_TIMEOUT) as client:
            response = await client.get(health_url)
            response.raise_for_status()

            # Parse the response to verify it's the expected health check
            health_data = response.json()

            if health_data.get("status") == "healthy":
                emit_success(
                    f"Server is healthy at {server_url}",
                    message_group=group_id,
                )
                return {
                    "success": True,
                    "server_url": server_url,
                    "status": "healthy",
                }
            else:
                # Server responded but not with expected health status
                emit_error(
                    f"Server responded but health check failed: {health_data}",
                    message_group=group_id,
                )
                return {
                    "success": False,
                    "error": f"Unexpected health response: {health_data}",
                }

    except httpx.ConnectError:
        error_msg = (
            f"Server not running at {server_url}. "
            "Please start the Code Puppy API server first."
        )
        emit_error(error_msg, message_group=group_id)
        return {"success": False, "error": error_msg}

    except httpx.TimeoutException:
        error_msg = f"Connection to {server_url} timed out."
        emit_error(error_msg, message_group=group_id)
        return {"success": False, "error": error_msg}

    except httpx.HTTPStatusError as e:
        error_msg = f"Server returned error status {e.response.status_code}."
        emit_error(error_msg, message_group=group_id)
        return {"success": False, "error": error_msg}

    except Exception as e:
        error_msg = f"Failed to check server health: {str(e)}"
        emit_error(error_msg, message_group=group_id)
        logger.exception("Unexpected error checking terminal server")
        return {"success": False, "error": error_msg}


async def open_terminal(host: str = "localhost", port: int = 8765) -> Dict[str, Any]:
    """Open the terminal browser interface.

    First checks if the API server is running, then opens a Chromium browser
    and navigates to the terminal endpoint. Waits for the terminal (xterm.js)
    to be fully loaded before returning.

    Args:
        host: The hostname where the server is running. Defaults to "localhost".
        port: The port number for the server. Defaults to 8765.

    Returns:
        A dictionary containing:
            - success (bool): True if terminal was opened successfully.
            - url (str): The URL of the terminal page (if successful).
            - page_title (str): The title of the terminal page (if successful).
            - error (str): Error message describing the failure (if unsuccessful).

    Example:
        >>> result = await open_terminal()
        >>> if result["success"]:
        ...     print(f"Terminal opened at {result['url']}")
        ... else:
        ...     print(f"Error: {result['error']}")
    """
    group_id = generate_group_id("terminal_open", f"{host}:{port}")
    emit_info(
        f"TERMINAL OPEN 🖥️ {host}:{port}",
        message_group=group_id,
    )

    # First, check if the server is running
    server_check = await check_terminal_server(host, port)
    if not server_check["success"]:
        return {
            "success": False,
            "error": (
                f"Cannot open terminal: {server_check['error']} "
                "Please start the API server with 'code-puppy api' first."
            ),
        }

    terminal_url = f"http://{host}:{port}/terminal"

    try:
        # Get the ChromiumTerminalManager and initialize browser
        manager = get_chromium_terminal_manager()
        await manager.async_initialize()

        # Create a new page and navigate to the terminal
        page = await manager.new_page(terminal_url)

        # Wait for xterm.js to be loaded and ready
        # The terminal container should have the xterm class when ready
        try:
            await page.wait_for_selector(
                ".xterm",
                timeout=TERMINAL_LOAD_TIMEOUT,
            )
            emit_info("Terminal xterm.js loaded", message_group=group_id)
        except Exception as e:
            logger.warning(f"Timeout waiting for xterm.js: {e}")
            # Continue anyway - the page might still be usable

        # Get page information
        final_url = page.url
        page_title = await page.title()

        emit_success(
            f"Terminal opened: {final_url}",
            message_group=group_id,
        )

        return {
            "success": True,
            "url": final_url,
            "page_title": page_title,
        }

    except Exception as e:
        error_msg = f"Failed to open terminal: {str(e)}"
        emit_error(error_msg, message_group=group_id)
        logger.exception("Error opening terminal browser")
        return {"success": False, "error": error_msg}


async def close_terminal() -> Dict[str, Any]:
    """Close the terminal browser and clean up resources.

    Closes the Chromium browser instance managed by ChromiumTerminalManager,
    saving any browser state and releasing resources.

    Returns:
        A dictionary containing:
            - success (bool): True if terminal was closed successfully.
            - message (str): A message describing the result.
            - error (str): Error message if closing failed (only if unsuccessful).

    Example:
        >>> result = await close_terminal()
        >>> print(result["message"])
        "Terminal closed"
    """
    group_id = generate_group_id("terminal_close")
    emit_info(
        "TERMINAL CLOSE 🔒",
        message_group=group_id,
    )

    try:
        manager = get_chromium_terminal_manager()
        await manager.close()

        emit_success("Terminal browser closed", message_group=group_id)

        return {
            "success": True,
            "message": "Terminal closed",
        }

    except Exception as e:
        error_msg = f"Failed to close terminal: {str(e)}"
        emit_error(error_msg, message_group=group_id)
        logger.exception("Error closing terminal browser")
        return {"success": False, "error": error_msg}


# =============================================================================
# Tool Registration Functions
# =============================================================================


def register_check_terminal_server(agent):
    """Register the terminal server health check tool with an agent.

    Args:
        agent: The pydantic-ai agent to register the tool with.
    """

    @agent.tool
    async def terminal_check_server(
        context: RunContext,
        host: str = "localhost",
        port: int = 8765,
    ) -> Dict[str, Any]:
        """
        Check if the Code Puppy API server is running and healthy.

        Args:
            host: The hostname where the server is running (default: localhost)
            port: The port number for the server (default: 8765)

        Returns:
            Dict with:
                - success: True if server is healthy
                - server_url: Full URL of the server (if successful)
                - status: "healthy" if running (if successful)
                - error: Error message (if unsuccessful)
        """
        return await check_terminal_server(host, port)


def register_open_terminal(agent):
    """Register the terminal open tool with an agent.

    Args:
        agent: The pydantic-ai agent to register the tool with.
    """

    @agent.tool
    async def terminal_open(
        context: RunContext,
        host: str = "localhost",
        port: int = 8765,
    ) -> Dict[str, Any]:
        """
        Open the terminal browser interface.

        First checks if the API server is running, then opens a browser
        to the terminal endpoint. Waits for xterm.js to load.

        Args:
            host: The hostname where the server is running (default: localhost)
            port: The port number for the server (default: 8765)

        Returns:
            Dict with:
                - success: True if terminal opened successfully
                - url: URL of the terminal page (if successful)
                - page_title: Title of the page (if successful)
                - error: Error message (if unsuccessful)
        """
        return await open_terminal(host, port)


def register_close_terminal(agent):
    """Register the terminal close tool with an agent.

    Args:
        agent: The pydantic-ai agent to register the tool with.
    """

    @agent.tool
    async def terminal_close(
        context: RunContext,
    ) -> Dict[str, Any]:
        """
        Close the terminal browser and clean up resources.

        Returns:
            Dict with:
                - success: True if terminal closed successfully
                - message: Status message (if successful)
                - error: Error message (if unsuccessful)
        """
        return await close_terminal()
