"""Proxy for calling Client methods in ACP.

In ACP, the Agent can call methods on the Client for:
- File system access (fs/read_text_file, fs/write_text_file)
- Terminal management (terminal/create, terminal/output, etc.)
- Permission requests (session/request_permission)

This module provides async functions that send JSON-RPC requests
TO the client and await responses.
"""

import sys
from typing import Any, Awaitable, Callable, Dict, List, Optional

# Type for the send_request callback
SendRequestCallback = Callable[[str, Dict[str, Any]], Awaitable[Any]]


class ClientProxy:
    """Proxy for calling methods on the ACP client.

    This class wraps the JSON-RPC request mechanism to provide
    a clean API for agent code to interact with the client (editor).

    The client may support various capabilities:
    - fs/read_text_file, fs/write_text_file - File operations
    - terminal/* - Terminal/shell command execution
    - session/request_permission - Permission requests

    Attributes:
        _send_request: Callback to send JSON-RPC requests
        _session_id: Current session ID
        _capabilities: Client capabilities from initialize
    """

    def __init__(
        self,
        send_request: SendRequestCallback,
        session_id: str,
        client_capabilities: Dict[str, Any],
    ):
        """Initialize the client proxy.

        Args:
            send_request: Async callback to send JSON-RPC requests
            session_id: Session ID for all requests
            client_capabilities: Capabilities from initialize response
        """
        self._send_request = send_request
        self._session_id = session_id
        self._capabilities = client_capabilities

    # =========================================================================
    # Capability Checks
    # =========================================================================

    @property
    def supports_read_file(self) -> bool:
        """Check if client supports fs/read_text_file."""
        fs = self._capabilities.get("fs", {})
        return fs.get("readTextFile", False)

    @property
    def supports_write_file(self) -> bool:
        """Check if client supports fs/write_text_file."""
        fs = self._capabilities.get("fs", {})
        return fs.get("writeTextFile", False)

    @property
    def supports_terminal(self) -> bool:
        """Check if client supports terminal methods."""
        return self._capabilities.get("terminal", False)

    @property
    def capabilities(self) -> Dict[str, Any]:
        """Get the raw client capabilities."""
        return self._capabilities

    # =========================================================================
    # File System Methods
    # =========================================================================

    async def read_text_file(
        self,
        path: str,
        line: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> str:
        """Read a text file via the client.

        This may return unsaved editor buffer contents, which is a key
        advantage over direct file reading.

        Args:
            path: Absolute path to the file
            line: Optional starting line (1-based)
            limit: Optional max lines to read

        Returns:
            File contents as string

        Raises:
            RuntimeError: If client doesn't support file reading
        """
        if not self.supports_read_file:
            raise RuntimeError("Client does not support fs/read_text_file")

        params: Dict[str, Any] = {
            "sessionId": self._session_id,
            "path": path,
        }
        if line is not None:
            params["line"] = line
        if limit is not None:
            params["limit"] = limit

        print(f"[ACP] Reading file: {path}", file=sys.stderr)
        result = await self._send_request("fs/read_text_file", params)
        return result.get("content", "")

    async def write_text_file(self, path: str, content: str) -> None:
        """Write a text file via the client.

        The client handles the actual file writing, which may include
        updating editor buffers.

        Args:
            path: Absolute path to the file
            content: Content to write

        Raises:
            RuntimeError: If client doesn't support file writing
        """
        if not self.supports_write_file:
            raise RuntimeError("Client does not support fs/write_text_file")

        print(f"[ACP] Writing file: {path}", file=sys.stderr)
        await self._send_request(
            "fs/write_text_file",
            {
                "sessionId": self._session_id,
                "path": path,
                "content": content,
            },
        )

    # =========================================================================
    # Permission Methods
    # =========================================================================

    async def request_permission(
        self,
        tool_call_id: str,
        tool_call_update: Dict[str, Any],
        options: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Request permission from user for a tool call.

        This presents the user with options and waits for their choice.

        Args:
            tool_call_id: ID of the tool call
            tool_call_update: Tool call details to display
            options: Permission options to present

        Returns:
            Permission outcome (selected option or cancelled)
        """
        print(f"[ACP] Requesting permission for tool: {tool_call_id}", file=sys.stderr)
        result = await self._send_request(
            "session/request_permission",
            {
                "sessionId": self._session_id,
                "toolCall": tool_call_update,
                "options": options,
            },
        )
        return result.get("outcome", {"outcome": "cancelled"})

    # =========================================================================
    # Terminal Methods
    # =========================================================================

    async def create_terminal(
        self,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[List[Dict[str, str]]] = None,
        cwd: Optional[str] = None,
        output_byte_limit: Optional[int] = None,
    ) -> str:
        """Create a terminal to run a command.

        Returns immediately with terminal ID - command runs asynchronously.
        Use terminal_output() to get output and terminal_wait_for_exit()
        to wait for completion.

        Args:
            command: Command to execute
            args: Command arguments
            env: Environment variables as [{name, value}, ...]
            cwd: Working directory
            output_byte_limit: Max output bytes to retain

        Returns:
            Terminal ID for further operations

        Raises:
            RuntimeError: If client doesn't support terminal
        """
        if not self.supports_terminal:
            raise RuntimeError("Client does not support terminal methods")

        params: Dict[str, Any] = {
            "sessionId": self._session_id,
            "command": command,
        }
        if args:
            params["args"] = args
        if env:
            params["env"] = env
        if cwd:
            params["cwd"] = cwd
        if output_byte_limit:
            params["outputByteLimit"] = output_byte_limit

        print(f"[ACP] Creating terminal: {command}", file=sys.stderr)
        result = await self._send_request("terminal/create", params)
        return result["terminalId"]

    async def terminal_output(self, terminal_id: str) -> Dict[str, Any]:
        """Get current terminal output.

        Args:
            terminal_id: ID from create_terminal()

        Returns:
            Dict with:
                - output: Current output string
                - truncated: Whether output was truncated
                - exitStatus: Optional exit status if completed
        """
        return await self._send_request(
            "terminal/output",
            {
                "sessionId": self._session_id,
                "terminalId": terminal_id,
            },
        )

    async def terminal_wait_for_exit(self, terminal_id: str) -> Dict[str, Any]:
        """Wait for terminal command to complete.

        Blocks until the command exits.

        Args:
            terminal_id: ID from create_terminal()

        Returns:
            Exit status with:
                - exitCode: Process exit code (if exited normally)
                - signal: Signal number (if killed by signal)
        """
        print(f"[ACP] Waiting for terminal: {terminal_id}", file=sys.stderr)
        return await self._send_request(
            "terminal/wait_for_exit",
            {
                "sessionId": self._session_id,
                "terminalId": terminal_id,
            },
        )

    async def terminal_kill(self, terminal_id: str) -> None:
        """Kill terminal command without releasing resources.

        Use this to stop a long-running command. Follow up with
        terminal_release() to clean up.

        Args:
            terminal_id: ID from create_terminal()
        """
        print(f"[ACP] Killing terminal: {terminal_id}", file=sys.stderr)
        await self._send_request(
            "terminal/kill",
            {
                "sessionId": self._session_id,
                "terminalId": terminal_id,
            },
        )

    async def terminal_release(self, terminal_id: str) -> None:
        """Release terminal resources.

        Call this when done with a terminal to free resources.

        Args:
            terminal_id: ID from create_terminal()
        """
        print(f"[ACP] Releasing terminal: {terminal_id}", file=sys.stderr)
        await self._send_request(
            "terminal/release",
            {
                "sessionId": self._session_id,
                "terminalId": terminal_id,
            },
        )

    async def run_command(
        self,
        command: str,
        args: Optional[List[str]] = None,
        cwd: Optional[str] = None,
        timeout: float = 60.0,
    ) -> Dict[str, Any]:
        """Convenience method to run a command and wait for completion.

        This is a higher-level wrapper around the terminal methods.

        Args:
            command: Command to execute
            args: Command arguments
            cwd: Working directory
            timeout: Max seconds to wait (not implemented yet)

        Returns:
            Dict with:
                - output: Command output
                - exit_code: Exit code
                - success: True if exit_code == 0
        """
        terminal_id = await self.create_terminal(command, args=args, cwd=cwd)
        try:
            exit_status = await self.terminal_wait_for_exit(terminal_id)
            output_result = await self.terminal_output(terminal_id)

            exit_code = exit_status.get("exitCode", -1)
            return {
                "output": output_result.get("output", ""),
                "exit_code": exit_code,
                "success": exit_code == 0,
                "truncated": output_result.get("truncated", False),
            }
        finally:
            await self.terminal_release(terminal_id)
