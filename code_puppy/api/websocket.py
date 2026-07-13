"""WebSocket endpoints for Code Puppy API.

Provides real-time communication channels:
- /ws/events - Server-sent events stream
- /ws/chat - Interactive chat with the agent
- /ws/health - Simple health check endpoint

This module is the thin entry point that registers all WebSocket endpoints.
Each handler lives in its own module under `code_puppy.api.ws.*` for
maintainability.
"""

import logging

from fastapi import FastAPI

from code_puppy.api.ws import (
    register_chat_endpoint,
    register_events_endpoint,
    register_health_endpoint,
)

# Re-export build_file_context_and_attachments for backward compatibility
from code_puppy.api.ws.attachments import (  # noqa: F401
    build_file_context_and_attachments,
)

# Re-export connection_manager for backward compatibility
from code_puppy.api.ws.connection_manager import (  # noqa: F401
    WebSocketConnectionManager,
)

logger = logging.getLogger(__name__)


def setup_websocket(app: FastAPI) -> None:
    """Setup WebSocket endpoints for the application.

    Registers all WebSocket routes by delegating to specialized handler modules.
    """
    register_events_endpoint(app)
    register_chat_endpoint(app)
    register_health_endpoint(app)

    logger.debug("WebSocket endpoints registered")
