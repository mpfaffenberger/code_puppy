"""FastAPI application factory for Code Puppy API."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Code Puppy API",
        description="REST API for Code Puppy configuration, sessions, and commands",
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

    # WebSocket endpoint
    from code_puppy.api.websocket import setup_websocket

    setup_websocket(app)

    @app.get("/")
    async def root():
        return {"message": "Code Puppy API", "version": "1.0.0", "docs": "/docs"}

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    return app
