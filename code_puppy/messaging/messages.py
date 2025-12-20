"""Structured message models for Code Puppy's messaging system.

Pydantic models that decouple message content from presentation.
NO Rich markup or formatting should be embedded in any string fields.
Renderers decide how to display these structured messages.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Literal, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field

# =============================================================================
# Enums
# =============================================================================


class MessageLevel(str, Enum):
    """Severity level for text messages."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"


class MessageCategory(str, Enum):
    """Category of message for routing and rendering decisions."""

    SYSTEM = "system"
    TOOL_OUTPUT = "tool_output"
    AGENT = "agent"
    USER_INTERACTION = "user_interaction"
    DIVIDER = "divider"


# =============================================================================
# Base Message
# =============================================================================


class BaseMessage(BaseModel):
    """Base class for all structured messages with auto-generated id and timestamp."""

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique identifier for this message instance",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this message was created (UTC)",
    )
    category: MessageCategory = Field(
        description="Category for routing and rendering decisions"
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Session ID of the agent that emitted this message (for multi-agent tracking)",
    )

    model_config = {"frozen": False, "extra": "forbid"}


# =============================================================================
# Text Messages
# =============================================================================


class TextMessage(BaseMessage):
    """Simple text message with a severity level. Text must be plain, no markup!"""

    category: MessageCategory = MessageCategory.SYSTEM
    level: MessageLevel = Field(description="Severity level of this message")
    text: str = Field(description="Plain text content - NO Rich markup allowed")


# =============================================================================
# File Operation Messages
# =============================================================================


class FileEntry(BaseModel):
    """A single file or directory entry in a listing."""

    path: str = Field(description="Path to the file or directory")
    type: Literal["file", "dir"] = Field(
        description="Whether this is a file or directory"
    )
    size: int = Field(ge=0, description="Size in bytes (0 for directories)")
    depth: int = Field(ge=0, description="Nesting depth from listing root")

    model_config = {"frozen": True, "extra": "forbid"}


class FileListingMessage(BaseMessage):
    """Result of a directory listing operation."""

    category: MessageCategory = MessageCategory.TOOL_OUTPUT
    directory: str = Field(description="Root directory that was listed")
    files: List[FileEntry] = Field(
        default_factory=list,
        description="List of file and directory entries found",
    )
    recursive: bool = Field(description="Whether the listing was recursive")
    total_size: int = Field(ge=0, description="Total size of all files in bytes")
    dir_count: int = Field(ge=0, description="Number of directories found")
    file_count: int = Field(ge=0, description="Number of files found")


class FileContentMessage(BaseMessage):
    """Content of a file that was read, with metadata for partial reads."""

    category: MessageCategory = MessageCategory.TOOL_OUTPUT
    path: str = Field(description="Path to the file that was read")
    content: str = Field(description="The file content (plain text)")
    start_line: Optional[int] = Field(
        default=None,
        ge=1,
        description="Starting line number if partial read (1-based)",
    )
    num_lines: Optional[int] = Field(
        default=None,
        ge=1,
        description="Number of lines read if partial read",
    )
    total_lines: int = Field(ge=0, description="Total lines in the file")
    num_tokens: int = Field(ge=0, description="Estimated token count of content")


class GrepMatch(BaseModel):
    """A single match from a grep/search operation."""

    file_path: str = Field(description="Path to file containing this match")
    line_number: int = Field(ge=1, description="Line number (1-based)")
    line_content: str = Field(description="Full line content containing the match")

    model_config = {"frozen": True, "extra": "forbid"}


class GrepResultMessage(BaseMessage):
    """Results from a grep/search operation with matches and statistics."""

    category: MessageCategory = MessageCategory.TOOL_OUTPUT
    search_term: str = Field(description="The search pattern used")
    directory: str = Field(description="Root directory that was searched")
    matches: List[GrepMatch] = Field(
        default_factory=list,
        description="List of matches found",
    )
    total_matches: int = Field(ge=0, description="Total number of matches")
    files_searched: int = Field(ge=0, description="Number of files searched")
    verbose: bool = Field(
        default=False,
        description="Whether to show verbose output with line content",
    )


# =============================================================================
# Diff/Modification Messages
# =============================================================================


