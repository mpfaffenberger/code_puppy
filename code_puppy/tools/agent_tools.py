# agent_tools.py
import asyncio
import hashlib
import itertools
import json
import pickle
import re
import traceback
from datetime import datetime
from pathlib import Path
from typing import List, Set

from dbos import DBOS, SetWorkflowID
from pydantic import BaseModel

# Import Agent from pydantic_ai to create temporary agents for invocation
from pydantic_ai import Agent, RunContext, UsageLimits
from pydantic_ai.messages import ModelMessage

from code_puppy.config import (
    DATA_DIR,
    get_message_limit,
    get_use_dbos,
)
from code_puppy.messaging import (
    SubAgentInvocationMessage,
    SubAgentResponseMessage,
    emit_error,
    emit_info,
    get_message_bus,
    get_session_context,
    set_session_context,
)
from code_puppy.model_factory import ModelFactory, make_model_settings
from code_puppy.tools.common import generate_group_id

# Set to track active subagent invocation tasks
_active_subagent_tasks: Set[asyncio.Task] = set()

# Atomic counter for DBOS workflow IDs - ensures uniqueness even in rapid back-to-back calls
# itertools.count() is thread-safe for next() calls
_dbos_workflow_counter = itertools.count()


def _generate_dbos_workflow_id(base_id: str) -> str:
    """Generate a unique DBOS workflow ID by appending an atomic counter.

    DBOS requires workflow IDs to be unique across all executions.
    This function ensures uniqueness by combining the base_id with
    an atomically incrementing counter.

    Args:
        base_id: The base identifier (e.g., group_id from generate_group_id)

    Returns:
        A unique workflow ID in format: {base_id}-wf-{counter}
    """
    counter = next(_dbos_workflow_counter)
    return f"{base_id}-wf-{counter}"


def _generate_session_hash_suffix() -> str:
    """Generate a short SHA1 hash suffix based on current timestamp for uniqueness.

    Returns:
        A 6-character hex string, e.g., "a3f2b1"
    """
    timestamp = str(datetime.now().timestamp())
    return hashlib.sha1(timestamp.encode()).hexdigest()[:6]


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

    # Save pickle file with message history
    pkl_path = sessions_dir / f"{session_id}.pkl"
    with open(pkl_path, "wb") as f:
        pickle.dump(message_history, f)

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
        with open(txt_path, "w") as f:
            json.dump(metadata, f, indent=2)
    elif txt_path.exists():
        # Update message count on subsequent saves
        try:
            with open(txt_path, "r") as f:
                metadata = json.load(f)
            metadata["message_count"] = len(message_history)
            metadata["last_updated"] = datetime.now().isoformat()
            with open(txt_path, "w") as f:
                json.dump(metadata, f, indent=2)
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
    error: str | None = None


def register_list_agents(agent):
    """Register the list_agents tool with the provided agent.

    Args:
        agent: The agent to register the tool with
    """

    @agent.tool
    def list_agents(context: RunContext) -> ListAgentsOutput:
        """List all available sub-agents that can be invoked.

        Returns:
            ListAgentsOutput: A list of available agents with their names and display names.
        """
        # Generate a group ID for this tool execution
        group_id = generate_group_id("list_agents")

        from rich.text import Text

        from code_puppy.config import get_banner_color

        list_agents_color = get_banner_color("list_agents")
        emit_info(
            Text.from_markup(
                f"\n[bold white on {list_agents_color}] LIST AGENTS [/bold white on {list_agents_color}]"
            ),
            message_group=group_id,
        )

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

            # Accumulate output into a single string and emit once
            # Use Text.from_markup() to pass a Rich object that won't be escaped
            lines = []
            for agent_item in agents:
                lines.append(
                    f"- [bold]{agent_item.name}[/bold]: {agent_item.display_name}\n"
                    f"  [dim]{agent_item.description}[/dim]"
                )
            emit_info(Text.from_markup("\n".join(lines)), message_group=group_id)

            return ListAgentsOutput(agents=agents)

        except Exception as e:
            error_msg = f"Error listing agents: {str(e)}"
            emit_error(error_msg, message_group=group_id)
            return ListAgentsOutput(agents=[], error=error_msg)

    return list_agents


