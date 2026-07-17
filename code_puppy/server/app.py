"""ASGI API for the headless Mist runtime."""

from __future__ import annotations

import json
from typing import Any

from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    StreamingResponse,
)
from starlette.routing import Route

from code_puppy.server.auth import load_or_create_token
from code_puppy.server.session_manager import SessionManager


def _error(message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


def create_app(
    manager: SessionManager | None = None,
    *,
    token: str | None = None,
) -> Starlette:
    from code_puppy.config import CONFIG_DIR

    runtime = manager or SessionManager()
    bearer = token or load_or_create_token(
        __import__("pathlib").Path(CONFIG_DIR) / "server.json"
    )

    async def auth(request: Request, call_next):
        if request.url.path in {
            "/",
            "/doc",
            "/openapi.json",
        } or request.url.path.startswith("/share/"):
            return await call_next(request)
        if request.headers.get("authorization") != f"Bearer {bearer}":
            return _error("Unauthorized", 401)
        return await call_next(request)

    async def create_session(request: Request) -> JSONResponse:
        body = await _json_body(request)
        record = await runtime.create_session(body.get("agent_name"))
        return JSONResponse(record.public(), status_code=201)

    async def list_sessions(_: Request) -> JSONResponse:
        return JSONResponse({"sessions": runtime.list_sessions()})

    async def get_session(request: Request) -> JSONResponse:
        try:
            return JSONResponse(
                runtime.get_session(request.path_params["session_id"]).public()
            )
        except KeyError as exc:
            return _error(str(exc), 404)

    async def submit(request: Request) -> JSONResponse:
        body = await _json_body(request)
        try:
            await runtime.submit(
                request.path_params["session_id"], str(body.get("prompt", ""))
            )
        except KeyError as exc:
            return _error(str(exc), 404)
        except (ValueError, RuntimeError) as exc:
            return _error(str(exc), 409 if isinstance(exc, RuntimeError) else 400)
        return JSONResponse({"accepted": True}, status_code=202)

    async def fork_session(request: Request) -> JSONResponse:
        body = await _json_body(request)
        try:
            record = await runtime.fork(
                request.path_params["session_id"], message_id=body.get("message_id")
            )
        except KeyError as exc:
            return _error(str(exc), 404)
        return JSONResponse(record.public(), status_code=201)

    async def interrupt(request: Request) -> JSONResponse:
        try:
            interrupted = await runtime.interrupt(request.path_params["session_id"])
        except KeyError as exc:
            return _error(str(exc), 404)
        return JSONResponse({"interrupted": interrupted})

    async def events(request: Request) -> StreamingResponse | JSONResponse:
        session_id = request.path_params["session_id"]
        try:
            runtime.get_session(session_id)
        except KeyError as exc:
            return _error(str(exc), 404)
        raw_after = request.headers.get("last-event-id") or request.query_params.get(
            "after", "0"
        )
        try:
            after = max(0, int(raw_after))
        except ValueError:
            return _error("Last-Event-ID must be an integer", 400)

        async def stream():
            async for event in runtime.events(session_id, after=after):
                yield f"id: {event.sequence}\nevent: {event.type}\ndata: {event.model_dump_json()}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    async def create_share(request: Request) -> JSONResponse:
        try:
            share_id, _ = runtime.share(request.path_params["session_id"])
        except KeyError as exc:
            return _error(str(exc), 404)
        return JSONResponse({"url": f"/share/{share_id}"}, status_code=201)

    async def get_share(request: Request) -> FileResponse | JSONResponse:
        share_id = request.path_params["share_id"]
        if not share_id.isalnum():
            return _error("Invalid share id", 400)
        path = runtime.state_dir / "shares" / f"{share_id}.html"
        if not path.exists():
            return _error("Unknown share", 404)
        return FileResponse(path, media_type="text/html")

    async def openapi(_: Request) -> JSONResponse:
        return JSONResponse(_openapi_schema())

    async def docs(_: Request) -> HTMLResponse:
        return HTMLResponse(
            "<!doctype html><title>Mist API</title><h1>Mist API</h1>"
            '<p>OpenAPI schema: <a href="/openapi.json">/openapi.json</a></p>'
        )

    async def home(_: Request) -> HTMLResponse:
        from code_puppy.server.web import WEB_CLIENT_HTML

        return HTMLResponse(WEB_CLIENT_HTML)

    routes = [
        Route("/", home),
        Route("/doc", docs),
        Route("/openapi.json", openapi),
        Route("/session", create_session, methods=["POST"]),
        Route("/sessions", list_sessions),
        Route("/session/{session_id}", get_session),
        Route("/session/{session_id}/message", submit, methods=["POST"]),
        Route("/session/{session_id}/fork", fork_session, methods=["POST"]),
        Route("/session/{session_id}/interrupt", interrupt, methods=["POST"]),
        Route("/session/{session_id}/events", events),
        Route("/session/{session_id}/share", create_share, methods=["POST"]),
        Route("/share/{share_id}", get_share),
    ]
    app = Starlette(routes=routes)
    app.add_middleware(BaseHTTPMiddleware, dispatch=auth)
    app.state.session_manager = runtime
    app.state.token = bearer
    return app


async def _json_body(request: Request) -> dict[str, Any]:
    try:
        value = await request.json()
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _openapi_schema() -> dict[str, Any]:
    from code_puppy.events import EventEnvelope

    session_response = {
        "description": "Session",
        "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/Session"}}
        },
    }
    paths = {
        "/session": {
            "post": {
                "operationId": "createSession",
                "summary": "Create a session",
                "requestBody": _request_schema("CreateSessionRequest"),
                "responses": {"201": session_response},
            }
        },
        "/sessions": {
            "get": {
                "operationId": "listSessions",
                "summary": "List sessions",
                "responses": {"200": {"description": "Session list"}},
            }
        },
        "/session/{session_id}": {
            "get": {
                "operationId": "getSession",
                "summary": "Get a session",
                "responses": {"200": session_response},
            }
        },
        "/session/{session_id}/message": {
            "post": {
                "operationId": "submitPrompt",
                "summary": "Submit a prompt",
                "requestBody": _request_schema("SubmitRequest"),
                "responses": {"202": {"description": "Accepted"}},
            }
        },
        "/session/{session_id}/fork": {
            "post": {
                "operationId": "forkSession",
                "summary": "Fork a session tree",
                "requestBody": _request_schema("ForkRequest"),
                "responses": {"201": session_response},
            }
        },
        "/session/{session_id}/events": {
            "get": {
                "operationId": "streamEvents",
                "summary": "Stream EventEnvelope objects over SSE",
                "responses": {
                    "200": {
                        "description": "SSE stream",
                        "content": {
                            "text/event-stream": {"schema": {"type": "string"}}
                        },
                    }
                },
            }
        },
        "/session/{session_id}/interrupt": {
            "post": {
                "operationId": "interruptSession",
                "summary": "Interrupt a run",
                "responses": {"200": {"description": "Interrupt result"}},
            }
        },
    }
    session_parameter = {
        "name": "session_id",
        "in": "path",
        "required": True,
        "schema": {"type": "string"},
    }
    for path, item in paths.items():
        if "{session_id}" in path:
            item["parameters"] = [session_parameter]
    return {
        "openapi": "3.1.0",
        "info": {"title": "Mist Agent API", "version": "1"},
        "paths": paths,
        "components": {
            "securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}},
            "schemas": {
                "EventEnvelope": EventEnvelope.model_json_schema(),
                "Session": {
                    "type": "object",
                    "required": ["id", "agent_name", "state", "last_event_id"],
                    "properties": {
                        "id": {"type": "string"},
                        "agent_name": {"type": "string"},
                        "state": {"type": "string"},
                        "last_event_id": {"type": "integer"},
                        "created_at": {"type": "string", "format": "date-time"},
                        "updated_at": {"type": "string", "format": "date-time"},
                        "error": {"type": ["string", "null"]},
                    },
                },
                "CreateSessionRequest": {
                    "type": "object",
                    "properties": {"agent_name": {"type": ["string", "null"]}},
                },
                "SubmitRequest": {
                    "type": "object",
                    "required": ["prompt"],
                    "properties": {"prompt": {"type": "string"}},
                },
                "ForkRequest": {
                    "type": "object",
                    "properties": {"message_id": {"type": ["string", "null"]}},
                },
            },
        },
        "security": [{"bearerAuth": []}],
    }


def _request_schema(name: str) -> dict[str, Any]:
    return {
        "required": True,
        "content": {
            "application/json": {"schema": {"$ref": f"#/components/schemas/{name}"}}
        },
    }
