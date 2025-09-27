"""Test agent refresh functionality."""

import tempfile
from pathlib import Path
from unittest.mock import patch

from code_puppy.agents import get_available_agents, refresh_agents


def test_refresh_agents_function():
    """Test that refresh_agents clears the cache and rediscovers agents."""
    # First call to get_available_agents should populate the cache
    agents1 = get_available_agents()

    # Call refresh_agents
    refresh_agents()

    # Second call should work (this tests that the cache was properly cleared)
    agents2 = get_available_agents()

    # Should find the same agents (since we didn't add any new ones)
    assert agents1 == agents2
    assert len(agents1) > 0  # Should have at least the built-in agents


def test_get_available_agents():
    """Test that get_available_agents works correctly."""
    # Call get_available_agents
    agents = get_available_agents()

    # Should find agents
    assert len(agents) > 0


def test_json_agent_discovery_refresh():
    """Test that refresh picks up new JSON agents."""
    with tempfile.TemporaryDirectory() as temp_dir:
        with patch(
            "code_puppy.config.get_user_agents_directory", return_value=temp_dir
        ):
            # Get initial agents (should not include our test agent)
            initial_agents = get_available_agents()
            assert "test-agent" not in initial_agents

            # Create a test JSON agent file
            test_agent_config = {
                "name": "test-agent",
                "description": "A test agent for refresh functionality",
                "system_prompt": "You are a test agent.",
                "tools": ["list_files", "read_file"],
            }

            agent_file = Path(temp_dir) / "test-agent.json"
            import json

            with open(agent_file, "w") as f:
                json.dump(test_agent_config, f)

            # Refresh agents and check if the new agent is discovered
            refreshed_agents = get_available_agents()
            assert "test-agent" in refreshed_agents
            assert (
                refreshed_agents["test-agent"] == "Test-Agent 🤖"
            )  # Default display name format
