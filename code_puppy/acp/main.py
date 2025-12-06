"""Main entry point for ACP agent mode.

This module implements the JSON-RPC 2.0 transport layer for the
Agent Client Protocol (ACP). It handles:

- Reading newline-delimited JSON-RPC messages from stdin
- Dispatching messages to appropriate handlers
- Writing JSON-RPC responses and notifications to stdout
- Bidirectional communication (agent can call client methods)
- Error handling and protocol compliance

Usage:
    code-puppy --acp

The protocol uses stdio communication:
- stdin: Receives JSON-RPC requests from the client (editor)
- stdout: Sends JSON-RPC responses and notifications to the client
- stderr: Used for logging (never pollute stdout with non-JSON)
"""

import asyncio
import json
import sys
from typing import Any, Dict, Optional

from code_puppy.acp.handlers import (
    handle_initialize,
    handle_session_cancel,
    handle_session_load,
    handle_session_new,
    handle_session_prompt,
)
from code_puppy.acp.state import get_state

# JSON-RPC error codes (per spec)
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# ACP-specific error codes (application-defined, must be in -32000 to -32099)
NOT_INITIALIZED = -32002
SESSION_NOT_FOUND = -32003


class ACPTransport:
    """Handles JSON-RPC message transport over stdio.

    This class manages the low-level communication with the ACP client,
    including message framing, JSON parsing, async I/O, and bidirectional
    request/response handling.

    Attributes:
        _reader: Async stream reader for stdin
        _writer: Reference to stdout for writing responses
        _running: Flag to control the main loop
        _pending_requests: Map of request ID to awaiting Future
        _next_request_id: Counter for outgoing request IDs
    """

    def __init__(self) -> None:
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer = sys.stdout
        self._running = False
        self._write_lock = asyncio.Lock()
        # For bidirectional communication (agent calling client)
        self._pending_requests: Dict[int, asyncio.Future] = {}
        self._next_request_id = 1

    async def start(self) -> None:
        """Initialize the transport layer.

        Sets up async stdin reading. Must be called before read_message().
        """
        # Create an async reader for stdin
        loop = asyncio.get_event_loop()
        self._reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(self._reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)
        self._running = True
        print("[ACP] Transport started", file=sys.stderr)

    async def stop(self) -> None:
        """Stop the transport layer."""
        self._running = False
        # Cancel any pending requests
        for future in self._pending_requests.values():
            if not future.done():
                future.cancel()
        self._pending_requests.clear()
        print("[ACP] Transport stopped", file=sys.stderr)

    async def read_message(self) -> Optional[Dict[str, Any]]:
        """Read a single JSON-RPC message from stdin.

        Messages are newline-delimited JSON. Each message must be a
        complete JSON object on a single line.

        Returns:
            Parsed JSON-RPC message dict, or None on EOF/error
        """
        if self._reader is None:
            raise RuntimeError("Transport not started")

        try:
            # Read until newline (messages are newline-delimited)
            line = await self._reader.readline()

            if not line:
                # EOF - client closed connection
                print("[ACP] EOF received", file=sys.stderr)
                return None

            # Decode and parse JSON
            text = line.decode("utf-8").strip()
            if not text:
                # Empty line, skip it
                return await self.read_message()

            message = json.loads(text)
            print(f"[ACP] Received: {text[:100]}...", file=sys.stderr)
            return message

        except json.JSONDecodeError as e:
            print(f"[ACP] JSON parse error: {e}", file=sys.stderr)
            # Send parse error response (no id since we couldn't parse it)
            await self.send_error(None, PARSE_ERROR, f"Parse error: {e}")
            return await self.read_message()

        except Exception as e:
            print(f"[ACP] Read error: {e}", file=sys.stderr)
            return None

    async def write_message(self, message: Dict[str, Any]) -> None:
        """Write a JSON-RPC message to stdout.

        Messages are serialized as single-line JSON followed by newline.
        Output is flushed immediately to ensure timely delivery.

        Args:
            message: The JSON-RPC message dict to send
        """
        async with self._write_lock:
            try:
                # Serialize to JSON (no embedded newlines!)
                text = json.dumps(message, separators=(",", ":"))
                # Write with newline terminator
                self._writer.write(text + "\n")
                self._writer.flush()
                print(f"[ACP] Sent: {text[:100]}...", file=sys.stderr)
            except Exception as e:
                print(f"[ACP] Write error: {e}", file=sys.stderr)

    async def send_notification(self, method: str, params: Dict[str, Any]) -> None:
        """Send a JSON-RPC notification (no id, no response expected).

        Notifications are used for streaming updates (session/update)
        and other one-way messages.

        Args:
            method: The notification method name
            params: Parameters for the notification
        """
        await self.write_message(
            {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
            }
        )

    async def send_response(self, id: Any, result: Any) -> None:
        """Send a JSON-RPC success response.

        Args:
            id: The request id being responded to
            result: The result value to send
        """
        await self.write_message(
            {
                "jsonrpc": "2.0",
                "id": id,
                "result": result,
            }
        )

    async def send_error(
        self,
        id: Any,
        code: int,
        message: str,
        data: Any = None,
    ) -> None:
        """Send a JSON-RPC error response.

        Args:
            id: The request id being responded to (can be None for parse errors)
            code: JSON-RPC error code
            message: Human-readable error message
            data: Optional additional error data
        """
        error_obj: Dict[str, Any] = {
            "code": code,
            "message": message,
        }
        if data is not None:
            error_obj["data"] = data

        await self.write_message(
            {
                "jsonrpc": "2.0",
                "id": id,
                "error": error_obj,
            }
        )

    # =========================================================================
    # Bidirectional Communication (Agent -> Client)
    # =========================================================================

    async def send_request(self, method: str, params: Dict[str, Any]) -> Any:
        """Send a JSON-RPC request TO the client and await response.

        This is used for calling Client methods like:
        - fs/read_text_file, fs/write_text_file
        - terminal/create, terminal/output, etc.
        - session/request_permission

        Args:
            method: The method to call on the client
            params: Parameters for the method

        Returns:
            The result from the client

        Raises:
            RuntimeError: If the client returns an error
            asyncio.TimeoutError: If the client doesn't respond in time
        """
        request_id = self._next_request_id
        self._next_request_id += 1

        # Create future for response
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending_requests[request_id] = future

        # Send the request
        await self.write_message(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
        )

        # Await response with timeout
        try:
            result = await asyncio.wait_for(future, timeout=30.0)
            return result
        except asyncio.TimeoutError:
            print(f"[ACP] Request timeout for {method}", file=sys.stderr)
            raise
        finally:
            self._pending_requests.pop(request_id, None)

    def handle_response(self, message: Dict[str, Any]) -> bool:
        """Handle a JSON-RPC response (to our outgoing request).

        This is called when we receive a message that might be a response
        to a request we sent to the client.

        Args:
            message: The received message

        Returns:
            True if this was a response to our request, False otherwise
        """
        msg_id = message.get("id")
        if msg_id is None:
            return False

        # Check if this is a response to our request
        if msg_id in self._pending_requests:
            future = self._pending_requests[msg_id]
            if future.done():
                return True

            if "error" in message:
                error = message["error"]
                error_msg = error.get("message", "Unknown error")
                future.set_exception(RuntimeError(f"Client error: {error_msg}"))
            else:
                future.set_result(message.get("result"))
            return True

        return False


