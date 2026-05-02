"""Tests for plugin coverage gaps.

Covers missed lines in:
- example_custom_command/register_callbacks.py
- universal_constructor/register_callbacks.py
- agent_skills/discovery.py
"""

from unittest.mock import MagicMock, patch

# ─── example_custom_command/register_callbacks.py ──────────────────────


class TestExampleCustomCommand:
    """Tests for example custom command (lines 6, 23-47)."""

    def _get_handler(self):
        from code_puppy.plugins.example_custom_command.register_callbacks import (
            _handle_custom_command,
        )

        return _handle_custom_command

    def _get_help(self):
        from code_puppy.plugins.example_custom_command.register_callbacks import (
            _custom_help,
        )

        return _custom_help

    def test_help(self):
        entries = self._get_help()()
        assert len(entries) == 2
        names = [e[0] for e in entries]
        assert "woof" in names
        assert "echo" in names

    def test_empty_name_returns_none(self):
        assert self._get_handler()("/", "") is None

    def test_unknown_command_returns_none(self):
        assert self._get_handler()("unknown", "unknown") is None

    def test_woof_no_args(self):
        result = self._get_handler()("woof", "woof")
        assert result == "Tell me a dog fact"

    def test_woof_with_text(self):
        result = self._get_handler()("woof hello world", "woof")
        assert result == "hello world"

    def test_echo_no_args(self):
        result = self._get_handler()("echo", "echo")
        assert result == ""

    def test_echo_with_text(self):
        result = self._get_handler()("echo hello", "echo")
        assert result == "hello"


# ─── universal_constructor/register_callbacks.py ───────────────────────


class TestUniversalConstructorCallbacks:
    """Tests for UC startup callback (lines 19-38)."""

    def test_startup_disabled(self):
        from code_puppy.plugins.universal_constructor.register_callbacks import (
            _on_startup,
        )

        with patch(
            "code_puppy.config.get_universal_constructor_enabled",
            return_value=False,
        ) as mock_enabled:
            _on_startup()
            mock_enabled.assert_called_once()

    def test_startup_enabled(self):
        mock_tool = MagicMock()
        mock_tool.meta.enabled = True
        mock_registry = MagicMock()
        mock_registry.list_tools.return_value = [mock_tool]

        from code_puppy.plugins.universal_constructor.register_callbacks import (
            _on_startup,
        )

        with (
            patch(
                "code_puppy.config.get_universal_constructor_enabled",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.universal_constructor.register_callbacks.get_registry",
                return_value=mock_registry,
            ),
            patch(
                "code_puppy.plugins.universal_constructor.register_callbacks.USER_UC_DIR",
            ) as mock_dir,
        ):
            _on_startup()
            mock_dir.mkdir.assert_called_once_with(parents=True, exist_ok=True)
            mock_registry.list_tools.assert_called_once_with(include_disabled=True)


# ─── agent_skills/discovery.py ─────────────────────────────────────────


class TestDiscoveryMissedLines:
    """Tests for discovery.py lines 72-79 (None directories branch) and 95 (warning)."""

    def test_discover_skills_none_directories_uses_config(self, tmp_path):
        """Lines 72-79: when directories=None, merges config + defaults."""
        from code_puppy.plugins.agent_skills.discovery import discover_skills

        skill_dir = tmp_path / "skills" / "my-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Skill")

        with (
            patch(
                "code_puppy.plugins.agent_skills.discovery.get_skill_directories",
                return_value=[str(tmp_path / "skills")],
            ),
            patch(
                "code_puppy.plugins.agent_skills.discovery.get_default_skill_directories",
                return_value=[tmp_path / "skills"],  # same as config, tests dedup
            ),
        ):
            results = discover_skills(directories=None)
            assert any(s.name == "my-skill" for s in results)

    def test_discover_skills_path_not_directory(self, tmp_path):
        """Line 95: warning when skill path is not a directory."""
        # Create a file where a directory is expected
        not_a_dir = tmp_path / "not-a-dir"
        not_a_dir.write_text("I'm a file")

        from code_puppy.plugins.agent_skills.discovery import discover_skills

        results = discover_skills(directories=[not_a_dir])
        assert results == []
