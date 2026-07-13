"""Protocol schema endpoint – exposes JSON Schema for the WebSocket protocol."""

from fastapi import APIRouter
from pydantic import TypeAdapter

from code_puppy.api.ws.schemas import (
    PROTOCOL_VERSION,
    ClientMessage,
    ServerMessage,
)

router = APIRouter()

# Cache the schemas since they don't change at runtime
_client_schema = TypeAdapter(ClientMessage).json_schema()
_server_schema = TypeAdapter(ServerMessage).json_schema()


@router.get("/schema")
async def get_protocol_schema():
    """Return the WebSocket protocol JSON Schema for client consumption."""
    return {
        "protocol_version": PROTOCOL_VERSION,
        "client_messages": _client_schema,
        "server_messages": _server_schema,
    }