class ACPDispatcher:
    """Dispatches JSON-RPC messages to appropriate handlers.

    This class routes incoming messages to their handler functions
    and manages the request/response lifecycle.

    Attributes:
        transport: The ACPTransport instance for I/O
    """

    def __init__(self, transport: ACPTransport) -> None:
        self.transport = transport

    async def dispatch(self, message: Dict[str, Any]) -> None:
        """Dispatch a JSON-RPC message to the appropriate handler.

        Handles both requests (with id) and notifications (without id).

        Args:
            message: The parsed JSON-RPC message
        """
        # First check if this is a response to our request
        if self.transport.handle_response(message):
            return  # It was a response, not a request to us

        # Validate basic JSON-RPC structure
        if message.get("jsonrpc") != "2.0":
            print(
                f"[ACP] Invalid jsonrpc version: {message.get('jsonrpc')}",
                file=sys.stderr,
            )
            await self.transport.send_error(
                message.get("id"),
                INVALID_REQUEST,
                "Invalid Request: jsonrpc must be '2.0'",
            )
            return

        method = message.get("method")
        if not method or not isinstance(method, str):
            await self.transport.send_error(
                message.get("id"),
                INVALID_REQUEST,
                "Invalid Request: method is required",
            )
            return

        params = message.get("params", {})
        msg_id = message.get("id")  # None for notifications

        # Check if initialized (except for initialize itself)
        state = get_state()
        if not state.initialized and method != "initialize":
            if msg_id is not None:
                await self.transport.send_error(
                    msg_id,
                    NOT_INITIALIZED,
                    "Not initialized: call 'initialize' first",
                )
            return

        try:
            result = await self._handle_method(method, params)

            # Only send response for requests (with id), not notifications
            if msg_id is not None:
                await self.transport.send_response(msg_id, result)

        except ValueError as e:
            # Application-level errors
            if msg_id is not None:
                await self.transport.send_error(msg_id, INVALID_PARAMS, str(e))

        except NotImplementedError:
            if msg_id is not None:
                await self.transport.send_error(
                    msg_id,
                    METHOD_NOT_FOUND,
                    f"Method not found: {method}",
                )

        except Exception as e:
            print(f"[ACP] Handler error for {method}: {e}", file=sys.stderr)
            import traceback

            traceback.print_exc(file=sys.stderr)
            if msg_id is not None:
                await self.transport.send_error(
                    msg_id,
                    INTERNAL_ERROR,
                    f"Internal error: {e}",
                )

    async def _handle_method(self, method: str, params: Dict[str, Any]) -> Any:
        """Route a method to its handler.

        Args:
            method: The JSON-RPC method name
            params: Method parameters

        Returns:
            Handler result

        Raises:
            NotImplementedError: If method is not supported
        """
        # Method routing table
        if method == "initialize":
            return await handle_initialize(params)

        elif method == "session/new":
            result = await handle_session_new(
                params,
                self.transport.send_notification,
            )
            return result

        elif method == "session/prompt":
            # Pass both notification and request callbacks for full functionality
            return await handle_session_prompt(
                params,
                self.transport.send_notification,
                self.transport.send_request,
            )

        elif method == "session/cancel":
            await handle_session_cancel(params)
            return None  # Notifications don't return results

        elif method == "session/load":
            return await handle_session_load(params)

        else:
            raise NotImplementedError(f"Unknown method: {method}")


async def run_acp_agent() -> None:
    """Main loop for ACP agent mode.

    This is the entry point for running Code Puppy as an ACP agent.
    It initializes the transport, then loops reading and dispatching
    messages until EOF or error.
    """
    print("[ACP] Starting Code Puppy ACP agent...", file=sys.stderr)

    transport = ACPTransport()
    dispatcher = ACPDispatcher(transport)

    try:
        await transport.start()

        # Main message loop
        while transport._running:
            message = await transport.read_message()

            if message is None:
                # EOF or fatal error
                break

            # Dispatch the message (errors are handled inside dispatch)
            await dispatcher.dispatch(message)

    except asyncio.CancelledError:
        print("[ACP] Agent cancelled", file=sys.stderr)

    except Exception as e:
        print(f"[ACP] Fatal error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc(file=sys.stderr)

    finally:
        await transport.stop()
        print("[ACP] Agent shutdown complete", file=sys.stderr)


def main() -> None:
    """Entry point for ACP mode (can be called directly)."""
    asyncio.run(run_acp_agent())


if __name__ == "__main__":
    main()
