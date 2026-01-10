"""Tests for the Pack agents - workflow orchestration system.

The Pack consists of:
- Pack Leader: Main orchestrator for parallel workflows
- Bloodhound: Issue tracking specialist (bd + gh issues)
- Terrier: Worktree management (git worktree)
- Retriever: PR lifecycle (gh pr)
- Husky: Task execution in worktrees
"""

import pytest

from code_puppy.agents.base_agent import BaseAgent

# =============================================================================
# Import Tests
# =============================================================================


class TestPackImports:
    """Test that all pack agents can be imported."""

    def test_import_pack_leader(self):
        """Test Pack Leader agent can be imported."""
        from code_puppy.agents.agent_pack_leader import PackLeaderAgent

        assert PackLeaderAgent is not None

    def test_import_bloodhound(self):
        """Test Bloodhound agent can be imported."""
        from code_puppy.agents.pack.bloodhound import BloodhoundAgent

        assert BloodhoundAgent is not None

    def test_import_terrier(self):
        """Test Terrier agent can be imported."""
        from code_puppy.agents.pack.terrier import TerrierAgent

        assert TerrierAgent is not None

    def test_import_retriever(self):
        """Test Retriever agent can be imported."""
        from code_puppy.agents.pack.retriever import RetrieverAgent

        assert RetrieverAgent is not None

    def test_import_husky(self):
        """Test Husky agent can be imported."""
        from code_puppy.agents.pack.husky import HuskyAgent

        assert HuskyAgent is not None

    def test_import_from_pack_init(self):
        """Test all pack agents can be imported from pack __init__."""
        from code_puppy.agents.pack import (
            BloodhoundAgent,
            HuskyAgent,
            RetrieverAgent,
            TerrierAgent,
        )

        assert BloodhoundAgent is not None
        assert TerrierAgent is not None
        assert RetrieverAgent is not None
        assert HuskyAgent is not None


# =============================================================================
# Pack Leader Tests
# =============================================================================


class TestPackLeaderAgent:
    """Test Pack Leader agent properties and configuration."""

    @pytest.fixture
    def agent(self):
        """Create a Pack Leader agent instance."""
        from code_puppy.agents.agent_pack_leader import PackLeaderAgent

        return PackLeaderAgent()

    def test_inherits_base_agent(self, agent):
        """Test Pack Leader inherits from BaseAgent."""
        assert isinstance(agent, BaseAgent)

    def test_name(self, agent):
        """Test Pack Leader has correct name."""
        assert agent.name == "pack-leader"

    def test_display_name(self, agent):
        """Test Pack Leader has correct display name."""
        assert agent.display_name == "Pack Leader 🐺"

    def test_description(self, agent):
        """Test Pack Leader has a description."""
        assert agent.description is not None
        assert len(agent.description) > 0
        assert "orchestrat" in agent.description.lower()

    def test_tools_include_exploration(self, agent):
        """Test Pack Leader has exploration tools."""
        tools = agent.get_available_tools()
        assert "list_files" in tools
        assert "read_file" in tools
        assert "grep" in tools

    def test_tools_include_shell(self, agent):
        """Test Pack Leader has shell command tool for bd/gh."""
        tools = agent.get_available_tools()
        assert "agent_run_shell_command" in tools

    def test_tools_include_reasoning(self, agent):
        """Test Pack Leader has reasoning tool."""
        tools = agent.get_available_tools()
        assert "agent_share_your_reasoning" in tools

    def test_tools_include_agent_coordination(self, agent):
        """Test Pack Leader has agent coordination tools."""
        tools = agent.get_available_tools()
        assert "list_agents" in tools
        assert "invoke_agent" in tools

    def test_system_prompt_mentions_pack(self, agent):
        """Test Pack Leader system prompt mentions the pack."""
        prompt = agent.get_system_prompt()
        assert "pack" in prompt.lower()
        assert "bloodhound" in prompt.lower()
        assert "terrier" in prompt.lower()
        assert "retriever" in prompt.lower()
        assert "husky" in prompt.lower()

    def test_system_prompt_mentions_bd(self, agent):
        """Test Pack Leader system prompt mentions bd CLI."""
        prompt = agent.get_system_prompt()
        assert "bd" in prompt
        assert "bd ready" in prompt
        assert "bd create" in prompt

    def test_system_prompt_mentions_gh(self, agent):
        """Test Pack Leader system prompt mentions gh CLI."""
        prompt = agent.get_system_prompt()
        assert "gh" in prompt
        assert "gh pr" in prompt or "gh issue" in prompt


# =============================================================================
# Bloodhound Tests
# =============================================================================


