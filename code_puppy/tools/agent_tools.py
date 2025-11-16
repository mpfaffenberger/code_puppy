# agent_tools.py
import asyncio
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

from code_puppy.config import get_message_limit, get_use_dbos
from code_puppy.messaging import (
    emit_divider,
    emit_error,
    emit_info,
    emit_system_message,
)
from code_puppy.model_factory import ModelFactory
from code_puppy.tools.common import generate_group_id

_temp_agent_count = 0
# Set to track active subagent invocation tasks
_active_subagent_tasks: Set[asyncio.Task] = set()

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
        Path to ~/.code_puppy/subagent_sessions/
    """
    sessions_dir = Path.home() / ".code_puppy" / "subagent_sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
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


class ListAgentsOutput(BaseModel):
    """Output for the list_agents tool."""

    agents: List[AgentInfo]
    error: str | None = None


class AgentInvokeOutput(BaseModel):
    """Output for the invoke_agent tool."""

    response: str | None
    agent_name: str
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

        emit_info(
            "\n[bold white on blue] LIST AGENTS [/bold white on blue]",
            message_group=group_id,
        )
        emit_divider(message_group=group_id)

        try:
            from code_puppy.agents import get_available_agents

            # Get available agents from the agent manager
            agents_dict = get_available_agents()

            # Convert to list of AgentInfo objects
            agents = [
                AgentInfo(name=name, display_name=display_name)
                for name, display_name in agents_dict.items()
            ]

            # Display the agents in the console
            for agent_item in agents:
                emit_system_message(
                    f"- [bold]{agent_item.name}[/bold]: {agent_item.display_name}",
                    message_group=group_id,
                )

            emit_divider(message_group=group_id)
            return ListAgentsOutput(agents=agents)

        except Exception as e:
            error_msg = f"Error listing agents: {str(e)}"
            emit_error(error_msg, message_group=group_id)
            emit_divider(message_group=group_id)
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
                       - Should be human-readable with random suffix: e.g., "implement-oauth-abc123", "review-auth-x7k9"
                       - Add 3-6 random characters/numbers at the end to prevent namespace collisions
                       - If None (default), auto-generates like "agent-name-session-1"

                       **When to use session_id:**
                       - **REUSE** the same session_id ONLY when you need the sub-agent to remember
                         previous conversation context (e.g., multi-turn discussions, iterative reviews)
                       - **DO NOT REUSE** for independent, one-off tasks - let it auto-generate or use
                         unique IDs for each invocation

                       **Most common pattern:** Leave session_id as None (auto-generate) unless you
                       specifically need conversational memory.

        Returns:
            AgentInvokeOutput: The agent's response to the prompt

        Examples:
            # COMMON CASE: One-off invocation, no memory needed (auto-generate session)
            result = invoke_agent(
                "qa-expert",
                "Review this function: def add(a, b): return a + b"
            )

            # MULTI-TURN: Start a conversation with explicit session ID (note random suffix)
            result1 = invoke_agent(
                "qa-expert",
                "Review this function: def add(a, b): return a + b",
                session_id="review-add-function-x7k9"  # Random suffix prevents collisions
            )

            # Continue the SAME conversation (reuse session_id to maintain memory)
            result2 = invoke_agent(
                "qa-expert",
                "Can you suggest edge cases for that function?",
                session_id="review-add-function-x7k9"  # SAME session_id = conversation memory
            )

            # Multiple INDEPENDENT reviews (unique session IDs with random suffixes)
            auth_review = invoke_agent(
                "code-reviewer",
                "Review my authentication code",
                session_id="auth-review-abc123"  # Random suffix for uniqueness
            )

            payment_review = invoke_agent(
                "code-reviewer",
                "Review my payment processing code",
                session_id="payment-review-def456"  # Different session = no shared context
            )
        """
        global _temp_agent_count

        from code_puppy.agents.agent_manager import load_agent

        # Generate or use provided session_id (kebab-case format)
        if session_id is None:
            # Create a new session ID in kebab-case format
            # Example: "qa-expert-session-1", "code-reviewer-session-2"
            _temp_agent_count += 1
            session_id = f"{agent_name}-session-{_temp_agent_count}"
        else:
            # Validate user-provided session_id
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

        emit_info(
            f"\n[bold white on blue] INVOKE AGENT [/bold white on blue] {agent_name} (session: {session_id})",
            message_group=group_id,
        )
        emit_divider(message_group=group_id)
        emit_system_message(f"Prompt: {prompt}", message_group=group_id)

        # Retrieve existing message history from filesystem for this session, if any
        message_history = _load_session_history(session_id)
        is_new_session = len(message_history) == 0

        if message_history:
            emit_system_message(
                f"Continuing conversation from session {session_id} ({len(message_history)} messages)",
                message_group=group_id,
            )
        else:
            emit_system_message(
                f"Starting new session {session_id}",
                message_group=group_id,
            )
        emit_divider(message_group=group_id)

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

            # Apply prompt additions (like file permission handling) to temporary agents
            from code_puppy import callbacks

            prompt_additions = callbacks.on_load_prompt()
            if len(prompt_additions):
                instructions += "\n" + "\n".join(prompt_additions)
            if model_name.startswith("claude-code"):
                prompt = instructions + "\n\n" + prompt
                instructions = (
                    "You are Claude Code, Anthropic's official CLI for Claude."
                )

            subagent_name = f"temp-invoke-agent-{_temp_agent_count}"
            temp_agent = Agent(
                model=model,
                instructions=instructions,
                output_type=str,
                retries=3,
                history_processors=[agent_config.message_history_accumulator],
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
            if get_use_dbos():
                with SetWorkflowID(group_id):
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
                    if get_use_dbos():
                        DBOS.cancel_workflow(group_id)

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

            emit_system_message(f"Response: {response}", message_group=group_id)
            emit_system_message(
                f"Session {session_id} saved to disk ({len(updated_history)} messages)",
                message_group=group_id,
            )
            emit_divider(message_group=group_id)

            return AgentInvokeOutput(response=response, agent_name=agent_name)

        except Exception:
            error_msg = f"Error invoking agent '{agent_name}': {traceback.format_exc()}"
            emit_error(error_msg, message_group=group_id)
            emit_divider(message_group=group_id)
            return AgentInvokeOutput(
                response=None, agent_name=agent_name, error=error_msg
            )

    return invoke_agent
