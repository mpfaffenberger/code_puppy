"""Sessions API endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_sessions():
    """List all sessions.

    Returns:
        dict: Sessions endpoint placeholder response.
    """
    return {"message": "Sessions endpoint - TODO"}
