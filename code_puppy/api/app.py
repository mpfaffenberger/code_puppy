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
    # Startup: nothing special needed yet, but this is where you'd do it
    logger.info("🐶 Code Puppy API starting up...")
    yield
    # Shutdown: clean up all the things!
    logger.info("🐶 Code Puppy API shutting down, cleaning up...")

    # 1. Close all PTY sessions
    try:
        from code_puppy.api.pty_manager import get_pty_manager

        pty_manager = get_pty_manager()
        await pty_manager.close_all()
        logger.info("✓ All PTY sessions closed")
    except Exception as e:
        logger.error(f"Error closing PTY sessions: {e}")

    # 2. Remove PID file so /api status knows we're gone
    try:
        from code_puppy.config import STATE_DIR

        pid_file = Path(STATE_DIR) / "api_server.pid"
        if pid_file.exists():
            pid_file.unlink()
            logger.info("✓ PID file removed")
    except Exception as e:
        logger.error(f"Error removing PID file: {e}")


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
    from code_puppy.api.routers import agents, commands, config, sessions

    app.include_router(config.router, prefix="/api/config", tags=["config"])
    app.include_router(commands.router, prefix="/api/commands", tags=["commands"])
    app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
    app.include_router(agents.router, prefix="/api/agents", tags=["agents"])

    # WebSocket endpoints (events + terminal)
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
            <a href="/terminal" class="px-6 py-3 bg-blue-600 hover:bg-blue-700 rounded-lg text-lg font-semibold">
                Open Terminal
            </a>
            <a href="/docs" class="px-6 py-3 bg-gray-700 hover:bg-gray-600 rounded-lg text-lg">
                API Docs
            </a>
        </div>
        <p class="mt-8 text-gray-400">
            WebSocket: ws://localhost:8765/ws/terminal
        </p>
    </div>
</body>
</html>
        """
        )

    @app.get("/terminal")
    async def terminal_page():
        """Serve the interactive terminal page."""
        html_file = templates_dir / "terminal.html"
        if html_file.exists():
            return FileResponse(html_file, media_type="text/html")
        return HTMLResponse(
            content="<h1>Terminal template not found</h1>",
            status_code=404,
        )

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    return app
