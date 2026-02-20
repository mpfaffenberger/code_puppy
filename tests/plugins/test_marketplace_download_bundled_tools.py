"""Tests for bundled UC tools installation during agent download.

Tests the _install_bundled_uc_tools function that auto-extracts
Universal Constructor tools embedded in marketplace agent JSON.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from code_puppy.plugins.agent_marketplace.download import (
    _install_bundled_uc_tools,
)


@pytest.fixture
def uc_dir(tmp_path):
    """Create a temporary UC tools directory."""
    d = tmp_path / "plugins" / "universal_constructor"
    d.mkdir(parents=True)
    return d


class TestInstallBundledUCTools:
    """Tests for _install_bundled_uc_tools."""

    def test_returns_zero_when_no_bundled_tools(self):
        """Should return 0 when agent has no bundled_uc_tools key."""
        agent_data = {"name": "test-agent", "tools": ["read_file"]}
        assert _install_bundled_uc_tools(agent_data, "test-agent") == 0

    def test_returns_zero_when_bundled_tools_is_none(self):
        """Should return 0 when bundled_uc_tools is None."""
        agent_data = {"name": "test-agent", "bundled_uc_tools": None}
        assert _install_bundled_uc_tools(agent_data, "test-agent") == 0

    def test_returns_zero_when_bundled_tools_is_not_dict(self):
        """Should return 0 when bundled_uc_tools is not a dict."""
        agent_data = {"name": "test-agent", "bundled_uc_tools": "bad"}
        assert _install_bundled_uc_tools(agent_data, "test-agent") == 0

    def test_returns_zero_when_bundled_tools_is_empty(self):
        """Should return 0 when bundled_uc_tools is empty dict."""
        agent_data = {"name": "test-agent", "bundled_uc_tools": {}}
        assert _install_bundled_uc_tools(agent_data, "test-agent") == 0

    def test_installs_single_tool(self, uc_dir):
        """Should install a single bundled tool file."""
        tool_code = (
            "TOOL_META = {'name': 'helper', 'namespace': 'myns', "
            "'description': 'A helper', 'enabled': True}\n\n"
            "def run():\n    return 'hello'\n"
        )
        agent_data = {
            "name": "test-agent",
            "bundled_uc_tools": {"myns/helper.py": tool_code},
        }

        with patch(
            "code_puppy.plugins.universal_constructor.USER_UC_DIR", uc_dir
        ), patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry"
        ):
            result = _install_bundled_uc_tools(agent_data, "test-agent")

        assert result == 1
        installed = uc_dir / "myns" / "helper.py"
        assert installed.exists()
        assert installed.read_text() == tool_code

    def test_creates_init_py_in_namespace(self, uc_dir):
        """Should create __init__.py in namespace directories."""
        agent_data = {
            "name": "test-agent",
            "bundled_uc_tools": {
                "myns/tool.py": "TOOL_META = {}\ndef run(): pass\n"
            },
        }

        with patch(
            "code_puppy.plugins.universal_constructor.USER_UC_DIR", uc_dir
        ), patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry"
        ):
            _install_bundled_uc_tools(agent_data, "test-agent")

        init_file = uc_dir / "myns" / "__init__.py"
        assert init_file.exists()

    def test_installs_multiple_tools(self, uc_dir):
        """Should install multiple bundled tool files."""
        agent_data = {
            "name": "test-agent",
            "bundled_uc_tools": {
                "danny/ask.py": "TOOL_META = {}\ndef ask(): pass\n",
                "danny/auth.py": "TOOL_META = {}\ndef auth(): pass\n",
                "danny/list.py": "TOOL_META = {}\ndef list_agents(): pass\n",
            },
        }

        with patch(
            "code_puppy.plugins.universal_constructor.USER_UC_DIR", uc_dir
        ), patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry"
        ):
            result = _install_bundled_uc_tools(agent_data, "test-agent")

        assert result == 3
        assert (uc_dir / "danny" / "ask.py").exists()
        assert (uc_dir / "danny" / "auth.py").exists()
        assert (uc_dir / "danny" / "list.py").exists()

    def test_skips_non_python_files(self, uc_dir):
        """Should skip files that don't end in .py."""
        agent_data = {
            "name": "test-agent",
            "bundled_uc_tools": {
                "myns/readme.md": "# README",
                "myns/tool.py": "TOOL_META = {}\ndef run(): pass\n",
            },
        }

        with patch(
            "code_puppy.plugins.universal_constructor.USER_UC_DIR", uc_dir
        ), patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry"
        ):
            result = _install_bundled_uc_tools(agent_data, "test-agent")

        assert result == 1
        assert not (uc_dir / "myns" / "readme.md").exists()

    def test_skips_non_string_content(self, uc_dir):
        """Should skip entries where value is not a string."""
        agent_data = {
            "name": "test-agent",
            "bundled_uc_tools": {
                "myns/bad.py": 12345,
                "myns/good.py": "TOOL_META = {}\ndef run(): pass\n",
            },
        }

        with patch(
            "code_puppy.plugins.universal_constructor.USER_UC_DIR", uc_dir
        ), patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry"
        ):
            result = _install_bundled_uc_tools(agent_data, "test-agent")

        assert result == 1

    def test_rejects_path_traversal(self, uc_dir):
        """Should reject paths with .. to prevent directory traversal."""
        agent_data = {
            "name": "test-agent",
            "bundled_uc_tools": {
                "../evil.py": "import os; os.system('rm -rf /')\n",
                "myns/../../escape.py": "bad stuff\n",
            },
        }

        with patch(
            "code_puppy.plugins.universal_constructor.USER_UC_DIR", uc_dir
        ), patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry"
        ):
            result = _install_bundled_uc_tools(agent_data, "test-agent")

        assert result == 0

    def test_rejects_absolute_paths(self, uc_dir):
        """Should reject absolute file paths."""
        agent_data = {
            "name": "test-agent",
            "bundled_uc_tools": {
                "/etc/evil.py": "bad stuff\n",
            },
        }

        with patch(
            "code_puppy.plugins.universal_constructor.USER_UC_DIR", uc_dir
        ), patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry"
        ):
            result = _install_bundled_uc_tools(agent_data, "test-agent")

        assert result == 0

    def test_overwrites_existing_tool(self, uc_dir):
        """Should overwrite existing tool files with newer version."""
        # Create pre-existing tool
        ns_dir = uc_dir / "myns"
        ns_dir.mkdir(parents=True)
        existing = ns_dir / "tool.py"
        existing.write_text("# old version")

        new_code = "# new version\ndef run(): return 'updated'\n"
        agent_data = {
            "name": "test-agent",
            "bundled_uc_tools": {"myns/tool.py": new_code},
        }

        with patch(
            "code_puppy.plugins.universal_constructor.USER_UC_DIR", uc_dir
        ), patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry"
        ):
            result = _install_bundled_uc_tools(agent_data, "test-agent")

        assert result == 1
        assert existing.read_text() == new_code

    def test_reloads_uc_registry(self, uc_dir):
        """Should reload the UC registry after installing tools."""
        agent_data = {
            "name": "test-agent",
            "bundled_uc_tools": {
                "myns/tool.py": "TOOL_META = {}\ndef run(): pass\n"
            },
        }

        with patch(
            "code_puppy.plugins.universal_constructor.USER_UC_DIR", uc_dir
        ), patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry"
        ) as mock_get_registry:
            _install_bundled_uc_tools(agent_data, "test-agent")
            mock_get_registry.return_value.reload.assert_called_once()

    def test_does_not_reload_registry_when_nothing_installed(self):
        """Should not reload registry when no tools were installed."""
        agent_data = {"name": "test-agent", "bundled_uc_tools": {}}

        with patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry"
        ) as mock_get_registry:
            _install_bundled_uc_tools(agent_data, "test-agent")
            mock_get_registry.assert_not_called()
