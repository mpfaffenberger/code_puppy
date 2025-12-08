"""Command models for User → Agent communication in Code Puppy's messaging system.

This module defines Pydantic models for commands that flow FROM the UI TO the Agent.
This is the opposite direction of messages.py (which flows Agent → UI).

Commands are used for:
- Controlling agent execution (cancel, interrupt)
- Responding to agent requests for user input
- Providing confirmations and selections

The UI layer creates these commands and sends them to the agent/runtime.
The agent processes them and may emit messages in response.

    ┌─────────┐   Commands    ┌─────────┐
    │   UI    │ ────────────> │  Agent  │
    │ (User)  │               │         │
    │         │ <──────────── │         │
    └─────────┘   Messages    └─────────┘

NO Rich markup or formatting should be embedded in any string fields.
"""

from datetime import datetime, timezone
from typing import Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field

# =============================================================================
# Base Command
# =============================================================================


class BaseCommand(BaseModel):
    """Base class for all commands with auto-generated id and timestamp."""

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique identifier for this command instance",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this command was created (UTC)",
    )

    model_config = {"frozen": False, "extra": "forbid"}


# =============================================================================
# Agent Control Commands
# =============================================================================


class CancelAgentCommand(BaseCommand):
    """Signals the agent to stop current execution gracefully.

    The agent should finish any in-progress atomic operation, clean up,
    and return control to the user. This is a soft cancellation.
    """

    reason: Optional[str] = Field(
        default=None,
        description="Optional reason for cancellation (for logging/debugging)",
    )


class InterruptShellCommand(BaseCommand):
    """Signals to interrupt a currently running shell command.

    This is equivalent to pressing Ctrl+C in a terminal. The shell process
    should receive SIGINT and terminate. Use this when a command is taking
    too long or producing unwanted output.
    """

    command_id: Optional[str] = Field(
        default=None,
        description="ID of the specific shell command to interrupt (None = current)",
    )


# =============================================================================
# User Interaction Responses
# =============================================================================


class UserInputResponse(BaseCommand):
    """Response to a UserInputRequest from the agent.

    The prompt_id must match the prompt_id from the original UserInputRequest
    so the agent can correlate the response with the request.
    """

    prompt_id: str = Field(
        description="ID of the prompt this responds to (must match request)"
    )
    value: str = Field(description="The user's input value")


class ConfirmationResponse(BaseCommand):
    """Response to a ConfirmationRequest from the agent.

    The user can confirm or deny, and optionally provide feedback text
    if the original request had allow_feedback=True.
    """

    prompt_id: str = Field(
        description="ID of the prompt this responds to (must match request)"
    )
    confirmed: bool = Field(
        description="Whether the user confirmed (True) or denied (False)"
    )
    feedback: Optional[str] = Field(
        default=None,
        description="Optional feedback text from the user",
    )


class SelectionResponse(BaseCommand):
    """Response to a SelectionRequest from the agent.

    Contains both the index and the value for convenience and validation.
    The agent can verify that selected_value matches options[selected_index].
    """

    prompt_id: str = Field(
        description="ID of the prompt this responds to (must match request)"
    )
    selected_index: int = Field(
        ge=0,
        description="Zero-based index of the selected option",
    )
    selected_value: str = Field(description="The value of the selected option")


# =============================================================================
# Union Type for Type Checking
# =============================================================================


# All concrete command types (excludes BaseCommand itself)
AnyCommand = Union[
    CancelAgentCommand,
    InterruptShellCommand,
    UserInputResponse,
    ConfirmationResponse,
    SelectionResponse,
]
"""Union of all command types for type checking."""


# =============================================================================
# Export all public symbols
# =============================================================================

__all__ = [
    # Base
    "BaseCommand",
    # Agent control
    "CancelAgentCommand",
    "InterruptShellCommand",
    # User interaction responses
    "UserInputResponse",
    "ConfirmationResponse",
    "SelectionResponse",
    # Union type
    "AnyCommand",
]
