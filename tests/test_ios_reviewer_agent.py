"""Test iOS reviewer agent functionality."""

from code_puppy.agents import get_available_agents, load_agent
from code_puppy.agents.agent_ios_reviewer import IOSReviewerAgent


def test_ios_reviewer_agent_exists():
    """Test that iOS reviewer agent is discoverable."""
    agents = get_available_agents()
    assert "ios-reviewer" in agents
    assert agents["ios-reviewer"] == "iOS Reviewer 🍎"


def test_ios_reviewer_agent_properties():
    """Test iOS reviewer agent basic properties."""
    agent = IOSReviewerAgent()

    assert agent.name == "ios-reviewer"
    assert agent.display_name == "iOS Reviewer 🍎"
    assert "iOS" in agent.description
    assert "Swift" in agent.description or "SwiftUI" in agent.description


def test_ios_reviewer_agent_tools():
    """Test iOS reviewer agent has correct read-only tools."""
    agent = IOSReviewerAgent()
    tools = agent.get_available_tools()

    # Reviewers should only have read-only tools
    assert "agent_share_your_reasoning" in tools
    assert "agent_run_shell_command" in tools
    assert "list_files" in tools
    assert "read_file" in tools
    assert "grep" in tools

    # Reviewers should NOT have write tools
    assert "edit_file" not in tools
    assert "delete_file" not in tools


def test_ios_reviewer_agent_system_prompt():
    """Test iOS reviewer agent has comprehensive system prompt."""
    agent = IOSReviewerAgent()
    prompt = agent.get_system_prompt()

    # Check for key iOS development concepts
    assert "Swift" in prompt or "iOS" in prompt
    assert "SwiftUI" in prompt or "UIKit" in prompt

    # Architecture patterns
    assert "MVVM" in prompt or "VIPER" in prompt or "Coordinator" in prompt

    # Modern iOS features
    assert "async/await" in prompt or "async" in prompt
    assert "Combine" in prompt

    # Memory management
    assert "ARC" in prompt or "retain cycle" in prompt

    # Accessibility
    assert "VoiceOver" in prompt or "accessibility" in prompt
    assert "Dynamic Type" in prompt

    # Security
    assert "Keychain" in prompt
    assert "biometric" in prompt or "Face ID" in prompt or "Touch ID" in prompt

    # Testing
    assert "XCTest" in prompt or "XCUITest" in prompt

    # Performance
    assert "Core Data" in prompt
    assert "performance" in prompt or "memory" in prompt


def test_ios_reviewer_agent_can_be_loaded():
    """Test that iOS reviewer agent can be loaded via agent manager."""
    agent = load_agent("ios-reviewer")

    assert agent is not None
    assert agent.name == "ios-reviewer"
    assert isinstance(agent, IOSReviewerAgent)


def test_ios_reviewer_agent_prompt_structure():
    """Test iOS reviewer agent prompt has proper structure and guidance."""
    agent = IOSReviewerAgent()
    prompt = agent.get_system_prompt()

    # Should have review methodology
    assert "review" in prompt.lower()
    assert "feedback" in prompt.lower() or "findings" in prompt.lower()

    # Should have severity levels or prioritization
    assert (
        "severity" in prompt.lower()
        or "blocker" in prompt.lower()
        or "critical" in prompt.lower()
    )

    # Should have iOS-specific anti-patterns
    assert "retain cycle" in prompt.lower() or "force unwrap" in prompt.lower()
    assert "main thread" in prompt.lower() or "mainactor" in prompt.lower()
