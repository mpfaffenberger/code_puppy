from __future__ import annotations

import httpx

from code_puppy.messaging.bus import MessageBus
from code_puppy.server.app import create_app
from code_puppy.server.session_manager import SessionManager
from tests.server.test_session_manager import FakeAgent


async def test_http_api_auth_lifecycle_and_share(tmp_path):
    bus = MessageBus()
    manager = SessionManager(
        state_dir=tmp_path,
        bus=bus,
        agent_factory=lambda name: FakeAgent(name, bus),
    )
    app = create_app(manager, token="test-token")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/sessions")).status_code == 401
        headers = {"Authorization": "Bearer test-token"}
        created = await client.post("/session", json={}, headers=headers)
        assert created.status_code == 201
        session_id = created.json()["id"]

        accepted = await client.post(
            f"/session/{session_id}/message",
            json={"prompt": "hello"},
            headers=headers,
        )
        assert accepted.status_code == 202
        await manager.get_session(session_id).task

        detail = await client.get(f"/session/{session_id}", headers=headers)
        assert detail.json()["state"] == "idle"
        shared = await client.post(f"/session/{session_id}/share", headers=headers)
        share_page = await client.get(shared.json()["url"])
        assert "Redacted, read-only export" in share_page.text

        schema = await client.get("/openapi.json")
        assert "/session/{session_id}/events" in schema.json()["paths"]
        assert (
            schema.json()["paths"]["/session/{session_id}/message"]["post"][
                "operationId"
            ]
            == "submitPrompt"
        )
        assert "EventEnvelope" in schema.json()["components"]["schemas"]
    manager.close()


async def test_web_client_is_thin_transport_ui(tmp_path):
    bus = MessageBus()
    manager = SessionManager(
        state_dir=tmp_path,
        bus=bus,
        agent_factory=lambda name: FakeAgent(name, bus),
    )
    app = create_app(manager, token="test-token")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        page = await client.get("/")
    assert "Thin web client" in page.text
    assert "/events" in page.text
    manager.close()