class DiffLine(BaseModel):
    """A single line in a diff output."""

    line_number: int = Field(ge=0, description="Line number for this diff line")
    type: Literal["add", "remove", "context"] = Field(description="Type of diff line")
    content: str = Field(description="The line content")

    model_config = {"frozen": True, "extra": "forbid"}


class DiffMessage(BaseMessage):
    """A file modification with diff information for rendering."""

    category: MessageCategory = MessageCategory.TOOL_OUTPUT
    path: str = Field(description="Path to the modified file")
    operation: Literal["create", "modify", "delete"] = Field(
        description="Type of file operation"
    )
    old_content: Optional[str] = Field(
        default=None,
        description="Previous file content (None for create)",
    )
    new_content: Optional[str] = Field(
        default=None,
        description="New file content (None for delete)",
    )
    diff_lines: List[DiffLine] = Field(
        default_factory=list,
        description="Individual diff lines for rendering",
    )


# =============================================================================
# Shell Messages
# =============================================================================


class ShellStartMessage(BaseMessage):
    """Notification that a shell command has started execution."""

    category: MessageCategory = MessageCategory.TOOL_OUTPUT
    command: str = Field(description="The shell command being executed")
    cwd: Optional[str] = Field(
        default=None, description="Working directory for the command"
    )
    timeout: int = Field(default=60, description="Timeout in seconds")


class ShellLineMessage(BaseMessage):
    """A single line of shell command output with ANSI preservation."""

    category: MessageCategory = MessageCategory.TOOL_OUTPUT
    line: str = Field(description="The output line (may contain ANSI codes)")
    stream: Literal["stdout", "stderr"] = Field(
        default="stdout", description="Which output stream this line came from"
    )


class ShellOutputMessage(BaseMessage):
    """Output from a shell command execution with stdout, stderr, and timing."""

    category: MessageCategory = MessageCategory.TOOL_OUTPUT
    command: str = Field(description="The shell command that was executed")
    stdout: str = Field(default="", description="Standard output from the command")
    stderr: str = Field(default="", description="Standard error from the command")
    exit_code: int = Field(description="Process exit code (0 = success)")
    duration_seconds: float = Field(
        ge=0,
        description="How long the command took to execute",
    )


# =============================================================================
# Agent Messages
# =============================================================================


class AgentReasoningMessage(BaseMessage):
    """Agent's reasoning and planned next steps. Plain text only!"""

    category: MessageCategory = MessageCategory.AGENT
    reasoning: str = Field(description="The agent's current reasoning/thought process")
    next_steps: Optional[str] = Field(
        default=None,
        description="Planned next actions (optional)",
    )


class AgentResponseMessage(BaseMessage):
    """A response from the agent. Use is_markdown flag for markdown content."""

    category: MessageCategory = MessageCategory.AGENT
    content: str = Field(description="The response content")
    is_markdown: bool = Field(
        default=False,
        description="Whether content should be rendered as markdown",
    )


class SubAgentInvocationMessage(BaseMessage):
    """Message for sub-agent invocation header/status. Used by invoke_agent tool."""

    category: MessageCategory = MessageCategory.AGENT
    agent_name: str = Field(description="Name of the agent being invoked")
    session_id: str = Field(description="Session ID for the invocation")
    prompt: str = Field(description="The prompt being sent to the agent")
    is_new_session: bool = Field(
        description="Whether this is a new session or continuation"
    )
    message_count: int = Field(
        default=0, description="Number of messages in history (for continuation)"
    )


class SubAgentResponseMessage(BaseMessage):
    """Response from a sub-agent invocation. Rendered as markdown."""

    category: MessageCategory = MessageCategory.AGENT
    agent_name: str = Field(description="Name of the agent that responded")
    session_id: str = Field(description="Session ID for the invocation")
    response: str = Field(description="The agent's response content")
    message_count: int = Field(
        default=0, description="Number of messages now in session history"
    )


# =============================================================================
# User Interaction Messages (Agent → User)
# =============================================================================


class UserInputRequest(BaseMessage):
    """Request for text input from the user."""

    category: MessageCategory = MessageCategory.USER_INTERACTION
    prompt_id: str = Field(description="Unique ID for matching responses to requests")
    prompt_text: str = Field(description="The prompt to display to the user")
    default_value: Optional[str] = Field(
        default=None,
        description="Default value to use if user provides no input",
    )
    input_type: Literal["text", "password"] = Field(
        default="text",
        description="Type of input field (password hides input)",
    )


