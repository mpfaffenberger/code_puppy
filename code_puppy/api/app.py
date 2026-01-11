"""FastAPI application factory for Code Puppy API."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Code Puppy API",
        description="REST API and Interactive Terminal for Code Puppy",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

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
