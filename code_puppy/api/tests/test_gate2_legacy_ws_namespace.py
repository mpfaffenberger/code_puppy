"""Post-cleanup WebSocket namespace tests for puppy-desk migration."""

from pathlib import Path

from fastapi import FastAPI, WebSocket


def test_setup_websocket_keeps_existing_chat_route_and_no_extra_routes(monkeypatch):
    import code_puppy.api.websocket as websocket_module

    def _register_chat(app):
        @app.websocket("/ws/chat")
        async def _chat(_ws: WebSocket):
            return None

    def _register_events(app):
        @app.websocket("/ws/events")
        async def _events(_ws: WebSocket):
            return None

    def _register_health(app):
        @app.websocket("/ws/health")
        async def _health(_ws: WebSocket):
            return None

    monkeypatch.setattr(websocket_module, "register_chat_endpoint", _register_chat)
    monkeypatch.setattr(websocket_module, "register_events_endpoint", _register_events)
    monkeypatch.setattr(websocket_module, "register_health_endpoint", _register_health)

    app = FastAPI()
    websocket_module.setup_websocket(app)

    websocket_paths = {
        getattr(route, "path", None)
        for route in app.routes
        if getattr(route, "path", None)
    }

    assert "/ws/chat" in websocket_paths
    assert "/ws/events" in websocket_paths
    assert "/ws/health" in websocket_paths
    assert "/ws/terminal" not in websocket_paths
    assert "/ws/sessions" not in websocket_paths
    assert "/ws/chat-migration" not in websocket_paths
    assert "/ws/chat-next" not in websocket_paths
    assert "/ws/chat-v2" not in websocket_paths


def test_legacy_ws_snapshot_removed_after_cleanup():
    ws_dir = Path(__file__).resolve().parents[1] / "ws"
    assert not (ws_dir / "legacy").exists()