class ConfirmationRequest(BaseMessage):
    """Request for user confirmation with options and optional feedback."""

    category: MessageCategory = MessageCategory.USER_INTERACTION
    prompt_id: str = Field(description="Unique ID for matching responses to requests")
    title: str = Field(description="Title/headline for the confirmation")
    description: str = Field(
        description="Detailed description of what's being confirmed"
    )
    options: List[str] = Field(
        default_factory=lambda: ["Yes", "No"],
        description="Available options to choose from",
    )
    allow_feedback: bool = Field(
        default=False,
        description="Whether to allow free-form feedback in addition to selection",
    )


class SelectionRequest(BaseMessage):
    """Request for user to select from a list of options."""

    category: MessageCategory = MessageCategory.USER_INTERACTION
    prompt_id: str = Field(description="Unique ID for matching responses to requests")
    prompt_text: str = Field(description="Prompt text to display")
    options: List[str] = Field(description="List of options to choose from")
    allow_cancel: bool = Field(
        default=True,
        description="Whether the user can cancel without selecting",
    )


# =============================================================================
# Control Messages
# =============================================================================


class SpinnerControl(BaseMessage):
    """Control message for spinner/progress indicator."""

    category: MessageCategory = MessageCategory.SYSTEM
    action: Literal["start", "stop", "update", "pause", "resume"] = Field(
        description="What action to take on the spinner"
    )
    spinner_id: str = Field(description="Unique identifier for this spinner")
    text: Optional[str] = Field(
        default=None,
        description="Text to display with the spinner (for start/update)",
    )


class DividerMessage(BaseMessage):
    """Visual divider/separator between sections."""

    category: MessageCategory = MessageCategory.DIVIDER
    style: Literal["light", "heavy", "double"] = Field(
        default="light",
        description="Visual style hint for the divider",
    )


# =============================================================================
# Status Messages
# =============================================================================


class StatusPanelMessage(BaseMessage):
    """A status panel with key-value fields for structured status info."""

    category: MessageCategory = MessageCategory.SYSTEM
    title: str = Field(description="Title for the status panel")
    fields: Dict[str, str] = Field(
        default_factory=dict,
        description="Key-value pairs to display",
    )


class VersionCheckMessage(BaseMessage):
    """Result of a version check against PyPI or similar."""

    category: MessageCategory = MessageCategory.SYSTEM
    current_version: str = Field(description="Currently installed version")
    latest_version: str = Field(description="Latest available version")
    update_available: bool = Field(description="Whether an update is available")


# =============================================================================
# Union Type for Type Checking
# =============================================================================

# All concrete message types (excludes BaseMessage itself)
AnyMessage = Union[
    TextMessage,
    FileListingMessage,
    FileContentMessage,
    GrepResultMessage,
    DiffMessage,
    ShellStartMessage,
    ShellLineMessage,
    ShellOutputMessage,
    AgentReasoningMessage,
    AgentResponseMessage,
    SubAgentInvocationMessage,
    SubAgentResponseMessage,
    UserInputRequest,
    ConfirmationRequest,
    SelectionRequest,
    SpinnerControl,
    DividerMessage,
    StatusPanelMessage,
    VersionCheckMessage,
]
"""Union of all message types for type checking."""


# =============================================================================
# Export all public symbols
# =============================================================================

__all__ = [
    # Enums
    "MessageLevel",
    "MessageCategory",
    # Base
    "BaseMessage",
    # Text
    "TextMessage",
    # File operations
    "FileEntry",
    "FileListingMessage",
    "FileContentMessage",
    "GrepMatch",
    "GrepResultMessage",
    # Diff/Modification
    "DiffLine",
    "DiffMessage",
    # Shell
    "ShellStartMessage",
    "ShellLineMessage",
    "ShellOutputMessage",
    # Agent
    "AgentReasoningMessage",
    "AgentResponseMessage",
    "SubAgentInvocationMessage",
    "SubAgentResponseMessage",
    # User interaction
    "UserInputRequest",
    "ConfirmationRequest",
    "SelectionRequest",
    # Control
    "SpinnerControl",
    "DividerMessage",
    # Status
    "StatusPanelMessage",
    "VersionCheckMessage",
    # Union type
    "AnyMessage",
]
