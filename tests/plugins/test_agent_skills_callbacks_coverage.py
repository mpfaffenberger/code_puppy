"""Tests for agent_skills/register_callbacks.py full coverage."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# Patch targets for lazy imports inside _get_skills_prompt_section
_CFG = "code_puppy.plugins.agent_skills.config"
_DISC = "code_puppy.plugins.agent_skills.discovery"
_META = "code_puppy.plugins.agent_skills.metadata"
_PB = "code_puppy.plugins.agent_skills.prompt_builder"
_ENABLED = "code_puppy.plugins.agent_skills.enabled_skills"


class TestGetSkillsPromptSection:
    def test_no_enabled_skills(self):
        """Helper returns [] → no prompt section."""
        from code_puppy.plugins.agent_skills.register_callbacks import (
            _get_skills_prompt_section,
        )

        with patch(f"{_ENABLED}.list_enabled_skill_metadata", return_value=[]):
            assert _get_skills_prompt_section() is None

    def test_success(self):
        """Helper returns metadata → prompt section built from it."""
        from code_puppy.plugins.agent_skills.register_callbacks import (
            _get_skills_prompt_section,
        )

        metadata = MagicMock()

        with (
            patch(f"{_ENABLED}.list_enabled_skill_metadata", return_value=[metadata]),
            patch(f"{_CFG}.get_frontmatter_in_system_prompt", return_value=True),
            patch(f"{_PB}.build_available_skills_block", return_value="BLOCK"),
            patch(f"{_PB}.build_skills_guidance", return_value="guidance"),
        ):
            result = _get_skills_prompt_section()
            assert "BLOCK" in result
            assert "guidance" in result

    def test_frontmatter_disabled_returns_guidance_only(self):
        """With frontmatter off, only the guidance one-liner is emitted —
        the per-skill block is suppressed but the model is still told the
        activate_skill / list_or_search_skills mechanism exists."""
        from code_puppy.plugins.agent_skills.register_callbacks import (
            _get_skills_prompt_section,
        )

        metadata = MagicMock()

        with (
            patch(f"{_ENABLED}.list_enabled_skill_metadata", return_value=[metadata]),
            patch(f"{_CFG}.get_frontmatter_in_system_prompt", return_value=False),
            patch(
                f"{_PB}.build_available_skills_block", return_value="BLOCK"
            ) as mock_block,
            patch(f"{_PB}.build_skills_guidance", return_value="guidance"),
        ):
            result = _get_skills_prompt_section()

        assert result == "guidance"
        assert "BLOCK" not in result
        # And critically: we never even built the block.
        mock_block.assert_not_called()

    def test_frontmatter_disabled_no_skills_returns_none(self):
        """No skills + frontmatter off should still short-circuit to None;
        don't advertise a mechanism that has nothing to find."""
        from code_puppy.plugins.agent_skills.register_callbacks import (
            _get_skills_prompt_section,
        )

        with (
            patch(f"{_ENABLED}.list_enabled_skill_metadata", return_value=[]),
            patch(f"{_CFG}.get_frontmatter_in_system_prompt", return_value=False),
        ):
            assert _get_skills_prompt_section() is None


class TestEnabledSkillsHelper:
    """Direct tests for the enabled_skills helper — guarantees we never
    parse frontmatter for disabled skills."""

    def test_disabled_skill_never_parses_frontmatter(self):
        """The headline guarantee: parse_skill_metadata is NOT called for
        a disabled skill."""
        from code_puppy.plugins.agent_skills.enabled_skills import (
            list_enabled_skill_metadata,
        )

        disabled = MagicMock(has_skill_md=True)
        disabled.name = "disabled_one"
        enabled = MagicMock(has_skill_md=True)
        enabled.name = "enabled_one"

        good_meta = MagicMock()

        with (
            patch(f"{_CFG}.get_skill_directories", return_value=["/fake"]),
            patch(f"{_DISC}.discover_skills", return_value=[disabled, enabled]),
            patch(f"{_CFG}.get_disabled_skills", return_value={"disabled_one"}),
            patch(
                f"{_META}.parse_skill_metadata", return_value=good_meta
            ) as mock_parse,
        ):
            result = list_enabled_skill_metadata()

        assert result == [good_meta]
        # The disabled skill's path must NEVER reach parse_skill_metadata.
        called_paths = [call.args[0] for call in mock_parse.call_args_list]
        assert enabled.path in called_paths
        assert disabled.path not in called_paths

    def test_skill_without_skill_md_is_skipped(self):
        from code_puppy.plugins.agent_skills.enabled_skills import (
            list_enabled_skill_metadata,
        )

        no_md = MagicMock(has_skill_md=False)
        no_md.name = "no_md"

        with (
            patch(f"{_CFG}.get_skill_directories", return_value=["/fake"]),
            patch(f"{_DISC}.discover_skills", return_value=[no_md]),
            patch(f"{_CFG}.get_disabled_skills", return_value=set()),
            patch(f"{_META}.parse_skill_metadata") as mock_parse,
        ):
            assert list_enabled_skill_metadata() == []
        mock_parse.assert_not_called()