class TestBloodhoundAgent:
    """Test Bloodhound agent properties and configuration."""

    @pytest.fixture
    def agent(self):
        """Create a Bloodhound agent instance."""
        from code_puppy.agents.pack.bloodhound import BloodhoundAgent

        return BloodhoundAgent()

    def test_inherits_base_agent(self, agent):
        """Test Bloodhound inherits from BaseAgent."""
        assert isinstance(agent, BaseAgent)

    def test_name(self, agent):
        """Test Bloodhound has correct name."""
        assert agent.name == "bloodhound"

    def test_display_name(self, agent):
        """Test Bloodhound has correct display name."""
        assert "Bloodhound" in agent.display_name

    def test_description_mentions_issue_tracking(self, agent):
        """Test Bloodhound description mentions issue tracking."""
        desc = agent.description.lower()
        assert "issue" in desc or "track" in desc

    def test_tools_include_shell(self, agent):
        """Test Bloodhound has shell command tool for bd/gh."""
        tools = agent.get_available_tools()
        assert "agent_run_shell_command" in tools

    def test_tools_include_reasoning(self, agent):
        """Test Bloodhound has reasoning tool."""
        tools = agent.get_available_tools()
        assert "agent_share_your_reasoning" in tools

    def test_system_prompt_not_empty(self, agent):
        """Test Bloodhound has a system prompt."""
        prompt = agent.get_system_prompt()
        assert prompt is not None
        assert len(prompt) > 0


# =============================================================================
# Terrier Tests
# =============================================================================


class TestTerrierAgent:
    """Test Terrier agent properties and configuration."""

    @pytest.fixture
    def agent(self):
        """Create a Terrier agent instance."""
        from code_puppy.agents.pack.terrier import TerrierAgent

        return TerrierAgent()

    def test_inherits_base_agent(self, agent):
        """Test Terrier inherits from BaseAgent."""
        assert isinstance(agent, BaseAgent)

    def test_name(self, agent):
        """Test Terrier has correct name."""
        assert agent.name == "terrier"

    def test_display_name(self, agent):
        """Test Terrier has correct display name."""
        assert "Terrier" in agent.display_name

    def test_description_mentions_worktree(self, agent):
        """Test Terrier description mentions worktree."""
        desc = agent.description.lower()
        assert "worktree" in desc

    def test_tools_include_shell(self, agent):
        """Test Terrier has shell command tool for git worktree."""
        tools = agent.get_available_tools()
        assert "agent_run_shell_command" in tools

    def test_tools_include_reasoning(self, agent):
        """Test Terrier has reasoning tool."""
        tools = agent.get_available_tools()
        assert "agent_share_your_reasoning" in tools

    def test_system_prompt_not_empty(self, agent):
        """Test Terrier has a system prompt."""
        prompt = agent.get_system_prompt()
        assert prompt is not None
        assert len(prompt) > 0


# =============================================================================
# Retriever Tests
# =============================================================================


class TestRetrieverAgent:
    """Test Retriever agent properties and configuration."""

    @pytest.fixture
    def agent(self):
        """Create a Retriever agent instance."""
        from code_puppy.agents.pack.retriever import RetrieverAgent

        return RetrieverAgent()

    def test_inherits_base_agent(self, agent):
        """Test Retriever inherits from BaseAgent."""
        assert isinstance(agent, BaseAgent)

    def test_name(self, agent):
        """Test Retriever has correct name."""
        assert agent.name == "retriever"

    def test_display_name(self, agent):
        """Test Retriever has correct display name."""
        assert "Retriever" in agent.display_name

    def test_description_mentions_pr(self, agent):
        """Test Retriever description mentions PR."""
        desc = agent.description.lower()
        assert "pr" in desc or "pull request" in desc

    def test_tools_include_shell(self, agent):
        """Test Retriever has shell command tool for gh pr."""
        tools = agent.get_available_tools()
        assert "agent_run_shell_command" in tools

    def test_tools_include_reasoning(self, agent):
        """Test Retriever has reasoning tool."""
        tools = agent.get_available_tools()
        assert "agent_share_your_reasoning" in tools

    def test_system_prompt_not_empty(self, agent):
        """Test Retriever has a system prompt."""
        prompt = agent.get_system_prompt()
        assert prompt is not None
        assert len(prompt) > 0


# =============================================================================
# Husky Tests
# =============================================================================


