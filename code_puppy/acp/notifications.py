"""Helper functions for sending ACP notifications.

These functions construct properly formatted session/update
notifications for various update types:

- agent_message_chunk: Streaming text responses
- user_message_chunk: User message replay
- tool_call: Tool invocation started
- tool_call_update: Tool progress/completion
- plan: Agent planning steps
- available_commands: Slash commands available
"""

import sys
from typing import Any, Awaitable, Callable, Dict, List, Optional

SendNotificationCallback = Callable[[str, Dict[str, Any]], Awaitable[None]]


class NotificationSender:
    """Helper for sending ACP session/update notifications.

    This class provides a clean API for sending various types of
    session updates to the ACP client.

    Attributes:
        _send: Callback to send notifications
        _session_id: Session ID for all notifications
    """

    def __init__(
        self,
        send_notification: SendNotificationCallback,
        session_id: str,
    ):
        """Initialize the notification sender.

        Args:
            send_notification: Async callback to send notifications
            session_id: Session ID for all notifications
        """
        self._send = send_notification
        self._session_id = session_id

    # =========================================================================
    # Message Streaming
    # =========================================================================

    async def agent_message_chunk(self, text: str) -> None:
        """Send an agent message chunk (streaming text response).

        This is the primary method for streaming agent responses.
        Multiple chunks are concatenated by the client.

        Args:
            text: Text chunk to send
        """
        await self._send(
            "session/update",
            {
                "sessionId": self._session_id,
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {
                        "type": "text",
                        "text": text,
                    },
                },
            },
        )

    async def user_message_chunk(self, text: str) -> None:
        """Send a user message chunk (for session replay).

        Used when replaying a session to show user messages.

        Args:
            text: User message text
        """
        await self._send(
            "session/update",
            {
                "sessionId": self._session_id,
                "update": {
                    "sessionUpdate": "user_message_chunk",
                    "content": {
                        "type": "text",
                        "text": text,
                    },
                },
            },
        )

    # =========================================================================
    # Tool Calls
    # =========================================================================

    async def tool_call(
        self,
        tool_call_id: str,
        title: str,
        kind: str = "other",
        status: str = "pending",
        raw_input: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Send a tool_call notification (tool invocation started).

        This should be sent when a tool is first invoked, before
        any work is done.

        Args:
            tool_call_id: Unique ID for this tool call
            title: Human-readable title for the tool call
            kind: Tool category (read, edit, execute, search, think, other)
            status: Initial status (pending, in_progress, completed, error)
            raw_input: Optional raw input parameters
        """
        update: Dict[str, Any] = {
            "sessionUpdate": "tool_call",
            "toolCallId": tool_call_id,
            "title": title,
            "kind": kind,
            "status": status,
        }
        if raw_input:
            update["rawInput"] = raw_input

        print(f"[ACP] Tool call: {title} ({kind})", file=sys.stderr)
        await self._send(
            "session/update",
            {
                "sessionId": self._session_id,
                "update": update,
            },
        )

    async def tool_call_update(
        self,
        tool_call_id: str,
        status: Optional[str] = None,
        content: Optional[List[Dict[str, Any]]] = None,
        raw_output: Optional[Any] = None,
    ) -> None:
        """Send a tool_call_update notification.

        Used to update the status of a tool call, add content,
        or report completion.

        Args:
            tool_call_id: ID of the tool call to update
            status: New status (in_progress, completed, error)
            content: Content blocks to add (text, diff, terminal, etc.)
            raw_output: Optional raw output data
        """
        update: Dict[str, Any] = {
            "sessionUpdate": "tool_call_update",
            "toolCallId": tool_call_id,
        }
        if status:
            update["status"] = status
        if content:
            update["content"] = content
        if raw_output is not None:
            update["rawOutput"] = raw_output

        await self._send(
            "session/update",
            {
                "sessionId": self._session_id,
                "update": update,
            },
        )

    # =========================================================================
    # Tool Call Convenience Methods
    # =========================================================================

    async def tool_call_with_text(
        self,
        tool_call_id: str,
        text: str,
        status: str = "completed",
    ) -> None:
        """Send a tool call update with text content.

        Args:
            tool_call_id: ID of the tool call
            text: Text content to display
            status: Status to set
        """
        content = [{"type": "text", "text": text}]
        await self.tool_call_update(tool_call_id, status=status, content=content)

    async def tool_call_with_diff(
        self,
        tool_call_id: str,
        path: str,
        old_text: Optional[str],
        new_text: str,
        status: str = "completed",
    ) -> None:
        """Send a tool call update with a diff (for file edits).

        The client will render this as a visual diff.

        Args:
            tool_call_id: ID of the tool call
            path: File path being edited
            old_text: Original content (None for new files)
            new_text: New content
            status: Status to set
        """
        content = [
            {
                "type": "diff",
                "path": path,
                "oldText": old_text,
                "newText": new_text,
            }
        ]
        await self.tool_call_update(tool_call_id, status=status, content=content)

    async def tool_call_with_terminal(
        self,
        tool_call_id: str,
        terminal_id: str,
        status: str = "in_progress",
    ) -> None:
        """Send a tool call update with embedded terminal.

        The client will show live terminal output.

        Args:
            tool_call_id: ID of the tool call
            terminal_id: ID of the terminal to embed
            status: Status to set
        """
        content = [
            {
                "type": "terminal",
                "terminalId": terminal_id,
            }
        ]
        await self.tool_call_update(tool_call_id, status=status, content=content)

    async def tool_call_error(
        self,
        tool_call_id: str,
        error_message: str,
    ) -> None:
        """Send a tool call update indicating an error.

        Args:
            tool_call_id: ID of the tool call
            error_message: Error message to display
        """
        content = [{"type": "text", "text": f"❌ Error: {error_message}"}]
        await self.tool_call_update(tool_call_id, status="error", content=content)

    # =========================================================================
    # Planning
    # =========================================================================

    async def plan(self, entries: List[Dict[str, Any]]) -> None:
        """Send a plan notification.

        Shows the agent's planned steps to the user.

        Args:
            entries: List of plan entries, each with:
                - title: Step title
                - status: pending, in_progress, completed, skipped
                - content: Optional additional content
        """
        await self._send(
            "session/update",
            {
                "sessionId": self._session_id,
                "update": {
                    "sessionUpdate": "plan",
                    "entries": entries,
                },
            },
        )

    async def plan_step(
        self,
        title: str,
        status: str = "pending",
        content: Optional[str] = None,
    ) -> None:
        """Send a single plan step.

        Convenience method for simple plans.

        Args:
            title: Step title
            status: Step status
            content: Optional step content
        """
        entry: Dict[str, Any] = {
            "title": title,
            "status": status,
        }
        if content:
            entry["content"] = [{"type": "text", "text": content}]
        await self.plan([entry])

    # =========================================================================
    # Commands
    # =========================================================================

    async def available_commands(
        self,
        commands: List[Dict[str, Any]],
    ) -> None:
        """Send available_commands_update notification.

        Tells the client what slash commands are available.

        Args:
            commands: List of command definitions, each with:
                - name: Command name (without /)
                - description: What the command does
                - input: Optional input hint
        """
        await self._send(
            "session/update",
            {
                "sessionId": self._session_id,
                "update": {
                    "sessionUpdate": "available_commands_update",
                    "availableCommands": commands,
                },
            },
        )

    # =========================================================================
    # Thinking / Reasoning
    # =========================================================================

    async def thinking(self, text: str) -> None:
        """Send a thinking/reasoning message.

        Shows the agent's internal reasoning to the user.

        Args:
            text: Reasoning text
        """
        await self._send(
            "session/update",
            {
                "sessionId": self._session_id,
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {
                        "type": "thinking",
                        "text": text,
                    },
                },
            },
        )
