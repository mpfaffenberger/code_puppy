"""WebSocket endpoint handlers package.

Each handler module exposes a `register_*_endpoint(app)` function
that attaches one WebSocket route to the FastAPI application.

Modules:
    - chat_handler: Interactive chat with the Code Puppy agent (/ws/chat)
    - events_handler: Server-sent events stream (/ws/events)
    - health_handler: Simple health check (/ws/health)
    - connection_manager: Singleton for broadcasting session updates
    - attachments: File attachment processing utilities
"""

from code_puppy.api.ws.chat_handler import register_chat_endpoint
from code_puppy.api.ws.connection_manager import connection_manager
from code_puppy.api.ws.events_handler import register_events_endpoint
from code_puppy.api.ws.health_handler import register_health_endpoint

__all__ = [
    "register_chat_endpoint",
    "register_events_endpoint",
    "register_health_endpoint",
    "connection_manager",
]
