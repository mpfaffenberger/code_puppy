"""Commands API endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_commands():
    """List all available commands.

    Returns:
        dict: Commands endpoint placeholder response.
    """
    return {"message": "Commands endpoint - TODO"}
