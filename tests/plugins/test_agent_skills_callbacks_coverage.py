"""Tests for agent_skills/register_callbacks.py full coverage."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# Patch targets for lazy imports inside _get_skills_prompt_section
_CFG = "code_puppy.plugins.agent_skills.config"
_DISC = "code_puppy.plugins.agent_skills.discovery"
_META = "code_puppy.plugins.agent_skills.metadata"
_PB = "code_puppy.plugins.agent_skills.prompt_builder"


class TestGetSkillsPromptSection:
    def test_disabled(self):
        from code_puppy.plugins.agent_skills.register_callbacks import (
            _get_skills_prompt_section,
        )

        with patch(f"{_CFG}.get_skills_enabled", return_value=False):
            assert _get_skills_prompt_section() is None

    def test_no_skills_discovered(self):
        from code_puppy.plugins.agent_skills.register_callbacks import (
            _get_skills_prompt_section,
        )

        with (
            patch(f"{_CFG}.get_skills_enabled", return_value=True),
            patch(f"{_CFG}.get_skill_directories", return_value=["/fake"]),
            patch(f"{_DISC}.discover_skills", return_value=[]),
        ):
            assert _get_skills_prompt_section() is None

    def test_disabled_and_no_skill_md(self):
        from code_puppy.plugins.agent_skills.register_callbacks import (
            _get_skills_prompt_section,
        )

        skill1 = MagicMock(name="disabled_skill", has_skill_md=True)
        skill1.name = "disabled_skill"
        skill2 = MagicMock(name="no_md", has_skill_md=False)
        skill2.name = "no_md"

        with (
            patch(f"{_CFG}.get_skills_enabled", return_value=True),
            patch(f"{_CFG}.get_skill_directories", return_value=["/fake"]),
            patch(f"{_DISC}.discover_skills", return_value=[skill1, skill2]),
            patch(f"{_CFG}.get_disabled_skills", return_value={"disabled_skill"}),
            patch(f"{_META}.parse_skill_metadata", return_value=None),
        ):
            assert _get_skills_prompt_section() is None

    def test_metadata_parse_fails(self):
        from code_puppy.plugins.agent_skills.register_callbacks import (
            _get_skills_prompt_section,
        )

        skill = MagicMock(has_skill_md=True)
        skill.name = "my_skill"

        with (
            patch(f"{_CFG}.get_skills_enabled", return_value=True),
            patch(f"{_CFG}.get_skill_directories", return_value=["/fake"]),
            patch(f"{_DISC}.discover_skills", return_value=[skill]),
            patch(f"{_CFG}.get_disabled_skills", return_value=set()),
            patch(f"{_META}.parse_skill_metadata", return_value=None),
        ):
            assert _get_skills_prompt_section() is None

    def test_success(self):
        from code_puppy.plugins.agent_skills.register_callbacks import (
            _get_skills_prompt_section,
        )

        skill = MagicMock(has_skill_md=True)
        skill.name = "good_skill"
        metadata = MagicMock()

        with (
            patch(f"{_CFG}.get_skills_enabled", return_value=True),
            patch(f"{_CFG}.get_skill_directories", return_value=["/fake"]),
            patch(f"{_DISC}.discover_skills", return_value=[skill]),
            patch(f"{_CFG}.get_disabled_skills", return_value=set()),
            patch(f"{_META}.parse_skill_metadata", return_value=metadata),
            patch(f"{_PB}.build_available_skills_xml", return_value="<xml/>"),
            patch(f"{_PB}.build_skills_guidance", return_value="guidance"),
        ):
            result = _get_skills_prompt_section()
            assert "<xml/>" in result
            assert "guidance" in result


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
            patch(f"{_CFG}.get_skills_enabled", return_value=True),
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
            patch(f"{_CFG}.get_skills_enabled", return_value=True),
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
            patch(f"{_CFG}.get_skills_enabled", return_value=False),
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
            patch(f"{_CFG}.get_skills_enabled", return_value=True),
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

    def test_skills_enable(self):
        from code_puppy.plugins.agent_skills.register_callbacks import (
            _handle_skills_command,
        )

        with (
            patch(f"{_CFG}.set_skills_enabled"),
            patch(f"{_MSG}.emit_success"),
        ):
            assert _handle_skills_command("/skills enable", "skills") is True

    def test_skills_disable(self):
        from code_puppy.plugins.agent_skills.register_callbacks import (
            _handle_skills_command,
        )

        with (
            patch(f"{_CFG}.set_skills_enabled"),
            patch(f"{_MSG}.emit_warning"),
        ):
            assert _handle_skills_command("/skills disable", "skills") is True

    def test_skills_unknown_subcommand(self):
        from code_puppy.plugins.agent_skills.register_callbacks import (
            _handle_skills_command,
        )

        with (
            patch(f"{_MSG}.emit_error"),
            patch(f"{_MSG}.emit_info"),
        ):
            assert _handle_skills_command("/skills bogus", "skills") is True

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
