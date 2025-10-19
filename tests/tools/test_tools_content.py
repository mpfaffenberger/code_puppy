"""Tests for code_puppy.tools.tools_content.

This module tests the tools_content string constant that provides
user-facing documentation about Code Puppy's available tools.
"""

import pytest
import sys
from pathlib import Path

# Import directly from the module file to avoid heavy dependencies in __init__.py
import importlib.util

spec = importlib.util.spec_from_file_location(
    "tools_content_module",
    Path(__file__).parent.parent.parent / "code_puppy" / "tools" / "tools_content.py"
)
tools_content_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tools_content_module)
tools_content = tools_content_module.tools_content


class TestToolsContentBasic:
    """Test basic properties of tools_content string."""

    def test_tools_content_exists_and_is_string(self):
        """Test that tools_content exists and is a string."""
        assert isinstance(tools_content, str)

    def test_tools_content_is_not_empty(self):
        """Test that tools_content is not empty."""
        assert len(tools_content) > 0
        assert tools_content.strip() != ""

    def test_tools_content_has_reasonable_length(self):
        """Test that tools_content has substantial content (not just a placeholder)."""
        # Should be at least 500 characters for meaningful documentation
        assert len(tools_content) > 500, "tools_content seems too short for proper documentation"


class TestToolsContentToolNames:
    """Test that tools_content mentions all key tools."""

    def test_contains_file_operations_tools(self):
        """Test that all file operation tools are mentioned."""
        file_tools = [
            "list_files",
            "read_file",
            "edit_file",
            "delete_file",
        ]
        for tool in file_tools:
            assert tool in tools_content, f"Expected tool '{tool}' not found in tools_content"

    def test_contains_search_tools(self):
        """Test that search tools are mentioned."""
        assert "grep" in tools_content, "Expected 'grep' tool not found in tools_content"

    def test_contains_system_operation_tools(self):
        """Test that system operation tools are mentioned."""
        assert "agent_run_shell_command" in tools_content, "Expected 'agent_run_shell_command' not found"

    def test_contains_agent_communication_tools(self):
        """Test that agent communication tools are mentioned."""
        agent_tools = [
            "agent_share_your_reasoning",
        ]
        for tool in agent_tools:
            assert tool in tools_content, f"Expected agent tool '{tool}' not found in tools_content"


class TestToolsContentSections:
    """Test that tools_content has proper section organization."""

    def test_contains_file_operations_section(self):
        """Test that File Operations section header exists."""
        assert "File Operations" in tools_content, "Expected 'File Operations' section header"

    def test_contains_system_operations_section(self):
        """Test that System Operations section header exists."""
        assert "System Operations" in tools_content, "Expected 'System Operations' section header"

    def test_contains_agent_communication_section(self):
        """Test that Agent Communication section header exists."""
        assert "Agent Communication" in tools_content, "Expected 'Agent Communication' section header"

    def test_contains_search_section(self):
        """Test that Search & Analysis section header exists."""
        assert "Search" in tools_content, "Expected 'Search' section header"

    def test_contains_philosophy_section(self):
        """Test that Tool Usage Philosophy section exists."""
        assert "Philosophy" in tools_content, "Expected 'Philosophy' section"

    def test_contains_pro_tips_section(self):
        """Test that Pro Tips section exists."""
        assert "Pro Tips" in tools_content, "Expected 'Pro Tips' section"


class TestToolsContentPrinciples:
    """Test that tools_content mentions key software principles."""

    def test_mentions_dry_principle(self):
        """Test that DRY (Don't Repeat Yourself) is mentioned."""
        assert "DRY" in tools_content, "Expected 'DRY' principle to be mentioned"

    def test_mentions_yagni_principle(self):
        """Test that YAGNI (You Ain't Gonna Need It) is mentioned."""
        assert "YAGNI" in tools_content, "Expected 'YAGNI' principle to be mentioned"

    def test_mentions_solid_principle(self):
        """Test that SOLID principles are mentioned."""
        assert "SOLID" in tools_content, "Expected 'SOLID' principles to be mentioned"

    def test_mentions_file_size_guideline(self):
        """Test that the 600 line file size guideline is mentioned."""
        assert "600" in tools_content, "Expected '600 line' guideline to be mentioned"


class TestToolsContentFormatting:
    """Test that tools_content has proper formatting and emojis."""

    def test_contains_dog_emoji(self):
        """Test that the content contains dog emoji (brand consistency)."""
        assert "🐶" in tools_content, "Expected dog emoji 🐶 for brand consistency"

    def test_contains_markdown_headers(self):
        """Test that content uses markdown-style headers."""
        assert "#" in tools_content, "Expected markdown headers (#) in content"

    def test_contains_bullet_points(self):
        """Test that content uses bullet points for lists."""
        # Could be - or * for markdown bullets
        assert "-" in tools_content or "*" in tools_content, "Expected bullet points in content"


class TestToolsContentUsageGuidance:
    """Test that tools_content provides usage guidance."""

    def test_mentions_edit_file_preference(self):
        """Test that guidance mentions preference for targeted replacements."""
        # The content should guide users on best practices
        assert "replacement" in tools_content.lower() or "replace" in tools_content.lower(), \
            "Expected guidance on edit_file replacements"

    def test_mentions_reasoning_before_operations(self):
        """Test that guidance mentions using share_your_reasoning."""
        assert "reasoning" in tools_content.lower(), \
            "Expected guidance on sharing reasoning"

    def test_mentions_exploration_before_modification(self):
        """Test that guidance suggests exploring before modifying."""
        # Should mention exploring/listing files first
        assert "explore" in tools_content.lower() or "list" in tools_content.lower(), \
            "Expected guidance on exploring before modifying"
