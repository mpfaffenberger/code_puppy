"""Agents API endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_agents():
    """List all available agents.

    Returns:
        dict: Agents endpoint placeholder response.
    """
    return {"message": "Agents endpoint - TODO"}