def register_invoke_agent(agent):
    """Register the invoke_agent tool with the provided agent.

    Args:
        agent: The agent to register the tool with
    """

    @agent.tool
    async def invoke_agent(
        context: RunContext, agent_name: str, prompt: str, session_id: str | None = None
    ) -> AgentInvokeOutput:
        """Invoke a specific sub-agent with a given prompt.

        Args:
            agent_name: The name of the agent to invoke
            prompt: The prompt to send to the agent
            session_id: Optional session ID for maintaining conversation memory across invocations.

                       **Session ID Format:**
                       - Must be kebab-case (lowercase letters, numbers, hyphens only)
                       - Should be human-readable: e.g., "implement-oauth", "review-auth"
                       - For NEW sessions, a SHA1 hash suffix is automatically appended for uniqueness
                       - To CONTINUE a session, use the full session_id (with hash) from the previous invocation
                       - If None (default), auto-generates like "agent-name-session-1"

                       **When to use session_id:**
                       - **NEW SESSION**: Provide a base name like "review-auth" - we'll append a unique hash
                       - **CONTINUE SESSION**: Use the full session_id from output (e.g., "review-auth-a3f2b1")
                       - **ONE-OFF TASKS**: Leave as None (auto-generate)

                       **Most common pattern:** Leave session_id as None (auto-generate) unless you
                       specifically need conversational memory.

        Returns:
            AgentInvokeOutput: Contains:
                - response (str | None): The agent's response to the prompt
                - agent_name (str): Name of the invoked agent
                - session_id (str | None): The full session ID (with hash suffix) - USE THIS to continue the conversation!
                - error (str | None): Error message if invocation failed

        Examples:
            # COMMON CASE: One-off invocation, no memory needed (auto-generate session)
            result = invoke_agent(
                "qa-expert",
                "Review this function: def add(a, b): return a + b"
            )
            # result.session_id will be something like "qa-expert-session-a3f2b1"

            # MULTI-TURN: Start a NEW conversation with a base session ID
            # A hash suffix is auto-appended: "review-add-function" -> "review-add-function-a3f2b1"
            result1 = invoke_agent(
                "qa-expert",
                "Review this function: def add(a, b): return a + b",
                session_id="review-add-function"
            )
            # result1.session_id contains the full ID like "review-add-function-a3f2b1"

            # Continue the SAME conversation using session_id from the previous result
            result2 = invoke_agent(
                "qa-expert",
                "Can you suggest edge cases for that function?",
                session_id=result1.session_id  # Use the session_id from previous output!
            )

            # Multiple INDEPENDENT reviews (each gets unique hash suffix)
            auth_review = invoke_agent(
                "code-reviewer",
                "Review my authentication code",
                session_id="auth-review"  # -> "auth-review-<hash1>"
            )
            # auth_review.session_id contains the full ID to continue this review

            payment_review = invoke_agent(
                "code-reviewer",
                "Review my payment processing code",
                session_id="payment-review"  # -> "payment-review-<hash2>"
            )
            # payment_review.session_id contains a different full ID
        """
        from code_puppy.agents.agent_manager import load_agent

        # Validate user-provided session_id if given
        if session_id is not None:
            try:
                _validate_session_id(session_id)
            except ValueError as e:
                # Return error immediately if session_id is invalid
                group_id = generate_group_id("invoke_agent", agent_name)
                emit_error(str(e), message_group=group_id)
                return AgentInvokeOutput(
                    response=None, agent_name=agent_name, error=str(e)
                )

        # Generate a group ID for this tool execution
        group_id = generate_group_id("invoke_agent", agent_name)

        # Check if this is an existing session or a new one
        # For user-provided session_id, check if it exists
        # For None, we'll generate a new one below
        if session_id is not None:
            message_history = _load_session_history(session_id)
            is_new_session = len(message_history) == 0
        else:
            message_history = []
            is_new_session = True

        # Generate or finalize session_id
        if session_id is None:
            # Auto-generate a session ID with hash suffix for uniqueness
            # Example: "qa-expert-session-a3f2b1"
            hash_suffix = _generate_session_hash_suffix()
            session_id = f"{agent_name}-session-{hash_suffix}"
        elif is_new_session:
            # User provided a base name for a NEW session - append hash suffix
            # Example: "review-auth" -> "review-auth-a3f2b1"
            hash_suffix = _generate_session_hash_suffix()
            session_id = f"{session_id}-{hash_suffix}"
        # else: continuing existing session, use session_id as-is

        # Emit structured invocation message via MessageBus
        bus = get_message_bus()
        bus.emit(
            SubAgentInvocationMessage(
                agent_name=agent_name,
                session_id=session_id,
                prompt=prompt,
                is_new_session=is_new_session,
                message_count=len(message_history),
            )
        )

        # Save current session context and set the new one for this sub-agent
        previous_session_id = get_session_context()
        set_session_context(session_id)

        try:
            # Load the specified agent config
            agent_config = load_agent(agent_name)

            # Get the current model for creating a temporary agent
            model_name = agent_config.get_model_name()
            models_config = ModelFactory.load_config()

            # Only proceed if we have a valid model configuration
            if model_name not in models_config:
                raise ValueError(f"Model '{model_name}' not found in configuration")

            model = ModelFactory.get_model(model_name, models_config)

            # Create a temporary agent instance to avoid interfering with current agent state
            instructions = agent_config.get_system_prompt()

            # Add AGENTS.md content to subagents
            puppy_rules = agent_config.load_puppy_rules()
            if puppy_rules:
                instructions += f"\n\n{puppy_rules}"

            # Apply prompt additions (like file permission handling) to temporary agents
            from code_puppy import callbacks
            from code_puppy.model_utils import prepare_prompt_for_model

            prompt_additions = callbacks.on_load_prompt()
            if len(prompt_additions):
                instructions += "\n" + "\n".join(prompt_additions)

            # Handle claude-code models: swap instructions, and prepend system prompt only on first message
            prepared = prepare_prompt_for_model(
                model_name,
                instructions,
                prompt,
                prepend_system_to_user=is_new_session,  # Only prepend on first message
            )
            instructions = prepared.instructions
            prompt = prepared.user_prompt

            subagent_name = f"temp-invoke-agent-{session_id}"
            model_settings = make_model_settings(model_name)

            temp_agent = Agent(
                model=model,
                instructions=instructions,
                output_type=str,
                retries=3,
                history_processors=[agent_config.message_history_accumulator],
                model_settings=model_settings,
            )

            # Register the tools that the agent needs
            from code_puppy.tools import register_tools_for_agent

            agent_tools = agent_config.get_available_tools()
            register_tools_for_agent(temp_agent, agent_tools)

            if get_use_dbos():
                from pydantic_ai.durable_exec.dbos import DBOSAgent

                dbos_agent = DBOSAgent(temp_agent, name=subagent_name)
                temp_agent = dbos_agent

            # Run the temporary agent with the provided prompt as an asyncio task
            # Pass the message_history from the session to continue the conversation
            workflow_id = None  # Track for potential cancellation
            if get_use_dbos():
                # Generate a unique workflow ID for DBOS - ensures no collisions in back-to-back calls
                workflow_id = _generate_dbos_workflow_id(group_id)
                with SetWorkflowID(workflow_id):
                    task = asyncio.create_task(
                        temp_agent.run(
                            prompt,
                            message_history=message_history,
                            usage_limits=UsageLimits(request_limit=get_message_limit()),
                        )
                    )
                    _active_subagent_tasks.add(task)
            else:
                task = asyncio.create_task(
                    temp_agent.run(
                        prompt,
                        message_history=message_history,
                        usage_limits=UsageLimits(request_limit=get_message_limit()),
                    )
                )
                _active_subagent_tasks.add(task)

            try:
                result = await task
            finally:
                _active_subagent_tasks.discard(task)
                if task.cancelled():
                    if get_use_dbos() and workflow_id:
                        DBOS.cancel_workflow(workflow_id)

            # Extract the response from the result
            response = result.output

            # Update the session history with the new messages from this interaction
            # The result contains all_messages which includes the full conversation
            updated_history = result.all_messages()

            # Save to filesystem (include initial prompt only for new sessions)
            _save_session_history(
                session_id=session_id,
                message_history=updated_history,
                agent_name=agent_name,
                initial_prompt=prompt if is_new_session else None,
            )

            # Emit structured response message via MessageBus
            bus.emit(
                SubAgentResponseMessage(
                    agent_name=agent_name,
                    session_id=session_id,
                    response=response,
                    message_count=len(updated_history),
                )
            )

            return AgentInvokeOutput(
                response=response, agent_name=agent_name, session_id=session_id
            )

        except Exception:
            error_msg = f"Error invoking agent '{agent_name}': {traceback.format_exc()}"
            emit_error(error_msg, message_group=group_id)
            return AgentInvokeOutput(
                response=None,
                agent_name=agent_name,
                session_id=session_id,
                error=error_msg,
            )

        finally:
            # Restore the previous session context
            set_session_context(previous_session_id)

    return invoke_agent
