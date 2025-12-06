"""Bridge between Code Puppy agents and ACP protocol.

This module adapts the existing BaseAgent/pydantic-ai infrastructure
to work with the ACP protocol, translating between:
- ACP prompts -> Agent runs
- Agent stream events -> ACP session/update notifications
- Agent tool calls -> ACP tool_call notifications + client method calls
"""

import sys
import uuid
from typing import Any, Dict, List

from code_puppy.acp.client_proxy import ClientProxy
from code_puppy.acp.notifications import NotificationSender
from code_puppy.acp.state import ACPSession

# Map Code Puppy tool names to ACP tool kinds
TOOL_KIND_MAP = {
    "read_file": "read",
    "list_files": "read",
    "grep": "search",
    "edit_file": "edit",
    "delete_file": "delete",
    "agent_run_shell_command": "execute",
    "agent_share_your_reasoning": "think",
    "invoke_agent": "other",
    "list_agents": "other",
}


def get_tool_kind(tool_name: str) -> str:
    """Map a tool name to an ACP tool kind.

    Args:
        tool_name: Name of the Code Puppy tool

    Returns:
        ACP tool kind (read, edit, execute, search, think, other)
    """
    return TOOL_KIND_MAP.get(tool_name, "other")


def generate_tool_call_id() -> str:
    """Generate a unique tool call ID."""
    return str(uuid.uuid4())


