"""Tests for edit_file → create_file/replace_in_file/delete_snippet expansion."""

import json
import os
import tempfile


class TestToolExpansion:
    """Test that edit_file expands into three individual tools."""

    def test_tool_expansions_dict_exists(self):
        """TOOL_EXPANSIONS maps edit_file to three tools."""
        from code_puppy.tools import TOOL_EXPANSIONS

        assert "edit_file" in TOOL_EXPANSIONS
        assert set(TOOL_EXPANSIONS["edit_file"]) == {
            "create_file",
            "replace_in_file",
            "delete_snippet",
        }

    def test_new_tools_in_registry(self):
        """All three new tools are in TOOL_REGISTRY."""
        from code_puppy.tools import TOOL_REGISTRY

        assert "create_file" in TOOL_REGISTRY
        assert "replace_in_file" in TOOL_REGISTRY
        assert "delete_snippet" in TOOL_REGISTRY

    def test_edit_file_still_in_registry(self):
        """edit_file remains in registry for direct use."""
        from code_puppy.tools import TOOL_REGISTRY

        assert "edit_file" in TOOL_REGISTRY

    def test_expansion_deduplication(self):
        """If agent lists both edit_file and create_file, no double registration."""
        from code_puppy.tools import TOOL_EXPANSIONS

        tool_names = ["edit_file", "create_file", "read_file"]

        # Simulate the expansion logic from register_tools_for_agent
        expanded_tools: list[str] = []
        seen: set[str] = set()
        for tool_name in tool_names:
            if tool_name in TOOL_EXPANSIONS:
                for expanded in TOOL_EXPANSIONS[tool_name]:
                    if expanded not in seen:
                        expanded_tools.append(expanded)
                        seen.add(expanded)
            else:
                if tool_name not in seen:
                    expanded_tools.append(tool_name)
                    seen.add(tool_name)

        assert expanded_tools.count("create_file") == 1
        assert "replace_in_file" in expanded_tools
        assert "delete_snippet" in expanded_tools
        assert "read_file" in expanded_tools
        assert "edit_file" not in expanded_tools  # expanded away

    def test_expansion_preserves_order(self):
        """Expansion inserts new tools at the position of the original."""
        from code_puppy.tools import TOOL_EXPANSIONS

        tool_names = ["list_files", "edit_file", "delete_file"]

        expanded_tools: list[str] = []
        seen: set[str] = set()
        for tool_name in tool_names:
            if tool_name in TOOL_EXPANSIONS:
                for expanded in TOOL_EXPANSIONS[tool_name]:
                    if expanded not in seen:
                        expanded_tools.append(expanded)
                        seen.add(expanded)
            else:
                if tool_name not in seen:
                    expanded_tools.append(tool_name)
                    seen.add(tool_name)

        # list_files should still be first, delete_file last
        assert expanded_tools[0] == "list_files"
        assert expanded_tools[-1] == "delete_file"
        # The three new tools should be in the middle
        middle = expanded_tools[1:-1]
        assert set(middle) == {"create_file", "replace_in_file", "delete_snippet"}

    def test_non_expanded_tools_pass_through(self):
        """Tools not in TOOL_EXPANSIONS are unaffected."""
        from code_puppy.tools import TOOL_EXPANSIONS

        tool_names = ["list_files", "grep", "agent_run_shell_command"]

        expanded_tools: list[str] = []
        seen: set[str] = set()
        for tool_name in tool_names:
            if tool_name in TOOL_EXPANSIONS:
                for expanded in TOOL_EXPANSIONS[tool_name]:
                    if expanded not in seen:
                        expanded_tools.append(expanded)
                        seen.add(expanded)
            else:
                if tool_name not in seen:
                    expanded_tools.append(tool_name)
                    seen.add(tool_name)

        assert expanded_tools == tool_names

    def test_json_agent_edit_file_in_config(self):
        """JSON agent with edit_file in config returns it from get_available_tools.

        Expansion happens in register_tools_for_agent, not in get_available_tools.
        """
        from code_puppy.agents.json_agent import JSONAgent

        config = {
            "name": "test-agent",
            "description": "Test",
            "system_prompt": "You are a test agent.",
            "tools": ["list_files", "read_file", "edit_file"],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config, f)
            tmp_path = f.name

        try:
            agent = JSONAgent(tmp_path)
            tools = agent.get_available_tools()
            # edit_file should still be returned by get_available_tools
            # (expansion happens in register_tools_for_agent, not here)
            assert "edit_file" in tools
        finally:
            os.unlink(tmp_path)


class TestNewToolRegistration:
    """Test that each new tool registration function exists and is callable."""

    def test_register_create_file_exists(self):
        from code_puppy.tools.file_modifications import register_create_file

        assert callable(register_create_file)

    def test_register_replace_in_file_exists(self):
        from code_puppy.tools.file_modifications import register_replace_in_file

        assert callable(register_replace_in_file)

    def test_register_delete_snippet_exists(self):
        from code_puppy.tools.file_modifications import register_delete_snippet

        assert callable(register_delete_snippet)

    def test_registry_functions_match_imports(self):
        """TOOL_REGISTRY entries point to the correct functions."""
        from code_puppy.tools import TOOL_REGISTRY
        from code_puppy.tools.file_modifications import (
            register_create_file,
            register_delete_snippet,
            register_replace_in_file,
        )

        assert TOOL_REGISTRY["create_file"] is register_create_file
        assert TOOL_REGISTRY["replace_in_file"] is register_replace_in_file
        assert TOOL_REGISTRY["delete_snippet"] is register_delete_snippet