class TestInjectSkillsIntoPrompt:
    def test_no_skills(self):
        from code_puppy.plugins.agent_skills.register_callbacks import (
            _inject_skills_into_prompt,
        )

        with patch(
            "code_puppy.plugins.agent_skills.register_callbacks._get_skills_prompt_section",
            return_value=None,
        ):
            assert _inject_skills_into_prompt("model", "prompt", "user") is None

    def test_with_skills(self):
        from code_puppy.plugins.agent_skills.register_callbacks import (
            _inject_skills_into_prompt,
        )

        with patch(
            "code_puppy.plugins.agent_skills.register_callbacks._get_skills_prompt_section",
            return_value="SKILLS SECTION",
        ):
            result = _inject_skills_into_prompt("model", "base prompt", "user input")
            assert result["instructions"].endswith("SKILLS SECTION")
            assert result["user_prompt"] == "user input"
            assert result["handled"] is False


class TestRegisterSkillsTools:
    def test_returns_tools(self):
        from code_puppy.plugins.agent_skills.register_callbacks import (
            _register_skills_tools,
        )

        tools = _register_skills_tools()
        assert len(tools) == 2
        names = {t["name"] for t in tools}
        assert "activate_skill" in names
        assert "list_or_search_skills" in names


class TestSkillsCommandHelp:
    def test_returns_entries(self):
        from code_puppy.plugins.agent_skills.register_callbacks import (
            _skills_command_help,
        )

        entries = _skills_command_help()
        names = [n for n, _ in entries]
        assert "skills" in names
        assert "skill" in names


# Patch targets for lazy imports inside _handle_skills_command
_MSG = "code_puppy.messaging"
_SKILLS_MENU = "code_puppy.plugins.agent_skills.skills_menu"
_SKILLS_INSTALL = "code_puppy.plugins.agent_skills.skills_install_menu"


