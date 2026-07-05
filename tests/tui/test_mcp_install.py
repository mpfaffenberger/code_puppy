"""Phase 3 Wave B: /mcp install flow (catalog browse + per-server form + custom)."""

import json

import pytest
from textual.widgets import OptionList

from code_puppy.tui.app import build_app
from code_puppy.tui.screens.base import FilterableListScreen
from code_puppy.tui.screens.form import FormScreen


class _FakeServer:
    def __init__(self, id, name, display_name, env=None, args=None, verified=False):
        self.id = id
        self.name = name
        self.display_name = display_name
        self.verified = verified
        self.description = ""
        self._env = env or []
        self._args = args or []

    def get_environment_vars(self):
        return self._env

    def get_command_line_args(self):
        return self._args


class _FakeCatalog:
    def __init__(self, servers):
        self.servers = servers

    def get_by_id(self, sid):
        return next((s for s in self.servers if s.id == sid), None)

    def search(self, query):
        q = query.lower()
        return [s for s in self.servers if q in s.name.lower()]


def _patch_catalog(monkeypatch, servers):
    monkeypatch.setattr(
        "code_puppy.mcp_.server_registry_catalog.catalog", _FakeCatalog(servers)
    )


@pytest.mark.asyncio
async def test_mcp_install_opens_browser(monkeypatch):
    _patch_catalog(monkeypatch, [_FakeServer("fs", "filesystem", "Filesystem")])
    app = build_app()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        app.submit_prompt("/mcp install")
        await pilot.pause(0.2)
        assert isinstance(app.screen, FilterableListScreen)
        items = app.screen.query_one("#items", OptionList)
        assert items.option_count >= 2  # custom entry + 1 catalog server


@pytest.mark.asyncio
async def test_mcp_install_custom_opens_form(monkeypatch):
    _patch_catalog(monkeypatch, [_FakeServer("fs", "filesystem", "Filesystem")])
    app = build_app()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        app.submit_prompt("/mcp install")
        await pilot.pause(0.2)
        await pilot.press(*"custom")
        await pilot.pause(0.1)
        await pilot.press("enter")
        await pilot.pause(0.1)
        assert isinstance(app.screen, FormScreen)


@pytest.mark.asyncio
async def test_mcp_install_catalog_form_has_env_field(monkeypatch):
    server = _FakeServer(
        "gh",
        "github",
        "GitHub",
        env=["GITHUB_TOKEN"],
        args=[{"name": "repo", "prompt": "Repo", "required": True}],
    )
    _patch_catalog(monkeypatch, [server])
    app = build_app()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        app.submit_prompt("/mcp install gh")
        await pilot.pause(0.2)
        assert isinstance(app.screen, FormScreen)
        # name + env_0 + arg_0 fields exist
        app.screen.query_one("#field-name")
        app.screen.query_one("#field-env_0")
        app.screen.query_one("#field-arg_0")


def test_save_custom_stdio_server(monkeypatch, tmp_path):
    mcp_file = tmp_path / "mcp_servers.json"
    monkeypatch.setattr("code_puppy.config.MCP_SERVERS_FILE", str(mcp_file))

    class _FakeManager:
        def register_server(self, cfg):
            return "id-1"

    monkeypatch.setattr(
        "code_puppy.mcp_.manager.get_mcp_manager", lambda: _FakeManager()
    )

    from code_puppy.tui.mcp_install import _save_custom_server

    _save_custom_server(
        {
            "name": "myserver",
            "type": "stdio",
            "command": "npx -y @scope/server",
            "args": "--flag",
            "url": "",
            "auth": "",
        }
    )
    data = json.loads(mcp_file.read_text())
    assert "myserver" in data["mcp_servers"]
    entry = data["mcp_servers"]["myserver"]
    assert entry["type"] == "stdio"
    assert entry["command"] == "npx"
    assert entry["args"] == ["-y", "@scope/server", "--flag"]


def test_save_custom_http_requires_url(monkeypatch):
    errors = []
    monkeypatch.setattr(
        "code_puppy.messaging.emit_error", lambda msg, *a, **k: errors.append(msg)
    )
    from code_puppy.tui.mcp_install import _save_custom_server

    _save_custom_server(
        {"name": "x", "type": "http", "command": "", "args": "", "url": "", "auth": ""}
    )
    assert errors and "URL" in errors[0]
