"""Tests for agent adapter — discovery and metadata helpers."""

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.plugins.acp_gateway.agent_adapter import (
    AgentInfo,
    build_agent_metadata,
    discover_agents,
)


# ---------------------------------------------------------------------------
# Helper: inject a fake ``code_puppy.agents`` module so that inline
# imports inside ``discover_agents`` / ``build_agent_metadata`` resolve
# without dragging in the real (heavy) agent machinery.
# ---------------------------------------------------------------------------

def _make_agents_module(
    agents_map: dict | None = None,
    descriptions_map: dict | None = None,
) -> ModuleType:
    mod = ModuleType("code_puppy.agents")
    mod.get_available_agents = MagicMock(return_value=agents_map or {})  # type: ignore[attr-defined]
    mod.get_agent_descriptions = MagicMock(return_value=descriptions_map or {})  # type: ignore[attr-defined]
    return mod


@pytest.fixture()
def _fake_agents():
    """Ensure ``code_puppy.agents`` exists in sys.modules for patching."""
    mod = _make_agents_module()
    with patch.dict(sys.modules, {"code_puppy.agents": mod}):
        yield mod


# ---------------------------------------------------------------------------
# discover_agents (async)
# ---------------------------------------------------------------------------

class TestDiscoverAgents:
    """Test dynamic agent discovery."""

    @pytest.mark.asyncio
    async def test_returns_agent_info_list(self, _fake_agents):
        _fake_agents.get_available_agents.return_value = {
            "code-puppy": "Code Puppy",
            "wibey": "Wibey",
        }
        _fake_agents.get_agent_descriptions.return_value = {
            "code-puppy": "The main agent",
            "wibey": "A wise agent",
        }

        agents = await discover_agents()

        assert len(agents) == 2
        names = {a.name for a in agents}
        assert names == {"code-puppy", "wibey"}

        cp = next(a for a in agents if a.name == "code-puppy")
        assert cp.display_name == "Code Puppy"
        assert cp.description == "The main agent"

    @pytest.mark.asyncio
    async def test_missing_description_uses_fallback(self, _fake_agents):
        _fake_agents.get_available_agents.return_value = {
            "code-puppy": "Code Puppy",
        }
        _fake_agents.get_agent_descriptions.return_value = {}  # empty

        agents = await discover_agents()

        assert len(agents) == 1
        assert agents[0].description == "No description available."

    @pytest.mark.asyncio
    async def test_empty_agent_registry(self, _fake_agents):
        agents = await discover_agents()
        assert agents == []

    @pytest.mark.asyncio
    async def test_import_error_returns_empty(self):
        """When code_puppy.agents can't be imported at all."""
        # Remove module from sys.modules so the import fails.
        with patch.dict(
            sys.modules,
            {"code_puppy.agents": None},  # type: ignore[dict-item]
        ):
            agents = await discover_agents()
            assert agents == []

    @pytest.mark.asyncio
    async def test_runtime_error_returns_empty(self, _fake_agents):
        _fake_agents.get_available_agents.side_effect = RuntimeError("boom")
        agents = await discover_agents()
        assert agents == []


# ---------------------------------------------------------------------------
# build_agent_metadata
# ---------------------------------------------------------------------------

class TestBuildAgentMetadata:
    """Test single-agent metadata builder."""

    def test_returns_correct_dict(self, _fake_agents):
        _fake_agents.get_available_agents.return_value = {
            "code-puppy": "Code Puppy",
        }
        _fake_agents.get_agent_descriptions.return_value = {
            "code-puppy": "The main agent",
        }

        meta = build_agent_metadata("code-puppy")

        assert meta == {
            "name": "code-puppy",
            "display_name": "Code Puppy",
            "description": "The main agent",
            "version": "0.1.0",
        }

    def test_unknown_agent_returns_none(self, _fake_agents):
        """Unknown agents are not in the registry — build_agent_metadata returns None."""
        meta = build_agent_metadata("unknown-agent")
        assert meta is None

    def test_error_returns_graceful_fallback(self, _fake_agents):
        _fake_agents.get_available_agents.side_effect = RuntimeError("boom")

        meta = build_agent_metadata("code-puppy")

        assert meta["name"] == "code-puppy"
        assert meta["display_name"] == "code-puppy"
        assert meta["version"] == "0.1.0"


# ---------------------------------------------------------------------------
# AgentInfo
# ---------------------------------------------------------------------------

class TestAgentInfoImmutability:
    """Test AgentInfo frozen dataclass."""

    def test_frozen(self):
        info = AgentInfo(name="a", display_name="A", description="desc")
        with pytest.raises(AttributeError):
            info.name = "b"  # type: ignore[misc]

    def test_equality(self):
        a = AgentInfo(name="x", display_name="X", description="d")
        b = AgentInfo(name="x", display_name="X", description="d")
        assert a == b