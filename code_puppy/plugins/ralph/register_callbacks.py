"""Ralph Plugin - Autonomous AI agent loop for completing PRDs.

This module registers all Ralph callbacks:
- register_tools: Ralph-specific tools for PRD management
- register_agents: PRD Generator, Converter, and Orchestrator agents
- custom_command: /ralph slash commands
- custom_command_help: Help entries for Ralph commands
- agent_response_complete: Detect completion signal for loop termination
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from code_puppy.callbacks import register_callback
from code_puppy.messaging import emit_info, emit_success

logger = logging.getLogger(__name__)


# ============================================================================
# TOOL REGISTRATION
# ============================================================================


def _provide_tools() -> List[Dict[str, Any]]:
    """Provide Ralph tools via the register_tools callback."""
    from .tools import get_ralph_tools

    logger.debug("Ralph plugin: providing tools")
    return get_ralph_tools()


# ============================================================================
# AGENT REGISTRATION
# ============================================================================


def _provide_agents() -> List[Dict[str, Any]]:
    """Provide Ralph agents via the register_agents callback."""
    from .agents import get_ralph_agents

    logger.debug("Ralph plugin: providing agents")
    return get_ralph_agents()


# ============================================================================
# COMMAND REGISTRATION
# ============================================================================


def _provide_command_help() -> List[Tuple[str, str]]:
    """Provide help entries for Ralph commands."""
    from .commands import get_ralph_help

    return get_ralph_help()


def _handle_command(command: str, name: str) -> Optional[Any]:
    """Handle /ralph commands."""
    from .commands import handle_ralph_command

    return handle_ralph_command(command, name)


# ============================================================================
# COMPLETION DETECTION
# ============================================================================

# Track completion state for the loop controller
_ralph_completion_detected = False
_ralph_last_session_id: Optional[str] = None


def is_ralph_complete() -> bool:
    """Check if Ralph has signaled completion."""
    return _ralph_completion_detected


def reset_ralph_completion() -> None:
    """Reset the completion flag for a new run."""
    global _ralph_completion_detected, _ralph_last_session_id
    _ralph_completion_detected = False
    _ralph_last_session_id = None


async def _on_agent_complete(
    agent_name: str,
    response_text: str,
    session_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    """Handle agent response completion.

    This detects the <promise>COMPLETE</promise> signal from the
    Ralph Orchestrator and sets the completion flag.
    """
    global _ralph_completion_detected, _ralph_last_session_id

    # Only track ralph-orchestrator completions
    if agent_name != "ralph-orchestrator":
        return

    logger.debug(f"Ralph plugin: orchestrator completed (session={session_id})")

    # Check for completion signal
    if response_text and "<promise>COMPLETE</promise>" in response_text:
        _ralph_completion_detected = True
        _ralph_last_session_id = session_id

        emit_success("🎉 Ralph has completed all user stories!")
        emit_info("All tasks in prd.json are now marked as passes: true")
        logger.info("Ralph completion signal detected - all stories complete")


# ============================================================================
# REGISTER ALL CALLBACKS
# ============================================================================

# Tools
register_callback("register_tools", _provide_tools)

# Agents
register_callback("register_agents", _provide_agents)

# Commands
register_callback("custom_command", _handle_command)
register_callback("custom_command_help", _provide_command_help)

# Completion detection
register_callback("agent_response_complete", _on_agent_complete)


logger.info("Ralph plugin: all callbacks registered successfully")
