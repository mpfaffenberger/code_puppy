"""Terminal connection tools for managing terminal browser connections.

This module provides tools for:
- Checking if the Code Puppy API server is running
- Opening the terminal browser interface
- Closing the terminal browser

These tools use the ChromiumTerminalManager to manage the browser instance
and connect to the Code Puppy API server's terminal endpoint.
"""

import contextvars
import logging
from typing import Any, Dict, Optional

import httpx
from pydantic_ai import RunContext
from rich.text import Text

from code_puppy.messaging import emit_error, emit_info, emit_success
from code_puppy.tools.browser import format_terminal_banner
from code_puppy.tools.common import generate_group_id

from .chromium_terminal_manager import get_chromium_terminal_manager

logger = logging.getLogger(__name__)

# Context variable for terminal session - properly inherits through async tasks
_terminal_session_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "terminal_session", default=None
)


def set_terminal_session(session_id: Optional[str]) -> contextvars.Token:
    """Set the terminal session ID for the current context.

    This must be called BEFORE any tool calls that use the terminal.
    The context will properly propagate to all subsequent async calls.

    Args:
        session_id: The session ID to use for terminal operations.

    Returns:
        A token that can be used to reset the context.
    """
    return _terminal_session_var.set(session_id)


def get_terminal_session() -> Optional[str]:
    """Get the terminal session ID for the current context.

    Returns:
        The current session ID, or None if not set.
    """
    return _terminal_session_var.get()


def get_session_manager():
    """Get the ChromiumTerminalManager for the current context's session."""
    session_id = get_terminal_session()
    return get_chromium_terminal_manager(session_id)


def _get_session_from_context(context: RunContext) -> str:
    """Get the session ID for the current context.

    If no session is set in the context var, generates one based on
    the page URL that was opened (stored in the manager).

    Args:
        context: The pydantic-ai RunContext from a tool call.

    Returns:
        A session ID string for the terminal browser.
    """
    # First check if we have a session in the context var
    session = get_terminal_session()
    if session:
        return session

    # Fallback: return default (all tools share one browser)
    return "default"


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
    banner = format_terminal_banner("TERMINAL CHECK SERVER 🔍")
    emit_info(
        Text.from_markup(f"{banner} [bold cyan]{host}:{port}[/bold cyan]"),
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
    banner = format_terminal_banner("TERMINAL OPEN 🖥️")
    emit_info(
        Text.from_markup(f"{banner} [bold cyan]{host}:{port}[/bold cyan]"),
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
        # Get the ChromiumTerminalManager for this session and initialize browser
        manager = get_session_manager()
        await manager.async_initialize()

        # Get the existing page (don't create a new one!) and navigate to terminal
        # This avoids leaving an about:blank tab that causes focus issues
        page = await manager.get_current_page()
        if not page:
            return {"success": False, "error": "Failed to get browser page"}

        await page.goto(terminal_url)

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
    banner = format_terminal_banner("TERMINAL CLOSE 🔒")
    emit_info(
        Text.from_markup(f"{banner}"),
        message_group=group_id,
    )

    try:
        manager = get_session_manager()
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


async def start_api_server(port: int = 8765) -> Dict[str, Any]:
    """Start the Code Puppy API server in the background.

    This starts the API server that provides the terminal endpoint for
    browser-based terminal testing. The server runs in the background
    and persists until stopped with /api stop or the process is killed.

    Args:
        port: The port to run the server on (default: 8765).

    Returns:
        A dictionary containing:
            - success (bool): True if server was started successfully.
            - pid (int): Process ID of the server (if successful).
            - url (str): URL where the server is running (if successful).
            - already_running (bool): True if server was already running.
            - error (str): Error message if start failed (only if unsuccessful).

    Example:
        >>> result = await start_api_server()
        >>> if result["success"]:
        ...     print(f"Server running at {result['url']}")
    """
    import os
    import subprocess
    import sys
    from pathlib import Path

    from code_puppy.config import STATE_DIR

    group_id = generate_group_id("start_api_server", str(port))
    emit_info(
        Text.from_markup(format_terminal_banner(f"START API SERVER 🚀 port:{port}")),
        message_group=group_id,
    )

    pid_file = Path(STATE_DIR) / "api_server.pid"
    server_url = f"http://127.0.0.1:{port}"

    # Check if already running
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)  # Check if process exists
            emit_success(
                f"API server already running (PID {pid})", message_group=group_id
            )
            return {
                "success": True,
                "pid": pid,
                "url": server_url,
                "already_running": True,
            }
        except (OSError, ValueError):
            pid_file.unlink(missing_ok=True)  # Stale PID file

    try:
        # Start the server in background
        proc = subprocess.Popen(
            [sys.executable, "-m", "code_puppy.api.main"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(proc.pid))

        emit_success(f"API server started (PID {proc.pid})", message_group=group_id)
        emit_info(f"Server URL: {server_url}", message_group=group_id)
        emit_info(f"Docs: {server_url}/docs", message_group=group_id)

        return {
            "success": True,
            "pid": proc.pid,
            "url": server_url,
            "already_running": False,
        }

    except Exception as e:
        error_msg = f"Failed to start API server: {str(e)}"
        emit_error(error_msg, message_group=group_id)
        logger.exception("Error starting API server")
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
        # Session is set by invoke_agent via contextvar - just use it
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
        # Session is set by invoke_agent via contextvar - just use it
        return await close_terminal()


def register_start_api_server(agent):
    """Register the API server start tool with an agent.

    Args:
        agent: The pydantic-ai agent to register the tool with.
    """

    @agent.tool
    async def start_api_server(
        context: RunContext,
        port: int = 8765,
    ) -> Dict[str, Any]:
        """
        Start the Code Puppy API server in the background.

        This starts the API server that provides the terminal endpoint.
        Use this if terminal_check_server reports the server isn't running.

        Args:
            port: The port to run the server on (default: 8765)

        Returns:
            Dict with:
                - success: True if server started successfully
                - pid: Process ID of the server (if successful)
                - url: URL where the server is running (if successful)
                - already_running: True if server was already running
                - error: Error message (if unsuccessful)
        """
        from . import terminal_tools

        return await terminal_tools.start_api_server(port)
