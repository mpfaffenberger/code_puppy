import os
from code_puppy.agents.json_agent import JSONAgent


def test_agent_orchestrator_loads_with_new_tools():
    """Test that our agent orchestrator loads correctly and has access to list_agents and invoke_agent tools."""
    # Get path to the agent orchestrator JSON file
    agents_dir = os.path.join(os.path.dirname(__file__), "..", "code_puppy", "agents")
    orchestrator_path = os.path.join(agents_dir, "agent_orchestrator.json")

    # Verify file exists
    assert os.path.exists(orchestrator_path), (
        f"Agent orchestrator file not found at {orchestrator_path}"
    )

    # Load agent
    agent = JSONAgent(orchestrator_path)

    # Verify properties
    assert agent.name == "agent-orchestrator"
    assert agent.display_name == "Agent Orchestrator 🎭"
    assert (
        agent.description
        == "Coordinates and manages various specialized agents to accomplish tasks"
    )

    # Verify tools are available
    available_tools = agent.get_available_tools()
    assert "list_agents" in available_tools
    assert "invoke_agent" in available_tools
    assert "agent_share_your_reasoning" in available_tools

    # Test passed if no exception was raised
    assert True
