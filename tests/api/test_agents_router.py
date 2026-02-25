"""Tests for code_puppy/api/routers/agents.py."""

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from code_puppy.api.app import create_app


@pytest.fixture
async def client():
    with (
        patch(
            "code_puppy.agents.get_available_agents",
            return_value={"main": "Main Agent"},
            create=True,
        ),
        patch(
            "code_puppy.agents.get_agent_descriptions",
            return_value={"main": "The main agent"},
            create=True,
        ),
    ):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@pytest.mark.asyncio
async def test_list_agents(client: AsyncClient) -> None:
    resp = await client.get("/api/agents/")
    assert resp.status_code == 200
    agents = resp.json()
    assert len(agents) == 1
    assert agents[0]["name"] == "main"
    assert agents[0]["display_name"] == "Main Agent"
    assert agents[0]["description"] == "The main agent"
