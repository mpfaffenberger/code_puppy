"""FastAPI application factory for Code Puppy API."""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


logger = logging.getLogger(__name__)

# Default request timeout (seconds) - fail fast!
REQUEST_TIMEOUT = 30.0


class TimeoutMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce request timeouts and prevent hanging requests."""

    def __init__(self, app, timeout: float = REQUEST_TIMEOUT):
        super().__init__(app)
        self.timeout = timeout

    async def dispatch(self, request: Request, call_next):
        # Skip timeout for WebSocket upgrades and streaming endpoints
        if request.headers.get(
            "upgrade", ""
        ).lower() == "websocket" or request.url.path.startswith("/ws/"):
            return await call_next(request)

        try:
            return await asyncio.wait_for(
                call_next(request),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError:
            return JSONResponse(
                status_code=504,
                content={
                    "detail": f"Request timed out after {self.timeout}s",
                    "error": "timeout",
                },
            )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager for startup and shutdown events.

    Handles graceful cleanup of resources when the server shuts down.
    """
    # Startup
    logger.info("🐶 Code Puppy API starting up...")

    # Load plugin callbacks (including frontend_emitter for real-time streaming)
    from code_puppy import plugins

    result = plugins.load_plugin_callbacks()
    logger.info(
        f"✓ Loaded plugins: builtin={result.get('builtin', [])}, user={result.get('user', [])}, external={result.get('external', [])}"
    )

    # Initialise shared SQLite database
    try:
        from code_puppy.api.db.connection import init_db

        await init_db()
        logger.info("✓ aiosqlite DB initialised")
    except Exception as _db_exc:
        logger.error("SQLite DB init failed (continuing without DB): %s", _db_exc)

    yield
    # Shutdown: clean up all the things!
    logger.info("🐶 Code Puppy API shutting down, cleaning up...")

    # 1. Shutdown session cache thread pool executor
    try:
        from code_puppy.api.session_cache import shutdown_executor

        await shutdown_executor()
        logger.info("✓ Session cache executor shut down")
    except Exception as e:
        logger.error("Error shutting down session cache executor: %s", e)

    # 2. Shutdown ws_sessions thread pool executor
    try:
        from code_puppy.api.routers import ws_sessions

        ws_sessions._executor.shutdown(wait=False)
        logger.info("✓ WS sessions executor shut down")
    except Exception as e:
        logger.error("Error shutting down ws_sessions executor: %s", e)

    # 4. Remove PID file so /api status knows we're gone
    try:
        from code_puppy.config import STATE_DIR

        pid_file = Path(STATE_DIR) / "api_server.pid"
        if pid_file.exists():
            pid_file.unlink()
            logger.info("✓ PID file removed")
    except Exception as e:
        logger.error("Error removing PID file: %s", e)

    # 6. Close SQLite database
    try:
        from code_puppy.api.db.connection import close_db

        await close_db()
        logger.info("✓ aiosqlite DB closed")
    except Exception as e:
        logger.error("Error closing SQLite DB: %s", e)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        lifespan=lifespan,
        title="Code Puppy API",
        description="REST API and Interactive Terminal for Code Puppy",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Timeout middleware - added first so it wraps everything
    app.add_middleware(TimeoutMiddleware, timeout=REQUEST_TIMEOUT)

    # CORS middleware for frontend access
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Local/trusted
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    from code_puppy.api.routers import (
        agents,
        commands,
        config,
        sessions,
        ws_sessions,
    )

    app.include_router(config.router, prefix="/api/config", tags=["config"])
    app.include_router(commands.router, prefix="/api/commands", tags=["commands"])
    app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
    app.include_router(
        ws_sessions.router, prefix="/api/ws-sessions", tags=["ws-sessions"]
    )
    app.include_router(agents.router, prefix="/api/agents", tags=["agents"])

    from code_puppy.api.routers import models

    app.include_router(models.router, prefix="/api/models", tags=["models"])

    from code_puppy.api.routers import protocol

    app.include_router(protocol.router, prefix="/api/protocol", tags=["protocol"])

    # WebSocket endpoints
    from code_puppy.api.websocket import setup_websocket

    setup_websocket(app)

    # Templates directory
    templates_dir = Path(__file__).parent / "templates"

    @app.get("/")
    async def root():
        """Landing page with links to terminal and docs."""
        return HTMLResponse(
            content="""
<!DOCTYPE html>
<html>
<head>
    <title>Code Puppy 🐶</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-900 text-white min-h-screen flex items-center justify-center">
    <div class="text-center">
        <h1 class="text-6xl mb-4">🐶</h1>
        <h2 class="text-3xl font-bold mb-8">Code Puppy</h2>
        <div class="space-x-4">
            <a href="/chat" class="px-6 py-3 bg-green-600 hover:bg-green-700 rounded-lg text-lg font-semibold">
                Open Chat
            </a>
            <a href="/docs" class="px-6 py-3 bg-gray-700 hover:bg-gray-600 rounded-lg text-lg">
                API Docs
            </a>
        </div>
        <p class="mt-8 text-gray-400">
            WebSocket: ws://localhost:8765/ws/chat
        </p>
    </div>
</body>
</html>
        """
        )

    @app.get("/chat")
    async def chat_page():
        """Serve the chat interface page."""
        html_file = templates_dir / "chat.html"
        if html_file.exists():
            return FileResponse(html_file, media_type="text/html")
        return HTMLResponse(
            content="<h1>Chat template not found</h1>",
            status_code=404,
        )

    @app.get("/health")
    async def health():
        """Simple health check endpoint."""
        return {"status": "healthy"}

    @app.get("/api/version-check")
    async def version_check():
        """
        Check current version and latest available version.

        Returns:
            dict: Contains current_version, latest_version, and update_available
        """
        from code_puppy import __version__
        from code_puppy.version_checker import fetch_latest_version, versions_are_equal

        current_version = __version__
        latest_version = fetch_latest_version("code-puppy")

        # Determine if update is available
        update_available = False
        if latest_version:
            update_available = not versions_are_equal(current_version, latest_version)

        return {
            "current_version": current_version,
            "latest_version": latest_version or current_version,
            "update_available": update_available,
            "status": "success" if latest_version else "error_fetching_latest",
        }

    return app