class TestHuskyAgent:
    """Test Husky agent properties and configuration."""

    @pytest.fixture
    def agent(self):
        """Create a Husky agent instance."""
        from code_puppy.agents.pack.husky import HuskyAgent

        return HuskyAgent()

    def test_inherits_base_agent(self, agent):
        """Test Husky inherits from BaseAgent."""
        assert isinstance(agent, BaseAgent)

    def test_name(self, agent):
        """Test Husky has correct name."""
        assert agent.name == "husky"

    def test_display_name(self, agent):
        """Test Husky has correct display name."""
        assert "Husky" in agent.display_name

    def test_description_mentions_task_execution(self, agent):
        """Test Husky description mentions task execution."""
        desc = agent.description.lower()
        assert "task" in desc or "execut" in desc or "work" in desc

    def test_tools_include_file_operations(self, agent):
        """Test Husky has file operation tools for coding work."""
        tools = agent.get_available_tools()
        # Husky needs to do actual coding work
        assert "edit_file" in tools or "agent_run_shell_command" in tools

    def test_tools_include_reasoning(self, agent):
        """Test Husky has reasoning tool."""
        tools = agent.get_available_tools()
        assert "agent_share_your_reasoning" in tools

    def test_system_prompt_not_empty(self, agent):
        """Test Husky has a system prompt."""
        prompt = agent.get_system_prompt()
        assert prompt is not None
        assert len(prompt) > 0


# =============================================================================
# Discovery Tests
# =============================================================================


class TestPackDiscovery:
    """Test that pack agents are discoverable via agent_manager."""

    def test_pack_leader_discoverable(self):
        """Test Pack Leader is discoverable."""
        from code_puppy.agents import get_available_agents

        agents = get_available_agents()
        assert "pack-leader" in agents

    def test_bloodhound_discoverable(self):
        """Test Bloodhound is discoverable."""
        from code_puppy.agents import get_available_agents

        agents = get_available_agents()
        assert "bloodhound" in agents

    def test_terrier_discoverable(self):
        """Test Terrier is discoverable."""
        from code_puppy.agents import get_available_agents

        agents = get_available_agents()
        assert "terrier" in agents

    def test_retriever_discoverable(self):
        """Test Retriever is discoverable."""
        from code_puppy.agents import get_available_agents

        agents = get_available_agents()
        assert "retriever" in agents

    def test_husky_discoverable(self):
        """Test Husky is discoverable."""
        from code_puppy.agents import get_available_agents

        agents = get_available_agents()
        assert "husky" in agents

    def test_all_pack_agents_discoverable(self):
        """Test all pack agents are discoverable in one check."""
        from code_puppy.agents import get_available_agents

        agents = get_available_agents()
        pack_agents = ["pack-leader", "bloodhound", "terrier", "retriever", "husky"]

        for agent_name in pack_agents:
            assert agent_name in agents, f"{agent_name} not found in available agents"

    def test_pack_agents_loadable(self):
        """Test all pack agents can be loaded via load_agent."""
        from code_puppy.agents import load_agent

        pack_agents = ["pack-leader", "bloodhound", "terrier", "retriever", "husky"]

        for agent_name in pack_agents:
            agent = load_agent(agent_name)
            assert agent is not None
            assert agent.name == agent_name
            assert isinstance(agent, BaseAgent)

    def test_pack_agents_have_display_names(self):
        """Test all pack agents have display names with emojis."""
        from code_puppy.agents import get_available_agents

        agents = get_available_agents()
        pack_agents = ["pack-leader", "bloodhound", "terrier", "retriever", "husky"]

        for agent_name in pack_agents:
            display_name = agents[agent_name]
            assert display_name is not None
            assert len(display_name) > 0
            # Display names should be more than just the agent name
            assert display_name != agent_name


# =============================================================================
# Integration Tests
# =============================================================================


class TestPackIntegration:
    """Test pack agents work together correctly."""

    def test_pack_leader_can_reference_pack_members(self):
        """Test Pack Leader's prompt references all pack members."""
        from code_puppy.agents.agent_pack_leader import PackLeaderAgent

        agent = PackLeaderAgent()
        prompt = agent.get_system_prompt().lower()

        # Pack Leader should know about all pack members
        assert "bloodhound" in prompt
        assert "terrier" in prompt
        assert "retriever" in prompt
        assert "husky" in prompt

    def test_all_pack_agents_have_unique_names(self):
        """Test all pack agents have unique names."""
        from code_puppy.agents import get_available_agents

        agents = get_available_agents()
        pack_agents = ["pack-leader", "bloodhound", "terrier", "retriever", "husky"]

        # All should be unique (no duplicates in list)
        assert len(pack_agents) == len(set(pack_agents))

        # All should exist
        for agent_name in pack_agents:
            assert agent_name in agents

    def test_pack_agents_tool_consistency(self):
        """Test pack agents have consistent tool availability."""
        from code_puppy.agents import load_agent

        pack_agents = ["pack-leader", "bloodhound", "terrier", "retriever", "husky"]

        for agent_name in pack_agents:
            agent = load_agent(agent_name)
            tools = agent.get_available_tools()

            # All pack agents should have reasoning capability
            assert "agent_share_your_reasoning" in tools, (
                f"{agent_name} missing reasoning tool"
            )

            # All pack agents should be able to run shell commands
            # (for bd, gh, git operations)
            assert "agent_run_shell_command" in tools, (
                f"{agent_name} missing shell command tool"
            )
