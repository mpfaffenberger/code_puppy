"""JSON-RPC method handlers for ACP protocol.

This module contains the handler functions for each ACP method.
Phase 2 implements session management and agent integration.
"""

import sys
from typing import Any, Awaitable, Callable, Dict, Optional

from code_puppy.acp.state import create_session, get_session, get_state

# Protocol version we support
PROTOCOL_VERSION = 1

# Type aliases for callbacks
SendNotificationCallback = Callable[[str, Dict[str, Any]], Awaitable[None]]
SendRequestCallback = Callable[[str, Dict[str, Any]], Awaitable[Any]]


def _get_version() -> str:
    """Get the code-puppy package version."""
    try:
        from code_puppy import __version__

        return __version__
    except ImportError:
        return "0.1.0"


async def handle_initialize(params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle the initialize method.

    Negotiates protocol version and exchanges capabilities between
    the client (editor) and the agent (code-puppy).

    Args:
        params: Initialize parameters from the client, including:
            - protocolVersion: Client's protocol version
            - clientCapabilities: What the client supports
            - clientInfo: Client name/version info

    Returns:
        Initialize response with:
            - protocolVersion: Negotiated protocol version
            - agentCapabilities: What this agent supports
            - agentInfo: Agent name/version info
            - authMethods: Authentication methods (empty for now)
    """
    state = get_state()

    # Store client capabilities for later use
    state.client_capabilities = params.get("clientCapabilities", {})

    # Negotiate protocol version (use minimum of client and agent version)
    client_version = params.get("protocolVersion", PROTOCOL_VERSION)
    state.protocol_version = min(client_version, PROTOCOL_VERSION)

    # Mark as initialized
    state.initialized = True

    # Log to stderr (stdout is reserved for JSON-RPC)
    print(
        f"[ACP] Initialized with protocol version {state.protocol_version}",
        file=sys.stderr,
    )

    return {
        "protocolVersion": state.protocol_version,
        "agentCapabilities": {
            "loadSession": True,
            "promptCapabilities": {
                "image": False,  # TODO: Enable when image support is ready
                "audio": False,
                "embeddedContext": True,
            },
        },
        "agentInfo": {
            "name": "code-puppy",
            "title": "Code Puppy 🐶",
            "version": _get_version(),
        },
        "authMethods": [],  # No auth required currently
    }


async def handle_session_new(
    params: Dict[str, Any],
    send_notification: SendNotificationCallback,
) -> Dict[str, Any]:
    """Handle session/new method.

    Creates a new coding session with its own context and history.

    Args:
        params: Session creation parameters including:
            - sessionId: Unique session identifier
            - cwd: Working directory for the session
            - mcpServers: Optional MCP server configurations
        send_notification: Callback to send notifications

    Returns:
        Session creation response (empty dict on success)
    """
    session_id = params.get("sessionId", "default")
    cwd = params.get("cwd", ".")

    # Create the session
    session = create_session(session_id, cwd)

    # Store MCP servers if provided
    if "mcpServers" in params:
        session.mcp_servers = params["mcpServers"]

    print(f"[ACP] Created session: {session_id} in {cwd}", file=sys.stderr)

    # Send available commands notification
    from code_puppy.acp.agent_bridge import ACPAgentBridge
    from code_puppy.acp.client_proxy import ClientProxy
    from code_puppy.acp.notifications import NotificationSender

    state = get_state()
    client_proxy = ClientProxy(
        send_request=lambda m, p: None,  # Dummy for now
        session_id=session_id,
        client_capabilities=state.client_capabilities,
    )
    notifier = NotificationSender(send_notification, session_id)
    bridge = ACPAgentBridge(session, client_proxy, notifier)
    await bridge.send_available_commands()

    return {}


async def handle_session_prompt(
    params: Dict[str, Any],
    send_notification: SendNotificationCallback,
    send_request: SendRequestCallback,
) -> Dict[str, Any]:
    """Handle session/prompt method.

    Processes a user prompt and streams the response back via
    session/update notifications.

    Args:
        params: Prompt parameters including:
            - sessionId: Session to use
            - prompt: The user's prompt content (list of content blocks)
            - context: Optional context (files, selections, etc.)
        send_notification: Callback to send streaming updates
        send_request: Callback to call client methods

    Returns:
        Final response with stopReason
    """
    session_id = params.get("sessionId", "default")
    prompt = params.get("prompt", [])

    session = get_session(session_id)
    if session is None:
        raise ValueError(f"Session not found: {session_id}")

    state = get_state()

    print(
        f"[ACP] Processing prompt in session {session_id}",
        file=sys.stderr,
    )

    # Create helpers
    from code_puppy.acp.agent_bridge import ACPAgentBridge
    from code_puppy.acp.client_proxy import ClientProxy
    from code_puppy.acp.notifications import NotificationSender

    client_proxy = ClientProxy(
        send_request=send_request,
        session_id=session_id,
        client_capabilities=state.client_capabilities,
    )
    notifier = NotificationSender(send_notification, session_id)

    # Create and run the bridge
    bridge = ACPAgentBridge(session, client_proxy, notifier)
    return await bridge.process_prompt(prompt)


async def handle_session_cancel(params: Dict[str, Any]) -> None:
    """Handle session/cancel notification.

    Cancels any in-progress prompt processing for a session.

    Args:
        params: Cancel parameters including:
            - sessionId: Session to cancel
    """
    session_id = params.get("sessionId", "default")
    print(f"[ACP] Cancel requested for session: {session_id}", file=sys.stderr)

    # TODO: Implement proper cancellation
    # This requires tracking active bridges and calling their cancel() method
    session = get_session(session_id)
    if session:
        # For now, just clear the message history to stop processing
        session.message_history.clear()


async def handle_session_load(params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Handle session/load method.

    Loads a previously saved session state.

    Args:
        params: Load parameters including:
            - sessionId: Session identifier to load
            - state: Serialized session state

    Returns:
        Load response or None
    """
    session_id = params.get("sessionId", "default")
    print(f"[ACP] Load requested for session: {session_id}", file=sys.stderr)

    # TODO: Implement session loading from saved state
    # This would restore message history and agent state
    return None
