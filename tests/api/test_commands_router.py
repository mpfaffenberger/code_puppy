"""Tests for code_puppy/api/routers/commands.py."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from code_puppy.api.app import create_app


def _make_cmd(
    name="test",
    description="A test command",
    usage="/test",
    aliases=None,
    category="core",
    detailed_help=None,
):
    cmd = MagicMock()
    cmd.name = name
    cmd.description = description
    cmd.usage = usage
    cmd.aliases = aliases or []
    cmd.category = category
    cmd.detailed_help = detailed_help
    return cmd


@pytest.fixture
def mock_commands():
    cmds = [
        _make_cmd("help", "Show help", "/help", ["h"]),
        _make_cmd("set", "Set config", "/set key=value", ["s"]),
    ]
    with (
        patch(
            "code_puppy.command_line.command_registry.get_unique_commands",
            return_value=cmds,
            create=True,
        ) as mock_unique,
        patch(
            "code_puppy.command_line.command_registry.get_command", create=True
        ) as mock_get,
    ):

        def _get_cmd(name):
            for c in cmds:
                if c.name == name or name in c.aliases:
                    return c
            return None

        mock_get.side_effect = _get_cmd
        yield {"unique": mock_unique, "get": mock_get, "cmds": cmds}


@pytest.fixture
async def client(mock_commands):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_list_commands(client: AsyncClient) -> None:
    resp = await client.get("/api/commands/")
    assert resp.status_code == 200
    cmds = resp.json()
    assert len(cmds) == 2
    names = [c["name"] for c in cmds]
    assert "help" in names


@pytest.mark.asyncio
async def test_get_command_info(client: AsyncClient) -> None:
    resp = await client.get("/api/commands/help")
    assert resp.status_code == 200
    assert resp.json()["name"] == "help"


@pytest.mark.asyncio
async def test_get_command_not_found(client: AsyncClient) -> None:
    resp = await client.get("/api/commands/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_execute_command(client: AsyncClient) -> None:
    with patch(
        "code_puppy.command_line.command_handler.handle_command",
        return_value="done",
        create=True,
    ):
        resp = await client.post("/api/commands/execute", json={"command": "/help"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_execute_command_without_slash(client: AsyncClient) -> None:
    with patch(
        "code_puppy.command_line.command_handler.handle_command",
        return_value="done",
        create=True,
    ):
        resp = await client.post("/api/commands/execute", json={"command": "help"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_execute_command_timeout(client: AsyncClient) -> None:
    async def slow(*a, **kw):
        await asyncio.sleep(100)

    with (
        patch("code_puppy.api.routers.commands.COMMAND_TIMEOUT", 0.01),
        patch(
            "code_puppy.command_line.command_handler.handle_command",
            side_effect=lambda *a: __import__("time").sleep(1),
            create=True,
        ),
    ):
        resp = await client.post("/api/commands/execute", json={"command": "/help"})
        assert resp.status_code == 200
        assert resp.json()["success"] is False
        assert "timed out" in resp.json()["error"].lower()


@pytest.mark.asyncio
async def test_execute_command_error(client: AsyncClient) -> None:
    with patch(
        "code_puppy.command_line.command_handler.handle_command",
        side_effect=ValueError("bad"),
        create=True,
    ):
        resp = await client.post("/api/commands/execute", json={"command": "/help"})
        assert resp.status_code == 200
        assert resp.json()["success"] is False
        assert "bad" in resp.json()["error"]


@pytest.mark.asyncio
async def test_autocomplete_empty(client: AsyncClient) -> None:
    resp = await client.post("/api/commands/autocomplete", json={"partial": ""})
    assert resp.status_code == 200
    suggestions = resp.json()["suggestions"]
    assert len(suggestions) == 2


@pytest.mark.asyncio
async def test_autocomplete_partial(client: AsyncClient) -> None:
    resp = await client.post("/api/commands/autocomplete", json={"partial": "he"})
    assert resp.status_code == 200
    assert "/help" in resp.json()["suggestions"]


@pytest.mark.asyncio
async def test_autocomplete_with_args(client: AsyncClient) -> None:
    resp = await client.post("/api/commands/autocomplete", json={"partial": "set foo"})
    assert resp.status_code == 200
    suggestions = resp.json()["suggestions"]
    assert len(suggestions) == 1  # usage hint


@pytest.mark.asyncio
async def test_autocomplete_unknown_command_with_args(client: AsyncClient) -> None:
    resp = await client.post("/api/commands/autocomplete", json={"partial": "zzz foo"})
    assert resp.status_code == 200
    assert resp.json()["suggestions"] == []


@pytest.mark.asyncio
async def test_autocomplete_alias(client: AsyncClient) -> None:
    resp = await client.post("/api/commands/autocomplete", json={"partial": "h"})
    assert resp.status_code == 200
    suggestions = resp.json()["suggestions"]
    assert "/help" in suggestions or "/h" in suggestions
