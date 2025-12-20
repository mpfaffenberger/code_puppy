"""MessageBus - Central coordinator for bidirectional Agent <-> UI communication.

The MessageBus manages two queues:
- outgoing: Messages flow from Agent → UI (AnyMessage)
- incoming: Commands flow from UI → Agent (AnyCommand)

It also handles request/response correlation for user interactions:
1. Agent calls request_input() which emits a UserInputRequest and waits
2. UI receives the request and displays a prompt
3. User provides input, UI calls provide_response() with UserInputResponse
4. MessageBus matches the response to the waiting request via prompt_id
5. Agent's request_input() returns with the user's value

    ┌─────────────────────────────────────────────────────────────┐
    │                       MessageBus                             │
    │  ┌─────────────┐                      ┌─────────────┐       │
    │  │  outgoing   │  Messages (Agent→UI) │  incoming   │       │
    │  │   Queue     │ ───────────────────> │   Queue     │       │
    │  │ [AnyMessage]│                      │ [AnyCommand]│       │
    │  └─────────────┘                      └─────────────┘       │
    │         ↑                                    │              │
    │         │                                    ↓              │
    │    emit()                           provide_response()      │
    │    emit_text()                                              │
    │    request_input() ─────────────────────────────────────────│
    │         ↑              (waits for matching response)        │
    │         │                                                   │
    │  ┌──────┴──────┐                                            │
    │  │  pending    │  prompt_id → Future                        │
    │  │  requests   │                                            │
    │  └─────────────┘                                            │
    └─────────────────────────────────────────────────────────────┘
"""

import asyncio
import queue
import threading
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from .commands import (
    AnyCommand,
    ConfirmationResponse,
    SelectionResponse,
    UserInputResponse,
)
from .messages import (
    AnyMessage,
    ConfirmationRequest,
    MessageCategory,
    MessageLevel,
    SelectionRequest,
    TextMessage,
    UserInputRequest,
)


