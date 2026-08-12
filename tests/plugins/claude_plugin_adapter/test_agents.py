import json

from code_puppy.plugins.claude_plugin_adapter.adapters.agents import sync_agents_adapter


def test_sync_agents_adapter(monkeypatch, tmp_path):
    mock_plugin_dir = tmp_path / "claude_plugins"
    plugin_name = "test-plugin"
    plugin_path = mock_plugin_dir / plugin_name
    plugin_agents_dir = plugin_path / "agents"
    plugin_agents_dir.mkdir(parents=True)

    mock_user_agents_dir = tmp_path / "agents"
    mock_user_agents_dir.mkdir()

    # Create an existing user agent
    user_agent = {"name": "user_agent", "system_prompt": "Hello", "tools": []}
    with open(mock_user_agents_dir / "user_agent.json", "w") as f:
        json.dump(user_agent, f)

    # Create an existing managed agent (should be removed)
    old_managed_agent = {
        "_managed_by": "claude_plugin_adapter:test-plugin",
        "name": "old_agent",
        "system_prompt": "Old",
        "tools": [],
    }
    with open(mock_user_agents_dir / "old_agent.json", "w") as f:
        json.dump(old_managed_agent, f)

    # Create a plugin agent markdown
    agent_md = """---
name: new_agent
description: A test agent
tools:
  - Bash
  - Glob
model: claude-3-5-sonnet-20241022
---
This is the body of the agent prompt.
"""
    with open(plugin_agents_dir / "new_agent.md", "w") as f:
        f.write(agent_md)

    # Create a plugin agent with no tools
    agent_no_tools_md = """---
name: new_agent_2
description: Another test agent
---
Body 2
"""
    with open(plugin_agents_dir / "new_agent_2.md", "w") as f:
        f.write(agent_no_tools_md)

    monkeypatch.setattr(
        "code_puppy.plugins.claude_plugin_adapter.adapters.agents.get_claude_plugins_dir",
        lambda: mock_plugin_dir,
    )
    monkeypatch.setattr(
        "code_puppy.plugins.claude_plugin_adapter.adapters.agents.get_user_agents_directory",
        lambda: str(mock_user_agents_dir),
    )

    # 1. Install sync
    sync_agents_adapter(plugin_name)

    # Assert old managed is gone
    assert not (mock_user_agents_dir / "old_agent.json").exists()

    # Assert user agent is still there
    assert (mock_user_agents_dir / "user_agent.json").exists()

    # Assert new agents are there
    assert (mock_user_agents_dir / "new_agent.json").exists()
    assert (mock_user_agents_dir / "new_agent_2.json").exists()

    with open(mock_user_agents_dir / "new_agent.json") as f:
        data = json.load(f)

    assert data["name"] == "new_agent"
    assert data["description"] == "A test agent"
    assert data["system_prompt"] == "This is the body of the agent prompt."
    assert data["_managed_by"] == "claude_plugin_adapter:test-plugin"
    assert "model" not in data
    # Test tool mapping
    assert "agent_run_shell_command" in data["tools"]
    assert "list_files" in data["tools"]

    with open(mock_user_agents_dir / "new_agent_2.json") as f:
        data2 = json.load(f)

    # Sensible default set
    assert "agent_run_shell_command" in data2["tools"]
    assert "read_file" in data2["tools"]

    # 3. Uninstall sync
    sync_agents_adapter(plugin_name, uninstall=True)

    # Assert new agents are gone
    assert not (mock_user_agents_dir / "new_agent.json").exists()
    assert not (mock_user_agents_dir / "new_agent_2.json").exists()
    # Assert user agent is still there
    assert (mock_user_agents_dir / "user_agent.json").exists()
