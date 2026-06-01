"""Gate 2 smoke tests for puppy-desk migration safety.

These tests ensure the legacy WS snapshot exists while the active WebSocket
registration still exposes the original `/ws/chat` route and does not expose a
migration side-route yet.
"""

from pathlib import Path

from fastapi import FastAPI


def test_setup_websocket_keeps_existing_chat_route_and_no_migration_route():
    from code_puppy.api.websocket import setup_websocket

    app = FastAPI()
    setup_websocket(app)

    websocket_paths = {
        getattr(route, "path", None)
        for route in app.routes
        if getattr(route, "path", None)
    }

    assert "/ws/chat" in websocket_paths
    assert "/ws/terminal" not in websocket_paths
    assert "/ws/sessions" not in websocket_paths
    assert "/ws/chat-migration" not in websocket_paths
    assert "/ws/chat-next" not in websocket_paths
    assert "/ws/chat-v2" not in websocket_paths


def test_legacy_ws_snapshot_namespace_exists_without_route_registration():
    import code_puppy.api.ws.legacy as legacy_ws

    legacy_dir = Path(legacy_ws.__file__).parent

    assert legacy_ws.LEGACY_SNAPSHOT_PURPOSE == "puppy-desk-gate2-reference-copy"
    assert (legacy_dir / "chat_handler.py").is_file()
    assert (legacy_dir / "schemas.py").is_file()
    assert (legacy_dir / "runtime" / "session_runtime_manager.py").is_file()
    assert (legacy_dir / "README.md").is_file()