class ACPAgentBridge:
    """Bridges Code Puppy agents to ACP protocol.

    This class handles:
    - Running prompts through the agent
    - Converting stream events to ACP notifications
    - Adapting tool calls to use client capabilities

    Attributes:
        session: The ACP session
        client: Proxy for calling client methods
        notifier: Helper for sending notifications
    """

    def __init__(
        self,
        session: ACPSession,
        client_proxy: ClientProxy,
        notification_sender: NotificationSender,
    ):
        """Initialize the bridge.

        Args:
            session: ACP session to work with
            client_proxy: Proxy for client method calls
            notification_sender: Helper for sending notifications
        """
        self.session = session
        self.client = client_proxy
        self.notifier = notification_sender
        self._agent = None
        self._cancelled = False

    def get_agent(self):
        """Get or create the agent for this session.

        Returns:
            The BaseAgent instance for this session
        """
        if self._agent is None:
            # Import here to avoid circular imports
            from code_puppy.agents import get_current_agent
            from code_puppy.agents.agent_manager import load_agent

            # Try to load the specified agent, fall back to current
            try:
                self._agent = load_agent(self.session.agent_name)
            except (ValueError, Exception):
                self._agent = get_current_agent()
        return self._agent

    def cancel(self) -> None:
        """Request cancellation of current operation."""
        self._cancelled = True
        print(
            f"[ACP] Cancellation requested for session {self.session.session_id}",
            file=sys.stderr,
        )

    async def send_available_commands(self) -> None:
        """Send the list of available slash commands."""
        commands = [
            {
                "name": "agent",
                "description": "Switch to a different agent",
                "input": {"hint": "agent name (e.g., code-puppy, planning-agent)"},
            },
            {
                "name": "model",
                "description": "Switch to a different model",
                "input": {
                    "hint": "model name (e.g., claude-sonnet-4-20250514, gpt-4o)"
                },
            },
            {
                "name": "clear",
                "description": "Clear conversation history",
            },
            {
                "name": "help",
                "description": "Show available commands and agents",
            },
            {
                "name": "agents",
                "description": "List all available agents",
            },
        ]
        await self.notifier.available_commands(commands)

    async def process_prompt(
        self,
        prompt_content: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Process a prompt and return when complete.

        Args:
            prompt_content: List of content blocks from session/prompt

        Returns:
            Dict with stopReason (end_turn, cancelled, error)
        """
        self._cancelled = False

        # Extract text from prompt content
        prompt_text = self._extract_prompt_text(prompt_content)

        if not prompt_text.strip():
            await self.notifier.agent_message_chunk(
                "I didn't receive any text. Please provide a prompt."
            )
            return {"stopReason": "end_turn"}

        # Check for slash commands
        if prompt_text.strip().startswith("/"):
            return await self._handle_slash_command(prompt_text.strip())

        # Run the agent
        return await self._run_agent(prompt_text, prompt_content)

    async def _run_agent(
        self,
        prompt_text: str,
        prompt_content: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Run the agent with the given prompt.

        Args:
            prompt_text: Extracted text prompt
            prompt_content: Original content blocks (may include resources)

        Returns:
            Dict with stopReason
        """
        import asyncio

        agent = self.get_agent()

        try:
            # Show which agent is processing
            await self.notifier.agent_message_chunk(
                f"*Processing with {agent.display_name}...*\n\n"
            )

            # Run the agent
            # TODO: In Phase 3, we'll adapt tools to use ClientProxy
            # For now, we run the agent normally but capture the output
            result = await agent.run(prompt_text)

            if result is not None:
                # Stream the response
                agent_response = result.output
                await self.notifier.agent_message_chunk(agent_response)

                # Update session message history
                if hasattr(result, "all_messages"):
                    self.session.message_history = list(result.all_messages())

            return {"stopReason": "end_turn"}

        except asyncio.CancelledError:
            print("[ACP] Agent run cancelled", file=sys.stderr)
            return {"stopReason": "cancelled"}

        except Exception as e:
            print(f"[ACP] Agent error: {e}", file=sys.stderr)
            import traceback

            traceback.print_exc(file=sys.stderr)
            await self.notifier.agent_message_chunk(f"\n\n❌ Error: {e}")
            return {"stopReason": "error"}

    def _extract_prompt_text(self, content: List[Dict[str, Any]]) -> str:
        """Extract text from prompt content blocks.

        Args:
            content: List of content blocks

        Returns:
            Extracted text with embedded resources
        """
        texts = []
        for block in content:
            block_type = block.get("type")

            if block_type == "text":
                texts.append(block.get("text", ""))

            elif block_type == "resource":
                # Include embedded resource context
                resource = block.get("resource", {})
                uri = resource.get("uri", "unknown")
                text = resource.get("text", "")
                texts.append(f"\n[File: {uri}]\n```\n{text}\n```\n")

            elif block_type == "image":
                # Note image presence but can't process yet
                texts.append(
                    "\n[Image attached - image processing not yet supported]\n"
                )

        return "\n".join(texts)

    # =========================================================================
    # Slash Command Handling
    # =========================================================================

    async def _handle_slash_command(self, command_text: str) -> Dict[str, Any]:
        """Handle a slash command.

        Args:
            command_text: Full command string starting with /

        Returns:
            Dict with stopReason
        """
        parts = command_text[1:].split(maxsplit=1)
        command = parts[0].lower() if parts else ""
        args = parts[1] if len(parts) > 1 else ""

        if command == "help":
            await self._send_help()
        elif command == "agent":
            await self._switch_agent(args)
        elif command == "agents":
            await self._list_agents()
        elif command == "model":
            await self._switch_model(args)
        elif command == "clear":
            await self._clear_history()
        else:
            await self.notifier.agent_message_chunk(
                f"Unknown command: /{command}\n\nUse `/help` to see available commands."
            )

        return {"stopReason": "end_turn"}

    async def _send_help(self) -> None:
        """Send help information."""
        agent = self.get_agent()

        help_text = f"""# Code Puppy ACP Help 🐶

## Available Commands
- `/agent <name>` - Switch to a different agent
- `/agents` - List all available agents
- `/model <name>` - Switch to a different model
- `/clear` - Clear conversation history
- `/help` - Show this help

## Current Session
- **Agent**: {agent.display_name}
- **Working Directory**: {self.session.cwd}
- **Session ID**: {self.session.session_id}

## Tips
- Use `@file.py` to attach files to your prompt
- The agent can read, write, and execute code
- Ask me to explain, refactor, or debug code!
"""
        await self.notifier.agent_message_chunk(help_text)

    async def _list_agents(self) -> None:
        """List all available agents."""
        from code_puppy.agents.agent_manager import get_available_agents

        # get_available_agents returns Dict[name, display_name]
        agents = get_available_agents()

        lines = ["# Available Agents\n"]
        for name, display_name in agents.items():
            lines.append(f"- **{name}**: {display_name}")

        lines.append(f"\n*Current agent: {self.session.agent_name}*")
        await self.notifier.agent_message_chunk("\n".join(lines))

    async def _switch_agent(self, agent_name: str) -> None:
        """Switch to a different agent.

        Args:
            agent_name: Name of the agent to switch to
        """
        if not agent_name:
            await self.notifier.agent_message_chunk(
                "Usage: `/agent <agent_name>`\n\nUse `/agents` to see available agents."
            )
            return

        from code_puppy.agents.agent_manager import load_agent

        agent_name = agent_name.strip().lower()
        try:
            new_agent = load_agent(agent_name)
        except (ValueError, Exception) as e:
            await self.notifier.agent_message_chunk(
                f"❌ Agent not found: `{agent_name}`\n\n"
                f"Error: {e}\n\n"
                "Use `/agents` to see available agents."
            )
            return

        self.session.agent_name = agent_name
        self._agent = new_agent
        await self.notifier.agent_message_chunk(
            f"✅ Switched to **{new_agent.display_name}**"
        )

    async def _switch_model(self, model_name: str) -> None:
        """Switch to a different model.

        Args:
            model_name: Name of the model to switch to
        """
        if not model_name:
            await self.notifier.agent_message_chunk(
                "Usage: `/model <model_name>`\n\n"
                "Example: `/model claude-sonnet-4-20250514`"
            )
            return

        model_name = model_name.strip()

        try:
            from code_puppy.config import set_model_name

            set_model_name(model_name)

            # Refresh the agent to use the new model
            self._agent = None

            await self.notifier.agent_message_chunk(
                f"✅ Switched to model: `{model_name}`"
            )
        except Exception as e:
            await self.notifier.agent_message_chunk(f"❌ Failed to switch model: {e}")

    async def _clear_history(self) -> None:
        """Clear conversation history."""
        self.session.message_history.clear()
        if self._agent:
            self._agent.clear_message_history()
        await self.notifier.agent_message_chunk("✅ Conversation history cleared.")
