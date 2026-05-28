"""Models API endpoint for listing available models."""

from typing import Any, Dict, List

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_models() -> List[Dict[str, Any]]:
    """List all available model names from models.json config.

    Returns:
        List of dicts with 'name' key for each model.
    """
    from code_puppy.model_factory import ModelFactory

    try:
        config = ModelFactory.load_config()
        return [{"name": name} for name in sorted(config.keys())]
    except Exception:
        return []