class MessageBus:
    """Central coordinator for bidirectional Agent <-> UI communication.

    Thread-safe message bus that works in both sync and async contexts.
    Uses stdlib queue.Queue for thread-safe sync operation.
    Manages outgoing messages, incoming commands, and request/response correlation.
    """

    def __init__(self, maxsize: int = 1000) -> None:
        """Initialize the MessageBus.

        Args:
            maxsize: Maximum queue size before blocking/dropping.
        """
        self._maxsize = maxsize
        self._lock = threading.Lock()

        # Use sync queues by default (works in any context)
        self._outgoing: queue.Queue[AnyMessage] = queue.Queue(maxsize=maxsize)
        self._incoming: queue.Queue[AnyCommand] = queue.Queue(maxsize=maxsize)

        # Event loop reference for async request/response (optional)
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None

        # Startup buffering
        self._startup_buffer: List[AnyMessage] = []
        self._has_active_renderer = False

        # Request/Response correlation: prompt_id → Future (for async usage)
        self._pending_requests: Dict[str, asyncio.Future[Any]] = {}

        # Session context for multi-agent tracking
        self._current_session_id: Optional[str] = None

    # =========================================================================
    # Outgoing Messages (Agent → UI)
    # =========================================================================

    def emit(self, message: AnyMessage) -> None:
        """Emit a message to the UI.

        Thread-safe. Can be called from sync or async context.
        If no renderer is active, messages are buffered for later.
        Auto-tags message with current session_id if not already set.

        Args:
            message: The message to emit.
        """
        # Auto-tag message with current session if not already set
        with self._lock:
            if message.session_id is None and self._current_session_id is not None:
                message.session_id = self._current_session_id

            if not self._has_active_renderer:
                self._startup_buffer.append(message)
                return

        # Direct put into thread-safe queue
        try:
            self._outgoing.put_nowait(message)
        except queue.Full:
            # Drop oldest and retry
            try:
                self._outgoing.get_nowait()
                self._outgoing.put_nowait(message)
            except queue.Empty:
                pass

    def emit_text(
        self,
        level: MessageLevel,
        text: str,
        category: MessageCategory = MessageCategory.SYSTEM,
    ) -> None:
        """Emit a text message with the specified level.

        Args:
            level: Severity level (DEBUG, INFO, WARNING, ERROR, SUCCESS).
            text: Plain text content (no Rich markup!).
            category: Message category for routing.
        """
        message = TextMessage(level=level, text=text, category=category)
        self.emit(message)

    def emit_info(self, text: str) -> None:
        """Emit an INFO level text message."""
        self.emit_text(MessageLevel.INFO, text)

    def emit_warning(self, text: str) -> None:
        """Emit a WARNING level text message."""
        self.emit_text(MessageLevel.WARNING, text)

    def emit_error(self, text: str) -> None:
        """Emit an ERROR level text message."""
        self.emit_text(MessageLevel.ERROR, text)

    def emit_success(self, text: str) -> None:
        """Emit a SUCCESS level text message."""
        self.emit_text(MessageLevel.SUCCESS, text)

    def emit_debug(self, text: str) -> None:
        """Emit a DEBUG level text message."""
        self.emit_text(MessageLevel.DEBUG, text)

    def emit_shell_line(self, line: str, stream: str = "stdout") -> None:
        """Emit a shell output line with ANSI preservation.

        Args:
            line: The output line (may contain ANSI codes).
            stream: Which stream this came from ("stdout" or "stderr").
        """
        from .messages import ShellLineMessage

        message = ShellLineMessage(line=line, stream=stream)  # type: ignore[arg-type]
        self.emit(message)

    # =========================================================================
    # Session Context (Multi-Agent Tracking)
    # =========================================================================

    def set_session_context(self, session_id: Optional[str]) -> None:
        """Set the current session context for auto-tagging messages.

        When set, all messages emitted via emit() will be automatically tagged
        with this session_id unless they already have one set.

        Args:
            session_id: The session ID to tag messages with, or None to clear.
        """
        with self._lock:
            self._current_session_id = session_id

    def get_session_context(self) -> Optional[str]:
        """Get the current session context.

        Returns:
            The current session_id, or None if not set.
        """
        with self._lock:
            return self._current_session_id

    # =========================================================================
    # User Input Requests (Agent waits for UI response)
    # =========================================================================

    async def request_input(
        self,
        prompt_text: str,
        default: Optional[str] = None,
        input_type: str = "text",
    ) -> str:
        """Request text input from the user.

        Emits a UserInputRequest and blocks until the UI provides a response.

        Args:
            prompt_text: The prompt to display to the user.
            default: Default value if user provides empty input.
            input_type: "text" or "password".

        Returns:
            The user's input string.
        """
        prompt_id = str(uuid4())

        # Create a Future to wait on
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()

        with self._lock:
            self._pending_requests[prompt_id] = future

        # Emit the request
        request = UserInputRequest(
            prompt_id=prompt_id,
            prompt_text=prompt_text,
            default_value=default,
            input_type=input_type,  # type: ignore[arg-type]
        )
        self.emit(request)

        try:
            # Wait for response
            result = await future
            return result if result else (default or "")
        finally:
            # Clean up
            with self._lock:
                self._pending_requests.pop(prompt_id, None)

    async def request_confirmation(
        self,
        title: str,
        description: str,
        options: Optional[List[str]] = None,
        allow_feedback: bool = False,
    ) -> Tuple[bool, Optional[str]]:
        """Request confirmation from the user.

        Emits a ConfirmationRequest and blocks until the UI provides a response.

        Args:
            title: Title/headline for the confirmation.
            description: Detailed description of what's being confirmed.
            options: Options to choose from (default: ["Yes", "No"]).
            allow_feedback: Whether to allow free-form feedback.

        Returns:
            Tuple of (confirmed: bool, feedback: Optional[str]).
        """
        prompt_id = str(uuid4())

        loop = asyncio.get_running_loop()
        future: asyncio.Future[Tuple[bool, Optional[str]]] = loop.create_future()

        with self._lock:
            self._pending_requests[prompt_id] = future

        request = ConfirmationRequest(
            prompt_id=prompt_id,
            title=title,
            description=description,
            options=options or ["Yes", "No"],
            allow_feedback=allow_feedback,
        )
        self.emit(request)

        try:
            return await future
        finally:
            with self._lock:
                self._pending_requests.pop(prompt_id, None)

    async def request_selection(
        self,
        prompt_text: str,
        options: List[str],
        allow_cancel: bool = True,
    ) -> Tuple[int, str]:
        """Request the user to select from a list of options.

        Emits a SelectionRequest and blocks until the UI provides a response.

        Args:
            prompt_text: The prompt to display.
            options: List of options to choose from.
            allow_cancel: Whether the user can cancel without selecting.

        Returns:
            Tuple of (selected_index: int, selected_value: str).
            Returns (-1, "") if cancelled.
        """
        prompt_id = str(uuid4())

        loop = asyncio.get_running_loop()
        future: asyncio.Future[Tuple[int, str]] = loop.create_future()

        with self._lock:
            self._pending_requests[prompt_id] = future

        request = SelectionRequest(
            prompt_id=prompt_id,
            prompt_text=prompt_text,
            options=options,
            allow_cancel=allow_cancel,
        )
        self.emit(request)

        try:
            return await future
        finally:
            with self._lock:
                self._pending_requests.pop(prompt_id, None)

    # =========================================================================
    # Incoming Commands (UI → Agent)
    # =========================================================================

    def provide_response(self, command: AnyCommand) -> None:
        """Provide a response to a pending request.

        Called by the UI when the user provides input, confirmation, or selection.
        Matches the response to the waiting request via prompt_id.

        Args:
            command: The response command (UserInputResponse, etc.).
        """
        # Handle user interaction responses
        if isinstance(command, UserInputResponse):
            self._complete_request(command.prompt_id, command.value)
        elif isinstance(command, ConfirmationResponse):
            self._complete_request(
                command.prompt_id, (command.confirmed, command.feedback)
            )
        elif isinstance(command, SelectionResponse):
            self._complete_request(
                command.prompt_id, (command.selected_index, command.selected_value)
            )
        else:
            # For non-response commands (CancelAgentCommand, etc.),
            # put them in the incoming queue for the agent to process
            try:
                self._incoming.put_nowait(command)
            except queue.Full:
                # Drop oldest and retry
                try:
                    self._incoming.get_nowait()
                    self._incoming.put_nowait(command)
                except queue.Empty:
                    pass

    def _complete_request(self, prompt_id: str, result: object) -> None:
        """Complete a pending request with the given result."""
        with self._lock:
            future = self._pending_requests.get(prompt_id)

        if future is not None and not future.done():
            # Must set result from the event loop thread if we have one
            if self._event_loop is not None:
                try:
                    self._event_loop.call_soon_threadsafe(
                        self._set_future_result, future, result
                    )
                except RuntimeError:
                    # Event loop closed - try direct set
                    self._set_future_result(future, result)
            else:
                # No event loop - try direct set
                self._set_future_result(future, result)

    def _set_future_result(self, future: asyncio.Future[Any], result: object) -> None:
        """Set a future's result if not already done."""
        if not future.done():
            future.set_result(result)

    # =========================================================================
    # Queue Access (for renderers/consumers)
    # =========================================================================

    async def get_message(self) -> AnyMessage:
        """Get the next outgoing message (async).

        Called by the renderer to consume messages.
        Blocks until a message is available.

        Returns:
            The next message to display.
        """
        # For async usage, wrap sync queue in asyncio-friendly way
        while True:
            try:
                return self._outgoing.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.01)

    def get_message_nowait(self) -> Optional[AnyMessage]:
        """Get the next outgoing message without blocking.

        Returns:
            The next message, or None if queue is empty.
        """
        try:
            return self._outgoing.get_nowait()
        except queue.Empty:
            return None

    async def get_command(self) -> AnyCommand:
        """Get the next incoming command (async).

        Called by the agent to consume commands (e.g., CancelAgentCommand).
        Blocks until a command is available.

        Returns:
            The next command to process.
        """
        # For async usage, wrap sync queue in asyncio-friendly way
        while True:
            try:
                return self._incoming.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.01)

    # =========================================================================
    # Startup Buffering
    # =========================================================================

    def get_buffered_messages(self) -> List[AnyMessage]:
        """Get all messages buffered before renderer attached.

        Returns a copy of the buffer. Call clear_buffer() after processing.

        Returns:
            List of buffered messages.
        """
        with self._lock:
            return list(self._startup_buffer)

    def clear_buffer(self) -> None:
        """Clear the startup buffer after processing."""
        with self._lock:
            self._startup_buffer.clear()

    def mark_renderer_active(self) -> None:
        """Mark that a renderer is now active and consuming messages.

        Call this when a renderer attaches. Messages will no longer be
        buffered and will go directly to the outgoing queue.
        """
        with self._lock:
            self._has_active_renderer = True

    def mark_renderer_inactive(self) -> None:
        """Mark that no renderer is currently active.

        Messages will be buffered until a renderer attaches again.
        """
        with self._lock:
            self._has_active_renderer = False

    @property
    def has_active_renderer(self) -> bool:
        """Check if a renderer is currently active."""
        with self._lock:
            return self._has_active_renderer

    # =========================================================================
    # Queue Status
    # =========================================================================

    @property
    def outgoing_qsize(self) -> int:
        """Number of messages waiting in the outgoing queue."""
        return self._outgoing.qsize()

    @property
    def incoming_qsize(self) -> int:
        """Number of commands waiting in the incoming queue."""
        return self._incoming.qsize()

    @property
    def pending_requests_count(self) -> int:
        """Number of requests waiting for responses."""
        with self._lock:
            return len(self._pending_requests)


