"""Agents API endpoints for agent management.

This router provides REST endpoints for:
- Listing all available agents with their metadata
- Refreshing the agent registry to discover new agents
- Switching the current active agent
"""

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


@router.get("/")
async def list_agents() -> List[Dict[str, Any]]:
    """List all available agents.

    Returns a list of all agents registered in the system,
    including their name, display name, and description.

    Returns:
        List[Dict[str, Any]]: List of agent information dictionaries.
    """
    from code_puppy.agents import get_agent_descriptions, get_available_agents

    agents_dict = get_available_agents()
    descriptions = get_agent_descriptions()

    return [
        {
            "name": name,
            "display_name": display_name,
            "description": descriptions.get(name, "No description"),
        }
        for name, display_name in agents_dict.items()
    ]


@router.post("/refresh")
async def refresh_agents_endpoint() -> Dict[str, Any]:
    """Force refresh the agents list by re-running agent discovery.

    This endpoint triggers the agent manager to re-scan for:
    - Python agent classes in the agents package
    - JSON agent configuration files in user directory
    - Plugin-registered agents

    Returns:
        Dict[str, Any]: Result containing:
            - success (bool): True if refresh completed
            - count (int): Number of agents discovered
            - message (str): Status message
    """
    from code_puppy.agents import get_available_agents
    from code_puppy.agents import refresh_agents as do_refresh_agents

    # Refresh agents - this will call _discover_agents() again
    do_refresh_agents()

    # Get the fresh count
    agents = get_available_agents()

    return {
        "success": True,
        "count": len(agents),
        "message": "Agent discovery refreshed",
    }


class SwitchAgentRequest(BaseModel):
    """Request model for switching agents."""

    agent_name: str


@router.post("/switch")
async def switch_agent(request: SwitchAgentRequest) -> Dict[str, Any]:
    """Switch to a different agent.

    Args:
        request: SwitchAgentRequest containing:
            - agent_name (str): The name of the agent to switch to

    Returns:
        Dict[str, Any]: Result containing:
            - success (bool): True if switch was successful
            - agentName (str): The name of the agent switched to
            - message (str): Success message

    Raises:
        HTTPException: If agent not found (404) or switch fails (500)
    """
    from code_puppy.agents import get_current_agent, set_current_agent

    agent_name = request.agent_name

    if not agent_name:
        raise HTTPException(status_code=400, detail="agent_name is required")

    # Switch to the new agent
    success = set_current_agent(agent_name)

    if not success:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    # Get the new current agent for display name
    current = get_current_agent()

    return {
        "success": True,
        "agentName": current.name,
        "message": f"Switched to {current.display_name}",
    }
