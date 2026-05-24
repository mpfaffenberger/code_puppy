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
from typing import Literal, Optional, Union
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


class PauseAgentCommand(BaseCommand):
    """Signals the agent to pause at the next safe boundary (between
    streaming events or between turns). The agent stops emitting output,
    the spinner is hidden, and any in-flight streaming chunks are silently
    consumed but not rendered. Use ResumeAgentCommand to continue.
    """

    reason: Optional[str] = Field(
        default=None,
        description="Optional reason for pause (for logging/debugging)",
    )


class ResumeAgentCommand(BaseCommand):
    """Resumes a paused agent. No-op if the agent isn't paused."""

    pass


class SteerAgentCommand(BaseCommand):
    """Queues a steering message to be injected as a user turn.

    The ``mode`` field controls when the model sees it:
      - ``"now"`` (default): injected mid-turn via ``history_processors``
        at the next model call. Interrupts the agent's current train of
        thought ASAP.
      - ``"queue"``: held until current ``agent.run()`` completes, then
        injected as a fresh user turn. Additive — won't interrupt
        in-progress work.
    """

    text: str = Field(
        description="The steering message to inject as a user turn",
    )
    mode: Literal["now", "queue"] = Field(
        default="now",
        description=(
            "When to deliver the steer: 'now' = mid-turn ASAP via "
            "history_processors; 'queue' = after current turn finishes"
        ),
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
    PauseAgentCommand,
    ResumeAgentCommand,
    SteerAgentCommand,
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
    "PauseAgentCommand",
    "ResumeAgentCommand",
    "SteerAgentCommand",
    # User interaction responses
    "UserInputResponse",
    "ConfirmationResponse",
    "SelectionResponse",
    # Union type
    "AnyCommand",
]
