# agent_tools.py
import hashlib
import json
import pickle
import re
from datetime import datetime
from pathlib import Path
from typing import List

from pydantic import BaseModel, ConfigDict

from pydantic_ai import RunContext
from pydantic_ai.messages import ModelMessage

from code_puppy.config import (
    DATA_DIR,
)
from code_puppy.messaging import (
    emit_error,
    emit_info,
    get_message_bus,
    get_session_context,
    set_session_context,
)
from code_puppy.tools.common import atomic_write_text, generate_group_id


def _generate_session_hash_suffix() -> str:
    """Generate a short SHA1 hash suffix based on current timestamp for uniqueness.

    Returns:
        A 6-character hex string, e.g., "a3f2b1"
    """
    timestamp = str(datetime.now().timestamp())
    return hashlib.sha1(timestamp.encode()).hexdigest()[:6]


def _sanitize_for_session_id(value: str) -> str:
    """Coerce an arbitrary string into kebab-case suitable for a session_id.

    Lowercases everything, replaces any non ``[a-z0-9]`` runs with a single
    hyphen, and strips leading/trailing hyphens.  This lets us safely embed
    agent names like ``"LPZ-Main-Coder"`` or ``"My_Agent"`` into auto-
    generated session IDs without tripping the kebab-case validator.
    """
    lowered = value.lower()
    # Replace any run of disallowed chars with a single hyphen
    cleaned = re.sub(r"[^a-z0-9]+", "-", lowered)
    # Strip leading/trailing hyphens
    return cleaned.strip("-")


# Regex pattern for kebab-case session IDs
SESSION_ID_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SESSION_ID_MAX_LENGTH = 128


def _validate_session_id(session_id: str) -> None:
    """Validate that a session ID follows kebab-case naming conventions.

    Args:
        session_id: The session identifier to validate

    Raises:
        ValueError: If the session_id is invalid

    Valid format:
        - Lowercase letters (a-z)
        - Numbers (0-9)
        - Hyphens (-) to separate words
        - No uppercase, no underscores, no special characters
        - Length between 1 and 128 characters

    Examples:
        Valid: "my-session", "agent-session-1", "discussion-about-code"
        Invalid: "MySession", "my_session", "my session", "my--session"
    """
    if not session_id:
        raise ValueError("session_id cannot be empty")

    if len(session_id) > SESSION_ID_MAX_LENGTH:
        raise ValueError(
            f"Invalid session_id '{session_id}': must be {SESSION_ID_MAX_LENGTH} characters or less"
        )

    if not SESSION_ID_PATTERN.match(session_id):
        raise ValueError(
            f"Invalid session_id '{session_id}': must be kebab-case "
            "(lowercase letters, numbers, and hyphens only). "
            "Examples: 'my-session', 'agent-session-1', 'discussion-about-code'"
        )


def _get_subagent_sessions_dir() -> Path:
    """Get the directory for storing subagent session data.

    Returns:
        Path to XDG data directory/subagent_sessions/
    """
    sessions_dir = Path(DATA_DIR) / "subagent_sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    return sessions_dir


