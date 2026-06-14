"""WebSocket protocol schemas — single source of truth for the CP wire protocol.

Every client→server and server→client message is defined here as a Pydantic
model with ``Literal`` type discriminators so the framework can parse raw JSON
into the correct model automatically via ``ClientMessage`` / ``ServerMessage``
discriminated unions.

Serialisation convention:
    ``.model_dump(exclude_none=True)`` — optional fields that are ``None``
    are omitted from the wire representation to keep payloads lean.

All field names and types are derived from the *actual* ``send_json`` /
``safe_send_json`` calls in ``chat_handler.py`` and ``permissions.py``.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Discriminator, Field, Tag

# ── Protocol version ────────────────────────────────────────────────────────
PROTOCOL_VERSION = "1.0.0"


# ── Enums ────────────────────────────────────────────────────────────────────


class ClientMessageType(str, Enum):
    """All ``type`` values a client may send over the WebSocket."""

    MESSAGE = "message"
    SWITCH_AGENT = "switch_agent"
    SWITCH_MODEL = "switch_model"
    SWITCH_SESSION = "switch_session"
    SET_WORKING_DIRECTORY = "set_working_directory"
    UPDATE_SESSION_META = "update_session_meta"
    GET_CONFIG = "get_config"
    SET_CONFIG = "set_config"
    COMMAND = "command"
    CANCEL = "cancel"
    PERMISSION_RESPONSE = "permission_response"
    USER_INPUT_RESPONSE = "user_input_response"
    CONFIRMATION_RESPONSE = "confirmation_response"
    SELECTION_RESPONSE = "selection_response"
    ASK_USER_QUESTION_RESPONSE = "ask_user_question_response"


class ServerMessageType(str, Enum):
    """All ``type`` values the server may send over the WebSocket."""

    SYSTEM = "system"
    SESSION_META = "session_meta"
    SESSION_RESTORED = "session_restored"
    SESSION_SWITCHED = "session_switched"
    WORKING_DIRECTORY_CHANGED = "working_directory_changed"
    SESSION_META_UPDATED = "session_meta_updated"
    CONFIG_VALUE = "config_value"
    COMMAND_RESULT = "command_result"
    STATUS = "status"
    USER_MESSAGE = "user_message"
    ASSISTANT_MESSAGE_START = "assistant_message_start"
    ASSISTANT_MESSAGE_DELTA = "assistant_message_delta"
    ASSISTANT_MESSAGE_END = "assistant_message_end"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TOOL_RETURN = "tool_return"
    AGENT_INVOKED = "agent_invoked"
    RESPONSE = "response"
    STREAM_END = "stream_end"
    ERROR = "error"
    PERMISSION_REQUEST = "permission_request"
    USER_INPUT_REQUEST = "user_input_request"
    CONFIRMATION_REQUEST = "confirmation_request"
    SELECTION_REQUEST = "selection_request"
    ASK_USER_QUESTION_REQUEST = "ask_user_question_request"
    CANCELLED = "cancelled"


class PartType(str, Enum):
    """Streaming part types used in ``assistant_message_start``."""

    TEXT = "text"
    THINKING = "thinking"
    TOOL_CALL = "tool_call"


class ErrorType(str, Enum):
    """Error categories returned by ``parse_api_error`` / ``error_parser``."""

    RATE_LIMIT = "rate_limit"
    SERVER_ERROR = "server_error"
    AUTH_ERROR = "auth_error"
    QUOTA_EXCEEDED = "quota_exceeded"
    CONTENT_BLOCKED = "content_blocked"
    TOOL_HISTORY_ERROR = "tool_history_error"
    NETWORK_ERROR = "network_error"
    MODEL_NOT_FOUND = "model_not_found"
    CLAUDE_TEMPERATURE_ERROR = "claude_temperature_error"
    UNKNOWN = "unknown"
    UNKNOWN_ERROR = "unknown_error"


# ── Base ─────────────────────────────────────────────────────────────────────


class _BaseMessage(BaseModel):
    """Shared config for all protocol messages."""

    model_config = {"extra": "allow"}


# ═══════════════════════════════════════════════════════════════════════════════
# CLIENT → SERVER  (11 message types)
# ═══════════════════════════════════════════════════════════════════════════════


class ClientMessageMessage(_BaseMessage):
    """User chat message.

    Sent when the user types a message in the chat input.
    ``content`` is the message text.  Optional ``model`` overrides the
    session model for this single turn.  ``model_settings`` passes
    per-request knobs (e.g. reasoning_effort).  ``attachments`` is a
    list of file paths to include.
    """

    type: Literal["message"] = "message"
    content: str
    model: Optional[str] = None
    model_settings: Optional[Dict[str, Any]] = None
    attachments: Optional[List[str]] = None


class ClientSwitchAgent(_BaseMessage):
    """Request to switch the active agent.

    ``agent_name`` is the target agent identifier (e.g. ``"code-puppy"``).
    """

    type: Literal["switch_agent"] = "switch_agent"
    agent_name: str


class ClientSwitchModel(_BaseMessage):
    """Request to switch the active model.

    The server accepts either ``model_name`` or ``model`` for backwards
    compatibility — see ``msg.get("model_name") or msg.get("model")``.
    """

    type: Literal["switch_model"] = "switch_model"
    model_name: Optional[str] = None
    model: Optional[str] = None


class ClientSwitchSession(_BaseMessage):
    """Request to switch to a different chat session.

    ``session_id`` is the target session identifier.
    """

    type: Literal["switch_session"] = "switch_session"
    session_id: str


class ClientSetWorkingDirectory(_BaseMessage):
    """Set the working directory for the current session.

    ``directory`` is an absolute filesystem path.
    """

    type: Literal["set_working_directory"] = "set_working_directory"
    directory: str


class ClientUpdateSessionMeta(_BaseMessage):
    """Update session metadata (title, pinned state).

    Both fields are optional — only supplied fields are updated.
    """

    type: Literal["update_session_meta"] = "update_session_meta"
    title: Optional[str] = None
    pinned: Optional[bool] = None


class ClientGetConfig(_BaseMessage):
    """Read a configuration value by key."""

    type: Literal["get_config"] = "get_config"
    key: str


class ClientSetConfig(_BaseMessage):
    """Write a configuration value."""

    type: Literal["set_config"] = "set_config"
    key: str
    value: Any


class ClientCommand(_BaseMessage):
    """Execute a slash command (e.g. ``/help``)."""

    type: Literal["command"] = "command"
    command: str


class ClientCancel(_BaseMessage):
    """Cancel / interrupt the current streaming response or agent run."""

    type: Literal["cancel"] = "cancel"


class ClientPermissionResponse(_BaseMessage):
    """User's response to a permission request.

    ``approved`` indicates whether the user granted the permission.
    ``remember`` is reserved for future "always allow" support.
    """

    type: Literal["permission_response"] = "permission_response"
    request_id: str
    approved: bool
    remember: Optional[bool] = None


class ClientUserInputResponse(_BaseMessage):
    """Response to a free-form input prompt emitted by the runtime."""

    type: Literal["user_input_response"] = "user_input_response"
    prompt_id: str
    value: str


class ClientConfirmationResponse(_BaseMessage):
    """Response to a confirmation prompt emitted by the runtime."""

    type: Literal["confirmation_response"] = "confirmation_response"
    prompt_id: str
    confirmed: bool
    feedback: Optional[str] = None


class ClientSelectionResponse(_BaseMessage):
    """Response to an option-selection prompt emitted by the runtime."""

    type: Literal["selection_response"] = "selection_response"
    prompt_id: str
    selected_index: int
    selected_value: str


class ClientAskUserQuestionResponse(_BaseMessage):
    """Response to a structured ask_user_question prompt emitted by the runtime."""

    type: Literal["ask_user_question_response"] = "ask_user_question_response"
    prompt_id: str
    answers: List[Dict[str, Any]] = Field(default_factory=list)
    cancelled: bool = False


# ═══════════════════════════════════════════════════════════════════════════════
# SERVER → CLIENT  (user-visible message types)
# ═══════════════════════════════════════════════════════════════════════════════


class ServerSystem(_BaseMessage):
    """System / informational message.

    Sent on initial connection (welcome), agent/model switches, and
    replayed directory banners on session restore.
    """

    type: Literal["system"] = "system"
    content: str
    session_id: str
    agent_name: Optional[str] = None
    model_name: Optional[str] = None
    resumed: Optional[bool] = None
    protocol_version: Optional[str] = None


class ServerSessionRestored(_BaseMessage):
    """Confirmation that an existing session was restored from storage.

    ``message_count`` reflects how many messages were loaded into the
    agent's history.  ``ui_metadata`` carries replayed UI-only records.
    """

    type: Literal["session_restored"] = "session_restored"
    session_id: str
    message_count: int
    title: Optional[str] = None
    ui_metadata: Optional[List[Any]] = None


class ServerSessionSwitched(_BaseMessage):
    """Confirmation that the active session was switched.

    ``created`` is ``True`` when the target session did not exist and
    was freshly created.
    """

    type: Literal["session_switched"] = "session_switched"
    session_id: str
    message_count: int
    title: Optional[str] = None
    working_directory: Optional[str] = None
    created: bool
    agent_name: Optional[str] = None
    model_name: Optional[str] = None


class ServerWorkingDirectoryChanged(_BaseMessage):
    """Result of a ``set_working_directory`` request.

    ``success`` is ``False`` when the directory does not exist.
    ``unchanged`` is ``True`` when the directory matches the current one.
    """

    type: Literal["working_directory_changed"] = "working_directory_changed"
    directory: str
    success: bool
    session_id: str
    unchanged: Optional[bool] = None
    error: Optional[str] = None


class ServerSessionMetaUpdated(_BaseMessage):
    """Acknowledgement that session metadata was updated."""

    type: Literal["session_meta_updated"] = "session_meta_updated"
    session_id: str
    pinned: Optional[bool] = None
    title: Optional[str] = None


class ServerConfigValue(_BaseMessage):
    """Response to ``get_config`` or ``set_config``.

    ``success`` is present only on ``set_config`` responses.
    """

    type: Literal["config_value"] = "config_value"
    key: str
    value: Any
    session_id: str
    success: Optional[bool] = None


class ServerCommandResult(_BaseMessage):
    """Result of a slash command execution.

    ``output`` contains rendered text (e.g. help output).
    ``error`` is present when the command raised an exception.
    """

    type: Literal["command_result"] = "command_result"
    command: str
    success: bool
    session_id: str
    output: Optional[str] = None
    messages: Optional[List[Any]] = None
    result: Optional[str] = None
    error: Optional[str] = None


class ServerStatus(_BaseMessage):
    """Transient status update (e.g. ``"cancelled"``, ``"thinking"``).

    Sent in response to a ``cancel`` request or to indicate agent
    activity (e.g. "thinking" with current agent/model context).
    """

    type: Literal["status"] = "status"
    status: str
    session_id: str
    agent_name: Optional[str] = None
    model_name: Optional[str] = None


class ServerUserMessage(_BaseMessage):
    """Echo of the user's chat message back to the client.

    Sent immediately after receiving a ``message`` from the client so
    the UI can render it before the assistant starts responding.
    """

    type: Literal["user_message"] = "user_message"
    content: str
    session_id: str


class ServerAssistantMessageStart(_BaseMessage):
    """Marks the beginning of a streaming assistant message part.

    ``part_type`` is ``"text"`` or ``"thinking"``.
    ``tool_name`` is set when the text part follows a tool call.
    """

    type: Literal["assistant_message_start"] = "assistant_message_start"
    message_id: str
    part_type: str
    part_index: int
    timestamp: float
    session_id: str
    agent_name: Optional[str] = None
    model_name: Optional[str] = None
    tool_name: Optional[str] = None


class ServerAssistantMessageDelta(_BaseMessage):
    """A streaming content chunk for an in-progress assistant message."""

    type: Literal["assistant_message_delta"] = "assistant_message_delta"
    message_id: str
    content: str
    part_index: int
    session_id: str
    agent_name: Optional[str] = None
    model_name: Optional[str] = None
    tool_name: Optional[str] = None


class ServerAssistantMessageEnd(_BaseMessage):
    """Marks the end of a streaming assistant message part.

    ``full_content`` contains the complete accumulated text for the part.
    ``part_type`` mirrors ``assistant_message_start`` for GUI reducers that
    route text/thinking/tool-call parts consistently.
    """

    type: Literal["assistant_message_end"] = "assistant_message_end"
    message_id: str
    part_type: Optional[str] = None
    part_index: int
    full_content: str
    timestamp: float
    session_id: str
    agent_name: Optional[str] = None
    model_name: Optional[str] = None
    tool_name: Optional[str] = None


class ServerToolCall(_BaseMessage):
    """Notification that a tool was invoked.

    ``args`` contains the parsed tool arguments.  ``tool_id`` correlates
    with a later ``tool_result`` bearing the same ID. ``tool_group_id``
    groups parallel tool calls in the same execution batch.
    """

    type: Literal["tool_call"] = "tool_call"
    tool_id: str
    tool_name: str
    args: Any  # dict after JSON parse, but may be raw str during streaming
    timestamp: float
    session_id: str
    agent_name: Optional[str] = None
    model_name: Optional[str] = None
    tool_group_id: Optional[str] = None  # Groups tools in same execution batch


class ServerToolResult(_BaseMessage):
    """Result of a tool execution.

    ``tool_id`` matches the originating ``tool_call``.  ``result`` is the
    tool's return value (may be ``dict``, ``str``, or a status sentinel).
    ``tool_group_id`` matches the originating ``tool_call`` group.
    """

    type: Literal["tool_result"] = "tool_result"
    tool_name: str
    result: Any
    success: bool
    duration_ms: float
    timestamp: float
    session_id: str
    tool_id: Optional[str] = None
    agent_name: Optional[str] = None
    model_name: Optional[str] = None
    tool_group_id: Optional[str] = None  # Matches originating tool_call group


class ServerToolReturn(_BaseMessage):
    """Internal tool-return part tracked during streaming.

    This message type represents a ``ToolReturnPart`` observed in the
    streaming pipeline.  It is stored internally for correlation but may
    not always be sent directly to the client.
    """

    type: Literal["tool_return"] = "tool_return"
    tool_call_id: Optional[str] = None
    content: Optional[Any] = None
    session_id: Optional[str] = None


class ServerAgentInvoked(_BaseMessage):
    """Notification that a sub-agent was invoked.

    ``prompt_preview`` is a truncated preview of the prompt sent to the
    sub-agent.
    """

    type: Literal["agent_invoked"] = "agent_invoked"
    agent_name: str
    prompt_preview: Optional[str] = None
    timestamp: float
    session_id: str


class TokenUsage(BaseModel):
    """Token usage statistics attached to ``response`` and ``stream_end``."""

    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    estimated: Optional[bool] = None


class ServerResponse(_BaseMessage):
    """Complete (non-streaming) response.

    Sent when B1 streaming was *not* used (e.g. non-streaming models).
    ``tokens`` carries optional token usage info.
    """

    type: Literal["response"] = "response"
    content: str
    done: bool
    session_id: str
    agent_name: Optional[str] = None
    model_name: Optional[str] = None
    tokens: Optional[Union[TokenUsage, Dict[str, Any]]] = None


class ServerStreamEnd(_BaseMessage):
    """End-of-stream marker for B1 streaming responses.

    ``success`` is ``False`` when the stream ended due to an error.
    ``total_length`` is the character count of the accumulated response.
    """

    type: Literal["stream_end"] = "stream_end"
    success: bool
    session_id: str
    total_length: Optional[int] = None
    agent_name: Optional[str] = None
    model_name: Optional[str] = None
    tokens: Optional[Union[TokenUsage, Dict[str, Any]]] = None


class ServerError(_BaseMessage):
    """Error message.

    ``error_type`` classifies the error for frontend handling (e.g.
    ``"rate_limit"``, ``"auth_error"``).  ``action_required`` hints
    that user intervention may be needed.
    """

    type: Literal["error"] = "error"
    error: str
    session_id: str
    error_type: Optional[str] = None
    technical_details: Optional[str] = None
    action_required: Optional[bool] = None


class ServerPermissionRequest(_BaseMessage):
    """Asks the user to approve or deny a potentially dangerous operation.

    Sent by the permission system before executing shell commands or
    other privileged operations.  The frontend should present an
    approve/deny dialog and reply with ``permission_response``.
    """

    type: Literal["permission_request"] = "permission_request"
    request_id: str
    permission_type: str
    title: str
    description: str
    details: Dict[str, Any]
    session_id: str
    timeout_seconds: int


class ServerUserInputRequest(_BaseMessage):
    """Ask the browser UI to collect free-form text from the user."""

    type: Literal["user_input_request"] = "user_input_request"
    prompt_id: str
    prompt_text: str
    session_id: str
    default_value: Optional[str] = None
    input_type: Literal["text", "password"] = "text"


class ServerConfirmationRequest(_BaseMessage):
    """Ask the browser UI to collect a yes/no-style confirmation."""

    type: Literal["confirmation_request"] = "confirmation_request"
    prompt_id: str
    title: str
    description: str
    session_id: str
    options: List[str] = []
    allow_feedback: bool = False


class ServerSelectionRequest(_BaseMessage):
    """Ask the browser UI to collect one selected option from a list."""

    type: Literal["selection_request"] = "selection_request"
    prompt_id: str
    prompt_text: str
    options: List[str]
    session_id: str
    allow_cancel: bool = True


class ServerAskUserQuestionRequest(_BaseMessage):
    """Ask the browser UI to collect structured ask_user_question answers."""

    type: Literal["ask_user_question_request"] = "ask_user_question_request"
    prompt_id: str
    questions: List[Dict[str, Any]]
    session_id: str
    timeout_seconds: int = 300


class ServerCancelled(_BaseMessage):
    """Confirmation that the current agent run was cancelled.

    Sent when the agent task is interrupted after a ``cancel`` request.
    """

    type: Literal["cancelled"] = "cancelled"
    session_id: str


# ═══════════════════════════════════════════════════════════════════════════════
# Discriminated unions
# ═══════════════════════════════════════════════════════════════════════════════


ClientMessage = Annotated[
    Union[
        Annotated[ClientMessageMessage, Tag("message")],
        Annotated[ClientSwitchAgent, Tag("switch_agent")],
        Annotated[ClientSwitchModel, Tag("switch_model")],
        Annotated[ClientSwitchSession, Tag("switch_session")],
        Annotated[ClientSetWorkingDirectory, Tag("set_working_directory")],
        Annotated[ClientUpdateSessionMeta, Tag("update_session_meta")],
        Annotated[ClientGetConfig, Tag("get_config")],
        Annotated[ClientSetConfig, Tag("set_config")],
        Annotated[ClientCommand, Tag("command")],
        Annotated[ClientCancel, Tag("cancel")],
        Annotated[ClientPermissionResponse, Tag("permission_response")],
        Annotated[ClientUserInputResponse, Tag("user_input_response")],
        Annotated[ClientConfirmationResponse, Tag("confirmation_response")],
        Annotated[ClientSelectionResponse, Tag("selection_response")],
        Annotated[ClientAskUserQuestionResponse, Tag("ask_user_question_response")],
    ],
    Discriminator("type"),
]
"""Discriminated union of all client→server message types."""

ServerMessage = Annotated[
    Union[
        Annotated[ServerSystem, Tag("system")],
        Annotated[ServerSessionRestored, Tag("session_restored")],
        Annotated[ServerSessionSwitched, Tag("session_switched")],
        Annotated[ServerWorkingDirectoryChanged, Tag("working_directory_changed")],
        Annotated[ServerSessionMetaUpdated, Tag("session_meta_updated")],
        Annotated[ServerConfigValue, Tag("config_value")],
        Annotated[ServerCommandResult, Tag("command_result")],
        Annotated[ServerStatus, Tag("status")],
        Annotated[ServerUserMessage, Tag("user_message")],
        Annotated[ServerAssistantMessageStart, Tag("assistant_message_start")],
        Annotated[ServerAssistantMessageDelta, Tag("assistant_message_delta")],
        Annotated[ServerAssistantMessageEnd, Tag("assistant_message_end")],
        Annotated[ServerToolCall, Tag("tool_call")],
        Annotated[ServerToolResult, Tag("tool_result")],
        Annotated[ServerToolReturn, Tag("tool_return")],
        Annotated[ServerAgentInvoked, Tag("agent_invoked")],
        Annotated[ServerResponse, Tag("response")],
        Annotated[ServerStreamEnd, Tag("stream_end")],
        Annotated[ServerError, Tag("error")],
        Annotated[ServerPermissionRequest, Tag("permission_request")],
        Annotated[ServerUserInputRequest, Tag("user_input_request")],
        Annotated[ServerConfirmationRequest, Tag("confirmation_request")],
        Annotated[ServerSelectionRequest, Tag("selection_request")],
        Annotated[ServerAskUserQuestionRequest, Tag("ask_user_question_request")],
        Annotated[ServerCancelled, Tag("cancelled")],
    ],
    Discriminator("type"),
]
"""Discriminated union of all server→client message types."""
