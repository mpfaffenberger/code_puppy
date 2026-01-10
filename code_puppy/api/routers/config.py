"""Configuration management API endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_config():
    """List all configuration settings.

    Returns:
        dict: Configuration endpoint placeholder response.
    """
    return {"message": "Config endpoint - TODO"}
