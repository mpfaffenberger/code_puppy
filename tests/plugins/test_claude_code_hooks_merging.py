"""
Tests for the new hook merging behavior in claude_code_hooks.

Tests that verify global and project-level hooks are merged correctly
when both configuration files exist.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch


class TestHookMerging:
    """Test merging of global and project-level hook configurations."""

    def test_merges_different_event_types(self):
        """Global and project hooks with different event types should both be present."""
        from code_puppy.plugins.claude_code_hooks.config import load_hooks_config

        project_hooks = {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [{"type": "command", "command": "echo project"}],
                }
            ]
        }
        global_hooks_data = {
            "PostToolUse": [
                {
                    "matcher": "*",
                    "hooks": [{"type": "command", "command": "echo global"}],
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir) / ".claude"
            claude_dir.mkdir()
            settings_path = claude_dir / "settings.json"
            settings_path.write_text(json.dumps({"hooks": project_hooks}))

            global_file = os.path.join(tmpdir, "hooks.json")
            with open(global_file, "w") as f:
                json.dump(global_hooks_data, f)

            with patch(
                "code_puppy.plugins.claude_code_hooks.config.os.getcwd",
                return_value=tmpdir,
            ):
                with patch(
                    "code_puppy.plugins.claude_code_hooks.config.GLOBAL_HOOKS_FILE",
                    global_file,
                ):
                    result = load_hooks_config()
                    # Both event types should be present
                    assert "PreToolUse" in result
                    assert "PostToolUse" in result
                    # Verify hook groups are concatenated
                    assert len(result["PreToolUse"]) == 1
                    assert len(result["PostToolUse"]) == 1

    def test_merges_same_event_type(self):
        """Global and project hooks with same event type should be concatenated."""
        from code_puppy.plugins.claude_code_hooks.config import load_hooks_config

        project_hooks = {
            "PreToolUse": [
                {
                    "matcher": "Edit",
                    "hooks": [{"type": "command", "command": "echo project"}],
                }
            ]
        }
        global_hooks_data = {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": "echo global"}],
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir) / ".claude"
            claude_dir.mkdir()
            settings_path = claude_dir / "settings.json"
            settings_path.write_text(json.dumps({"hooks": project_hooks}))

            global_file = os.path.join(tmpdir, "hooks.json")
            with open(global_file, "w") as f:
                json.dump(global_hooks_data, f)

            with patch(
                "code_puppy.plugins.claude_code_hooks.config.os.getcwd",
                return_value=tmpdir,
            ):
                with patch(
                    "code_puppy.plugins.claude_code_hooks.config.GLOBAL_HOOKS_FILE",
                    global_file,
                ):
                    result = load_hooks_config()
                    # PreToolUse should have both hook groups
                    assert "PreToolUse" in result
                    assert len(result["PreToolUse"]) == 2
                    # Global hooks should come first, project hooks second
                    assert result["PreToolUse"][0]["matcher"] == "Bash"
                    assert result["PreToolUse"][1]["matcher"] == "Edit"

    def test_global_hooks_loaded_first(self):
        """Global hooks should appear before project hooks in merged result."""
        from code_puppy.plugins.claude_code_hooks.config import load_hooks_config

        project_hooks = {
            "SessionStart": [
                {
                    "matcher": "*",
                    "hooks": [{"type": "command", "command": "project_init"}],
                }
            ]
        }
        global_hooks_data = {
            "SessionStart": [
                {
                    "matcher": "*",
                    "hooks": [{"type": "command", "command": "global_init"}],
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir) / ".claude"
            claude_dir.mkdir()
            settings_path = claude_dir / "settings.json"
            settings_path.write_text(json.dumps({"hooks": project_hooks}))

            global_file = os.path.join(tmpdir, "hooks.json")
            with open(global_file, "w") as f:
                json.dump(global_hooks_data, f)

            with patch(
                "code_puppy.plugins.claude_code_hooks.config.os.getcwd",
                return_value=tmpdir,
            ):
                with patch(
                    "code_puppy.plugins.claude_code_hooks.config.GLOBAL_HOOKS_FILE",
                    global_file,
                ):
                    result = load_hooks_config()
                    hooks = result["SessionStart"]
                    assert len(hooks) == 2
                    # Global should come first
                    assert hooks[0]["hooks"][0]["command"] == "global_init"
                    # Project should come second
                    assert hooks[1]["hooks"][0]["command"] == "project_init"

    def test_only_global_hooks_when_no_project(self):
        """Should load only global hooks if project config doesn't exist."""
        from code_puppy.plugins.claude_code_hooks.config import load_hooks_config

        global_hooks_data = {
            "PostToolUse": [
                {
                    "matcher": "*",
                    "hooks": [{"type": "command", "command": "echo global"}],
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            # No project-level config
            global_file = os.path.join(tmpdir, "hooks.json")
            with open(global_file, "w") as f:
                json.dump(global_hooks_data, f)

            with patch(
                "code_puppy.plugins.claude_code_hooks.config.os.getcwd",
                return_value=tmpdir,
            ):
                with patch(
                    "code_puppy.plugins.claude_code_hooks.config.GLOBAL_HOOKS_FILE",
                    global_file,
                ):
                    result = load_hooks_config()
                    assert result is not None
                    assert "PostToolUse" in result
                    assert len(result["PostToolUse"]) == 1

    def test_only_project_hooks_when_no_global(self):
        """Should load only project hooks if global config doesn't exist."""
        from code_puppy.plugins.claude_code_hooks.config import load_hooks_config

        project_hooks = {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [{"type": "command", "command": "echo project"}],
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir) / ".claude"
            claude_dir.mkdir()
            settings_path = claude_dir / "settings.json"
            settings_path.write_text(json.dumps({"hooks": project_hooks}))

            # Global file doesn't exist
            with patch(
                "code_puppy.plugins.claude_code_hooks.config.os.getcwd",
                return_value=tmpdir,
            ):
                with patch(
                    "code_puppy.plugins.claude_code_hooks.config.GLOBAL_HOOKS_FILE",
                    os.path.join(tmpdir, "nonexistent.json"),
                ):
                    result = load_hooks_config()
                    assert result is not None
                    assert "PreToolUse" in result
                    assert len(result["PreToolUse"]) == 1

    def test_multiple_hook_groups_per_event(self):
        """Multiple hook groups within same event should be preserved."""
        from code_puppy.plugins.claude_code_hooks.config import load_hooks_config

        project_hooks = {
            "PreToolUse": [
                {
                    "matcher": "Edit",
                    "hooks": [{"type": "command", "command": "project_1"}],
                },
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": "project_2"}],
                },
            ]
        }
        global_hooks_data = {
            "PreToolUse": [
                {
                    "matcher": "ReadFile",
                    "hooks": [{"type": "command", "command": "global_1"}],
                },
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir) / ".claude"
            claude_dir.mkdir()
            settings_path = claude_dir / "settings.json"
            settings_path.write_text(json.dumps({"hooks": project_hooks}))

            global_file = os.path.join(tmpdir, "hooks.json")
            with open(global_file, "w") as f:
                json.dump(global_hooks_data, f)

            with patch(
                "code_puppy.plugins.claude_code_hooks.config.os.getcwd",
                return_value=tmpdir,
            ):
                with patch(
                    "code_puppy.plugins.claude_code_hooks.config.GLOBAL_HOOKS_FILE",
                    global_file,
                ):
                    result = load_hooks_config()
                    hooks = result["PreToolUse"]
                    # Should have 3 groups total (1 from global + 2 from project)
                    assert len(hooks) == 3
                    assert hooks[0]["matcher"] == "ReadFile"  # global first
                    assert hooks[1]["matcher"] == "Edit"  # project
                    assert hooks[2]["matcher"] == "Bash"  # project

    def test_wrapped_global_hooks_format(self):
        """Global hooks wrapped in {'hooks': ...} format should work."""
        from code_puppy.plugins.claude_code_hooks.config import load_hooks_config

        project_hooks = {
            "PreToolUse": [
                {"matcher": "*", "hooks": [{"type": "command", "command": "project"}]}
            ]
        }
        # Global format wrapped in 'hooks' key
        global_hooks_data = {
            "hooks": {
                "PostToolUse": [
                    {
                        "matcher": "*",
                        "hooks": [{"type": "command", "command": "global"}],
                    }
                ]
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir) / ".claude"
            claude_dir.mkdir()
            settings_path = claude_dir / "settings.json"
            settings_path.write_text(json.dumps({"hooks": project_hooks}))

            global_file = os.path.join(tmpdir, "hooks.json")
            with open(global_file, "w") as f:
                json.dump(global_hooks_data, f)

            with patch(
                "code_puppy.plugins.claude_code_hooks.config.os.getcwd",
                return_value=tmpdir,
            ):
                with patch(
                    "code_puppy.plugins.claude_code_hooks.config.GLOBAL_HOOKS_FILE",
                    global_file,
                ):
                    result = load_hooks_config()
                    # Should have both event types
                    assert "PreToolUse" in result
                    assert "PostToolUse" in result