class TestHandleSkillsCommand:
    def test_unrelated_command(self):
        from code_puppy.plugins.agent_skills.register_callbacks import (
            _handle_skills_command,
        )

        assert _handle_skills_command("/other", "other") is None

    def test_skills_list_no_skills(self):
        from code_puppy.plugins.agent_skills.register_callbacks import (
            _handle_skills_command,
        )

        with (
            patch(f"{_CFG}.get_disabled_skills", return_value=set()),
            patch(f"{_DISC}.discover_skills", return_value=[]),
            patch(f"{_MSG}.emit_info"),
        ):
            assert _handle_skills_command("/skills list", "skills") is True

    def test_skills_list_with_skills(self):
        from code_puppy.plugins.agent_skills.register_callbacks import (
            _handle_skills_command,
        )

        skill = MagicMock(has_skill_md=True)
        skill.name = "my_skill"
        metadata = MagicMock(
            name="my_skill", version="1.0", author="me", description="desc", tags=["t"]
        )
        metadata.name = "my_skill"

        with (
            patch(f"{_CFG}.get_disabled_skills", return_value=set()),
            patch(f"{_DISC}.discover_skills", return_value=[skill]),
            patch(f"{_META}.parse_skill_metadata", return_value=metadata),
            patch(f"{_MSG}.emit_info"),
        ):
            assert _handle_skills_command("/skills list", "skills") is True

    def test_skills_list_disabled_skill(self):
        from code_puppy.plugins.agent_skills.register_callbacks import (
            _handle_skills_command,
        )

        skill = MagicMock(has_skill_md=True)
        skill.name = "dis_skill"
        metadata = MagicMock(version=None, author=None, tags=[])
        metadata.name = "dis_skill"

        with (
            patch(f"{_CFG}.get_disabled_skills", return_value={"dis_skill"}),
            patch(f"{_DISC}.discover_skills", return_value=[skill]),
            patch(f"{_META}.parse_skill_metadata", return_value=metadata),
            patch(f"{_MSG}.emit_info"),
        ):
            assert _handle_skills_command("/skills list", "skills") is True

    def test_skills_list_no_metadata(self):
        from code_puppy.plugins.agent_skills.register_callbacks import (
            _handle_skills_command,
        )

        skill = MagicMock(has_skill_md=True)
        skill.name = "no_meta"

        with (
            patch(f"{_CFG}.get_disabled_skills", return_value=set()),
            patch(f"{_DISC}.discover_skills", return_value=[skill]),
            patch(f"{_META}.parse_skill_metadata", return_value=None),
            patch(f"{_MSG}.emit_info"),
        ):
            assert _handle_skills_command("/skills list", "skills") is True

    def test_skills_install(self):
        from code_puppy.plugins.agent_skills.register_callbacks import (
            _handle_skills_command,
        )

        with patch(f"{_SKILLS_INSTALL}.run_skills_install_menu"):
            assert _handle_skills_command("/skills install", "skills") is True

    def test_skills_frontmatter_on(self):
        from code_puppy.plugins.agent_skills.register_callbacks import (
            _handle_skills_command,
        )

        with (
            patch(f"{_CFG}.get_frontmatter_in_system_prompt", return_value=False),
            patch(f"{_CFG}.set_frontmatter_in_system_prompt") as mock_set,
            patch(f"{_MSG}.emit_success") as mock_success,
        ):
            assert _handle_skills_command("/skills frontmatter on", "skills") is True
            mock_set.assert_called_once_with(True)
            mock_success.assert_called_once()

    def test_skills_frontmatter_off(self):
        from code_puppy.plugins.agent_skills.register_callbacks import (
            _handle_skills_command,
        )

        with (
            patch(f"{_CFG}.get_frontmatter_in_system_prompt", return_value=True),
            patch(f"{_CFG}.set_frontmatter_in_system_prompt") as mock_set,
            patch(f"{_MSG}.emit_warning") as mock_warning,
        ):
            assert _handle_skills_command("/skills frontmatter off", "skills") is True
            mock_set.assert_called_once_with(False)
            mock_warning.assert_called_once()

    def test_skills_frontmatter_toggle(self):
        from code_puppy.plugins.agent_skills.register_callbacks import (
            _handle_skills_command,
        )

        with (
            patch(f"{_CFG}.get_frontmatter_in_system_prompt", return_value=True),
            patch(f"{_CFG}.set_frontmatter_in_system_prompt") as mock_set,
            patch(f"{_MSG}.emit_warning"),
        ):
            assert (
                _handle_skills_command("/skills frontmatter toggle", "skills") is True
            )
            mock_set.assert_called_once_with(False)

    def test_skills_frontmatter_no_arg_shows_state(self):
        from code_puppy.plugins.agent_skills.register_callbacks import (
            _handle_skills_command,
        )

        with (
            patch(f"{_CFG}.get_frontmatter_in_system_prompt", return_value=True),
            patch(f"{_CFG}.set_frontmatter_in_system_prompt") as mock_set,
            patch(f"{_MSG}.emit_info") as mock_info,
        ):
            assert _handle_skills_command("/skills frontmatter", "skills") is True
            mock_set.assert_not_called()
            # Should mention current state in one of the emit_info calls.
            assert "on" in str(mock_info.call_args_list).lower()

    def test_skills_frontmatter_bogus_arg(self):
        from code_puppy.plugins.agent_skills.register_callbacks import (
            _handle_skills_command,
        )

        with (
            patch(f"{_CFG}.get_frontmatter_in_system_prompt", return_value=True),
            patch(f"{_CFG}.set_frontmatter_in_system_prompt") as mock_set,
            patch(f"{_MSG}.emit_error") as mock_error,
            patch(f"{_MSG}.emit_info"),
        ):
            assert (
                _handle_skills_command("/skills frontmatter banana", "skills") is True
            )
            mock_set.assert_not_called()
            mock_error.assert_called_once()

    def test_skills_help(self):
        from code_puppy.plugins.agent_skills.register_callbacks import (
            _handle_skills_command,
        )

        with patch(f"{_MSG}.emit_info") as mock_info:
            assert _handle_skills_command("/skills help", "skills") is True
            assert mock_info.call_count >= 2
            assert "toggle" in str(mock_info.call_args_list)

    def test_skills_refresh(self):
        from code_puppy.plugins.agent_skills.register_callbacks import (
            _handle_skills_command,
        )

        refreshed = [
            MagicMock(name="valid", has_skill_md=True),
            MagicMock(name="invalid", has_skill_md=False),
        ]

        with (
            patch(f"{_DISC}.refresh_skill_cache", return_value=refreshed),
            patch(f"{_MSG}.emit_success") as mock_success,
        ):
            assert _handle_skills_command("/skills refresh", "skills") is True
            mock_success.assert_called_once()
            assert "Refreshed skills cache" in str(mock_success.call_args)
            assert "2 discovered" in str(mock_success.call_args)
            assert "1 with SKILL.md" in str(mock_success.call_args)

    def test_skills_unknown_subcommand(self):
        from code_puppy.plugins.agent_skills.register_callbacks import (
            _handle_skills_command,
        )

        with (
            patch(f"{_MSG}.emit_error"),
            patch(f"{_MSG}.emit_info") as mock_info,
        ):
            assert _handle_skills_command("/skills bogus", "skills") is True
            assert "Usage:" in str(mock_info.call_args)
            assert "help" in str(mock_info.call_args)

    def test_skills_no_subcommand_launches_menu(self):
        from code_puppy.plugins.agent_skills.register_callbacks import (
            _handle_skills_command,
        )

        with patch(f"{_SKILLS_MENU}.show_skills_menu") as mock_menu:
            assert _handle_skills_command("/skills", "skills") is True
            mock_menu.assert_called_once()

    def test_skill_alias(self):
        from code_puppy.plugins.agent_skills.register_callbacks import (
            _handle_skills_command,
        )

        with patch(f"{_SKILLS_MENU}.show_skills_menu"):
            assert _handle_skills_command("/skill", "skill") is True
