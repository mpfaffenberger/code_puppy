"""Agents API endpoints for agent management.

This router provides REST endpoints for:
- Listing all available agents with their metadata
"""

from typing import Any, Dict, List

from fastapi import APIRouter

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