# =============================================================================
# Global Singleton
# =============================================================================

_global_bus: Optional[MessageBus] = None
_bus_lock = threading.Lock()


def get_message_bus() -> MessageBus:
    """Get or create the global MessageBus singleton.

    Thread-safe. Creates the bus on first call.

    Returns:
        The global MessageBus instance.
    """
    global _global_bus

    with _bus_lock:
        if _global_bus is None:
            _global_bus = MessageBus()
        return _global_bus


def reset_message_bus() -> None:
    """Reset the global MessageBus (for testing).

    Warning: This will lose any pending messages/requests!
    """
    global _global_bus

    with _bus_lock:
        _global_bus = None


# =============================================================================
# Convenience Functions
# =============================================================================


def emit(message: AnyMessage) -> None:
    """Emit a message via the global bus."""
    get_message_bus().emit(message)


def emit_info(text: str) -> None:
    """Emit an INFO message via the global bus."""
    get_message_bus().emit_info(text)


def emit_warning(text: str) -> None:
    """Emit a WARNING message via the global bus."""
    get_message_bus().emit_warning(text)


def emit_error(text: str) -> None:
    """Emit an ERROR message via the global bus."""
    get_message_bus().emit_error(text)


def emit_success(text: str) -> None:
    """Emit a SUCCESS message via the global bus."""
    get_message_bus().emit_success(text)


def emit_debug(text: str) -> None:
    """Emit a DEBUG message via the global bus."""
    get_message_bus().emit_debug(text)


def emit_shell_line(line: str, stream: str = "stdout") -> None:
    """Emit a shell output line with ANSI preservation."""
    get_message_bus().emit_shell_line(line, stream)


def set_session_context(session_id: Optional[str]) -> None:
    """Set the session context on the global bus."""
    get_message_bus().set_session_context(session_id)


def get_session_context() -> Optional[str]:
    """Get the session context from the global bus."""
    return get_message_bus().get_session_context()


# =============================================================================
# Export all public symbols
# =============================================================================

__all__ = [
    # Main class
    "MessageBus",
    # Singleton access
    "get_message_bus",
    "reset_message_bus",
    # Convenience functions
    "emit",
    "emit_info",
    "emit_warning",
    "emit_error",
    "emit_success",
    "emit_debug",
    "emit_shell_line",
    # Session context
    "set_session_context",
    "get_session_context",
]
