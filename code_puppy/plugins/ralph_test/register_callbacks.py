"""Register callbacks for the Ralph test plugin.

This plugin demonstrates and tests the new callback hooks:
- register_tools: Register custom tools
- register_agents: Register custom agents
- agent_response_complete: Hook into agent completion
"""

import logging
from typing import Any, Dict, List

from code_puppy.agents.base_agent import BaseAgent
from code_puppy.callbacks import register_callback
from code_puppy.messaging import emit_info

logger = logging.getLogger(__name__)

# ============================================================================
# DUMMY TOOL REGISTRATION
# ============================================================================


def _register_dummy_tool(agent) -> None:
    """Register a dummy tool on the agent for testing."""

    @agent.tool
    def cp_ralph_test_echo(text: str) -> str:
        """Echo back the input text with a prefix.

        This is a dummy tool to test plugin tool registration.

        Args:
            text: The text to echo back.

        Returns:
            The text with a prefix indicating it came from the ralph_test plugin.
        """
        return f"[ralph_test echo] {text}"

    return None


def _provide_tools() -> List[Dict[str, Any]]:
    """Provide tools to register via the register_tools callback.

    Returns:
        List of tool definitions with name and register_func.
    """
    logger.debug("ralph_test plugin: providing dummy tools")
    return [
        {
            "name": "ralph_test_echo",
            "register_func": _register_dummy_tool,
        }
    ]


# ============================================================================
# DUMMY AGENT REGISTRATION
# ============================================================================


class DummyRalphTestAgent(BaseAgent):
    """A dummy agent for testing plugin agent registration."""

    @property
    def name(self) -> str:
        return "ralph-test-dummy"

    @property
    def display_name(self) -> str:
        return "Ralph Test Dummy 🧪"

    @property
    def description(self) -> str:
        return "A dummy agent for testing the register_agents callback hook"

    def get_system_prompt(self) -> str:
        return """You are a test agent created by the ralph_test plugin.

Your only purpose is to verify that plugin-registered agents work correctly.
When asked anything, respond with: "Hello from the ralph-test-dummy agent!"
"""

    def get_available_tools(self) -> List[str]:
        return ["list_files", "read_file", "ralph_test_echo"]


def _provide_agents() -> List[Dict[str, Any]]:
    """Provide agents to register via the register_agents callback.

    Returns:
        List of agent definitions with name and class.
    """
    logger.debug("ralph_test plugin: providing dummy agents")
    return [
        {
            "name": "ralph-test-dummy",
            "class": DummyRalphTestAgent,
        }
    ]


# ============================================================================
# AGENT RESPONSE COMPLETE HOOK
# ============================================================================

_response_log: List[Dict[str, Any]] = []


async def _on_agent_complete(
    agent_name: str,
    response_text: str,
    session_id: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Handle agent response completion for testing.

    This logs completions and checks for special markers.
    """
    logger.debug(
        f"ralph_test plugin: agent '{agent_name}' completed (session={session_id})"
    )

    # Store for testing inspection
    _response_log.append(
        {
            "agent_name": agent_name,
            "response_text": response_text[:200]
            if response_text
            else "",  # Truncate for logging
            "session_id": session_id,
            "metadata": metadata,
        }
    )

    # Check for Ralph completion signal
    if response_text and "<promise>COMPLETE</promise>" in response_text:
        emit_info("🎉 [ralph_test] Detected COMPLETE signal in agent response!")
        logger.info(f"Ralph completion signal detected from agent '{agent_name}'")


def get_response_log() -> List[Dict[str, Any]]:
    """Get the log of agent completions (for testing)."""
    return _response_log.copy()


def clear_response_log() -> None:
    """Clear the response log (for testing)."""
    _response_log.clear()


# ============================================================================
# REGISTER ALL CALLBACKS
# ============================================================================

register_callback("register_tools", _provide_tools)
register_callback("register_agents", _provide_agents)
register_callback("agent_response_complete", _on_agent_complete)

logger.info("ralph_test plugin: callbacks registered successfully")