def _save_session_history(
    session_id: str,
    message_history: List[ModelMessage],
    agent_name: str,
    initial_prompt: str | None = None,
) -> None:
    """Save session history to filesystem.

    Args:
        session_id: The session identifier (must be kebab-case)
        message_history: List of messages to save
        agent_name: Name of the agent being invoked
        initial_prompt: The first prompt that started this session (for .txt metadata)

    Raises:
        ValueError: If session_id is not valid kebab-case format
    """
    # Validate session_id format before saving
    _validate_session_id(session_id)

    sessions_dir = _get_subagent_sessions_dir()

    # Save pickle file with message history (atomic: write a temp file then
    # replace, so a crash mid-write can't corrupt an existing session pickle)
    pkl_path = sessions_dir / f"{session_id}.pkl"
    tmp_pkl = pkl_path.with_suffix(".tmp")
    with open(tmp_pkl, "wb") as f:
        pickle.dump(message_history, f)
    tmp_pkl.replace(pkl_path)

    # Save or update txt file with metadata
    txt_path = sessions_dir / f"{session_id}.txt"
    if not txt_path.exists() and initial_prompt:
        # Only write initial metadata on first save
        metadata = {
            "session_id": session_id,
            "agent_name": agent_name,
            "initial_prompt": initial_prompt,
            "created_at": datetime.now().isoformat(),
            "message_count": len(message_history),
        }
        atomic_write_text(str(txt_path), json.dumps(metadata, indent=2))
    elif txt_path.exists():
        # Update message count on subsequent saves
        try:
            with open(txt_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            metadata["message_count"] = len(message_history)
            metadata["last_updated"] = datetime.now().isoformat()
            atomic_write_text(str(txt_path), json.dumps(metadata, indent=2))
        except Exception:
            pass  # If we can't update metadata, no big deal


def _load_session_history(session_id: str) -> List[ModelMessage]:
    """Load session history from filesystem.

    Args:
        session_id: The session identifier (must be kebab-case)

    Returns:
        List of ModelMessage objects, or empty list if session doesn't exist

    Raises:
        ValueError: If session_id is not valid kebab-case format
    """
    # Validate session_id format before loading
    _validate_session_id(session_id)

    sessions_dir = _get_subagent_sessions_dir()
    pkl_path = sessions_dir / f"{session_id}.pkl"

    if not pkl_path.exists():
        return []

    try:
        with open(pkl_path, "rb") as f:
            return pickle.load(f)
    except Exception:
        # If pickle is corrupted or incompatible, return empty history
        return []


class AgentInfo(BaseModel):
    """Information about an available agent."""

    name: str
    display_name: str
    description: str


class ListAgentsOutput(BaseModel):
    """Output for the list_agents tool."""

    agents: List[AgentInfo]
    error: str | None = None


class AgentInvokeOutput(BaseModel):
    """Output for the invoke_agent tool."""

    response: str | None
    agent_name: str
    session_id: str | None = None
    model_name: str | None = None
    error: str | None = None


class SubagentRequestUsage(BaseModel):
    """Token usage for ONE model call within a run.

    Providers decide pricing per request, not per run: several models charge a
    higher rate once a single call's context crosses a length threshold, and a
    run may switch models partway through. Summing calls therefore destroys the
    information cost depends on -- upstream says as much on
    ``RequestUsage.__add__``: "this CANNOT be used to sum multiple requests
    without breaking some pricing calculations."

    Each entry keeps one call's buckets intact alongside the model that served
    it, so callers can apply the correct price sheet and context tier per call.
    Buckets follow the same rules as the aggregate fields: non-overlapping, and
    ``None`` whenever the provider did not report them unambiguously.

    ``num_requests`` is deliberately absent -- it is always 1 here. The model
    forbids extra fields so that feeding it run-level metrics (which carry
    ``num_requests``) fails loudly instead of silently dropping the key.
    """

    model_config = ConfigDict(extra="forbid")

    model_name: str | None = None
    input_tokens: int | None = None
    cache_read_input_tokens: int | None = None
    cache_creation_input_tokens: int | None = None
    output_tokens: int | None = None


class AgentInvokeWithModelOutput(AgentInvokeOutput):
    """Output for the invoke_agent_with_model tool.

    Extends :class:`AgentInvokeOutput` with per-run token-usage and timing
    fields, populated on the success path only, so benchmarking/
    model-comparison callers that explicitly pin a model can measure per-run
    cost without reconstructing it from downstream telemetry. These fields are
    scoped to THIS tool only -- ``invoke_agent`` keeps the original five-field
    contract untouched, with no functional or schema changes.

    Token accounting is normalized so the buckets never overlap and map 1:1
    onto the dimensions providers actually bill for: ``input_tokens`` counts
    only regular (non-cached) input, cached input is split into
    ``cache_read_input_tokens`` (cache hits) and ``cache_creation_input_tokens``
    (cache writes), and ``output_tokens`` covers generated tokens. Those four
    are priced at different per-token rates, so they are reported separately
    rather than aggregated -- no single blended total would be meaningful.

    Each bucket is surfaced only when the provider reports it unambiguously,
    and each decides that independently, so an unavailable bucket stays ``None``
    rather than being estimated or defaulted to ``0``. Buckets a provider has no
    concept of also stay ``None``: only Anthropic bills cache writes, so
    ``cache_creation_input_tokens`` is ``None`` for OpenAI and Gemini runs.

    The root token fields are run-level TOTALS: convenient for coarse telemetry,
    but NOT sufficient to compute cost. Pricing is decided per request, so a run
    that crossed a context-length threshold on one call -- or switched models
    partway through -- cannot be priced from the totals alone. Use
    ``per_request_usage`` for exact cost; it preserves each call's buckets and
    the model that served it.

    ``final_context_tokens`` answers a different question: not what the run
    cost, but how much context was live when it ended. It counts the last
    call's raw combined input (cached tokens included -- they occupy the
    window regardless of how they are billed) plus that call's output. The
    root totals cannot answer this: they sum every request, so a four-call run
    reports several times the context that was ever live at once.
    """

    input_tokens: int | None = None
    cache_read_input_tokens: int | None = None
    cache_creation_input_tokens: int | None = None
    output_tokens: int | None = None
    num_requests: int | None = None
    per_request_usage: list[SubagentRequestUsage] | None = None
    final_context_tokens: int | None = None
    start_time: str | None = None
    end_time: str | None = None
    duration_ms: float | None = None


def register_list_agents(agent):
    """Register the list_agents tool with the provided agent.

    Args:
        agent: The agent to register the tool with
    """

    @agent.tool
    def list_agents(context: RunContext) -> ListAgentsOutput:
        """List all available sub-agents that can be invoked."""
        # Generate a group ID for this tool execution
        group_id = generate_group_id("list_agents")

        from rich.text import Text

        from code_puppy.config import get_banner_color

        list_agents_color = get_banner_color("list_agents")

        try:
            from code_puppy.agents import get_agent_descriptions, get_available_agents

            # Get available agents and their descriptions from the agent manager
            agents_dict = get_available_agents()
            descriptions_dict = get_agent_descriptions()

            # Convert to list of AgentInfo objects
            agents = [
                AgentInfo(
                    name=name,
                    display_name=display_name,
                    description=descriptions_dict.get(name, "No description available"),
                )
                for name, display_name in agents_dict.items()
            ]

            # Quiet output - banner and count on same line
            agent_count = len(agents)
            emit_info(
                Text.from_markup(
                    f"\n[bold white on {list_agents_color}] LIST AGENTS [/bold white on {list_agents_color}] "
                    f"[dim]Found {agent_count} agent(s).[/dim]"
                ),
                message_group=group_id,
            )

            return ListAgentsOutput(agents=agents)

        except Exception as e:
            error_msg = f"Error listing agents: {str(e)}"
            emit_error(error_msg, message_group=group_id)
            return ListAgentsOutput(agents=[], error=error_msg)

    return list_agents


# Backward-compatible re-exports: invocation tools live in subagent_invocation
# so this file stays below the bloat line.
from code_puppy.tools.subagent_invocation import (  # noqa: E402
    _active_subagent_tasks,
    register_invoke_agent,
    register_invoke_agent_with_model,
)

__all__ = [
    "AgentInfo",
    "AgentInvokeOutput",
    "AgentInvokeWithModelOutput",
    "ListAgentsOutput",
    "SubagentRequestUsage",
    "_active_subagent_tasks",
    "_generate_session_hash_suffix",
    "_get_subagent_sessions_dir",
    "_load_session_history",
    "get_message_bus",
    "get_session_context",
    "_sanitize_for_session_id",
    "_save_session_history",
    "_validate_session_id",
    "register_invoke_agent",
    "register_invoke_agent_with_model",
    "register_list_agents",
    "set_session_context",
]
