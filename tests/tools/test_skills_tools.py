"""Tests for code_puppy/tools/skills_tools.py - 100% coverage."""

from unittest.mock import MagicMock, patch

import pytest


def _make_agent():
    agent = MagicMock()
    captured = {}

    def tool(fn):
        captured["fn"] = fn
        return fn

    agent.tool = tool
    return agent, captured


class TestSkillModels:
    def test_skill_list_output(self):
        from code_puppy.tools.skills_tools import SkillListOutput

        out = SkillListOutput(skills=[], total_count=0, query="test", error=None)
        assert out.total_count == 0

    def test_skill_activate_output(self):
        from code_puppy.tools.skills_tools import SkillActivateOutput

        out = SkillActivateOutput(skill_name="x", content="c", resources=[], error=None)
        assert out.skill_name == "x"


class TestActivateSkill:
    @pytest.mark.asyncio
    @patch(
        "code_puppy.plugins.agent_skills.config.get_skills_enabled", return_value=False
    )
    async def test_disabled(self, mock_enabled):
        from code_puppy.tools.skills_tools import register_activate_skill

        agent, cap = _make_agent()
        register_activate_skill(agent)
        ctx = MagicMock()
        result = await cap["fn"](ctx, skill_name="test")
        assert result.error and "disabled" in result.error

    @pytest.mark.asyncio
    @patch(
        "code_puppy.plugins.agent_skills.config.get_skills_enabled", return_value=True
    )
    @patch(
        "code_puppy.plugins.agent_skills.config.get_skill_directories",
        return_value=["/tmp"],
    )
    @patch(
        "code_puppy.plugins.agent_skills.discovery.discover_skills",
        side_effect=Exception("boom"),
    )
    async def test_discover_error(self, mock_disc, mock_dirs, mock_enabled):
        from code_puppy.tools.skills_tools import register_activate_skill

        agent, cap = _make_agent()
        register_activate_skill(agent)
        ctx = MagicMock()
        result = await cap["fn"](ctx, skill_name="test")
        assert result.error and "discover" in result.error.lower()

    @pytest.mark.asyncio
    @patch(
        "code_puppy.plugins.agent_skills.config.get_skills_enabled", return_value=True
    )
    @patch(
        "code_puppy.plugins.agent_skills.config.get_skill_directories",
        return_value=["/tmp"],
    )
    @patch("code_puppy.plugins.agent_skills.discovery.discover_skills")
    async def test_skill_not_found(self, mock_disc, mock_dirs, mock_enabled):
        mock_disc.return_value = []
        from code_puppy.tools.skills_tools import register_activate_skill

        agent, cap = _make_agent()
        register_activate_skill(agent)
        ctx = MagicMock()
        result = await cap["fn"](ctx, skill_name="nonexistent")
        assert result.error and "not found" in result.error

    @pytest.mark.asyncio
    @patch("code_puppy.tools.skills_tools.get_message_bus")
    @patch(
        "code_puppy.plugins.agent_skills.metadata.get_skill_resources", return_value=[]
    )
    @patch(
        "code_puppy.plugins.agent_skills.metadata.load_full_skill_content",
        return_value=None,
    )
    @patch("code_puppy.plugins.agent_skills.discovery.discover_skills")
    @patch(
        "code_puppy.plugins.agent_skills.config.get_skill_directories",
        return_value=["/tmp"],
    )
    @patch(
        "code_puppy.plugins.agent_skills.config.get_skills_enabled", return_value=True
    )
    async def test_load_content_fails(
        self, mock_en, mock_dirs, mock_disc, mock_load, mock_res, mock_bus
    ):
        skill = MagicMock()
        skill.name = "test"
        skill.has_skill_md = True
        skill.path = "/tmp/test"
        mock_disc.return_value = [skill]
        from code_puppy.tools.skills_tools import register_activate_skill

        agent, cap = _make_agent()
        register_activate_skill(agent)
        ctx = MagicMock()
        result = await cap["fn"](ctx, skill_name="test")
        assert result.error and "Failed to load" in result.error

    @pytest.mark.asyncio
    @patch("code_puppy.tools.skills_tools.get_message_bus")
    @patch(
        "code_puppy.plugins.agent_skills.metadata.get_skill_resources",
        return_value=["/tmp/r.txt"],
    )
    @patch(
        "code_puppy.plugins.agent_skills.metadata.load_full_skill_content",
        return_value="# Skill content",
    )
    @patch("code_puppy.plugins.agent_skills.discovery.discover_skills")
    @patch(
        "code_puppy.plugins.agent_skills.config.get_skill_directories",
        return_value=["/tmp"],
    )
    @patch(
        "code_puppy.plugins.agent_skills.config.get_skills_enabled", return_value=True
    )
    async def test_success(
        self, mock_en, mock_dirs, mock_disc, mock_load, mock_res, mock_bus
    ):
        skill = MagicMock()
        skill.name = "test"
        skill.has_skill_md = True
        skill.path = "/tmp/test"
        mock_disc.return_value = [skill]
        from code_puppy.tools.skills_tools import register_activate_skill

        agent, cap = _make_agent()
        register_activate_skill(agent)
        ctx = MagicMock()
        result = await cap["fn"](ctx, skill_name="test")
        assert result.error is None
        assert result.content == "# Skill content"


class TestListOrSearchSkills:
    @pytest.mark.asyncio
    @patch(
        "code_puppy.plugins.agent_skills.config.get_skills_enabled", return_value=False
    )
    async def test_disabled(self, mock_enabled):
        from code_puppy.tools.skills_tools import register_list_or_search_skills

        agent, cap = _make_agent()
        register_list_or_search_skills(agent)
        ctx = MagicMock()
        result = await cap["fn"](ctx, query=None)
        assert result.error and "disabled" in result.error

    @pytest.mark.asyncio
    @patch(
        "code_puppy.plugins.agent_skills.config.get_skills_enabled", return_value=True
    )
    @patch(
        "code_puppy.plugins.agent_skills.config.get_disabled_skills", return_value=set()
    )
    @patch(
        "code_puppy.plugins.agent_skills.config.get_skill_directories",
        return_value=["/tmp"],
    )
    @patch(
        "code_puppy.plugins.agent_skills.discovery.discover_skills",
        side_effect=Exception("boom"),
    )
    async def test_discover_error(self, mock_disc, mock_dirs, mock_dis, mock_en):
        from code_puppy.tools.skills_tools import register_list_or_search_skills

        agent, cap = _make_agent()
        register_list_or_search_skills(agent)
        ctx = MagicMock()
        result = await cap["fn"](ctx, query=None)
        assert result.error

    @pytest.mark.asyncio
    @patch("code_puppy.tools.skills_tools.get_message_bus")
    @patch("code_puppy.plugins.agent_skills.metadata.parse_skill_metadata")
    @patch("code_puppy.plugins.agent_skills.discovery.discover_skills")
    @patch(
        "code_puppy.plugins.agent_skills.config.get_skill_directories",
        return_value=["/tmp"],
    )
    @patch(
        "code_puppy.plugins.agent_skills.config.get_disabled_skills",
        return_value={"disabled-skill"},
    )
    @patch(
        "code_puppy.plugins.agent_skills.config.get_skills_enabled", return_value=True
    )
    async def test_list_with_filter(
        self, mock_en, mock_dis, mock_dirs, mock_disc, mock_meta, mock_bus
    ):
        skill1 = MagicMock()
        skill1.name = "good-skill"
        skill1.has_skill_md = True
        skill1.path = "/tmp/good"

        skill2 = MagicMock()
        skill2.name = "disabled-skill"
        skill2.has_skill_md = True
        skill2.path = "/tmp/disabled"

        skill3 = MagicMock()
        skill3.name = "no-md"
        skill3.has_skill_md = False
        skill3.path = "/tmp/nomd"

        mock_disc.return_value = [skill1, skill2, skill3]

        meta = MagicMock()
        meta.name = "good-skill"
        meta.description = "A good skill"
        meta.path = "/tmp/good"
        meta.tags = ["python"]
        meta.version = "1.0"
        meta.author = "test"
        mock_meta.return_value = meta

        from code_puppy.tools.skills_tools import register_list_or_search_skills

        agent, cap = _make_agent()
        register_list_or_search_skills(agent)
        ctx = MagicMock()
        result = await cap["fn"](ctx, query=None)
        assert result.total_count == 1
        assert result.skills[0]["name"] == "good-skill"

    @pytest.mark.asyncio
    @patch("code_puppy.tools.skills_tools.get_message_bus")
    @patch("code_puppy.plugins.agent_skills.metadata.parse_skill_metadata")
    @patch("code_puppy.plugins.agent_skills.discovery.discover_skills")
    @patch(
        "code_puppy.plugins.agent_skills.config.get_skill_directories",
        return_value=["/tmp"],
    )
    @patch(
        "code_puppy.plugins.agent_skills.config.get_disabled_skills", return_value=set()
    )
    @patch(
        "code_puppy.plugins.agent_skills.config.get_skills_enabled", return_value=True
    )
    async def test_search_by_name(
        self, mock_en, mock_dis, mock_dirs, mock_disc, mock_meta, mock_bus
    ):
        skill = MagicMock()
        skill.name = "docker-deploy"
        skill.has_skill_md = True
        skill.path = "/tmp/dd"
        mock_disc.return_value = [skill]

        meta = MagicMock()
        meta.name = "docker-deploy"
        meta.description = "Deploy with docker"
        meta.path = "/tmp/dd"
        meta.tags = ["docker"]
        meta.version = "1.0"
        meta.author = "test"
        mock_meta.return_value = meta

        from code_puppy.tools.skills_tools import register_list_or_search_skills

        agent, cap = _make_agent()
        register_list_or_search_skills(agent)
        ctx = MagicMock()

        # Search by name
        result = await cap["fn"](ctx, query="docker")
        assert result.total_count == 1

    @pytest.mark.asyncio
    @patch("code_puppy.tools.skills_tools.get_message_bus")
    @patch("code_puppy.plugins.agent_skills.metadata.parse_skill_metadata")
    @patch("code_puppy.plugins.agent_skills.discovery.discover_skills")
    @patch(
        "code_puppy.plugins.agent_skills.config.get_skill_directories",
        return_value=["/tmp"],
    )
    @patch(
        "code_puppy.plugins.agent_skills.config.get_disabled_skills", return_value=set()
    )
    @patch(
        "code_puppy.plugins.agent_skills.config.get_skills_enabled", return_value=True
    )
    async def test_search_by_description(
        self, mock_en, mock_dis, mock_dirs, mock_disc, mock_meta, mock_bus
    ):
        skill = MagicMock()
        skill.name = "my-skill"
        skill.has_skill_md = True
        skill.path = "/tmp/s"
        mock_disc.return_value = [skill]

        meta = MagicMock()
        meta.name = "my-skill"
        meta.description = "Deploy kubernetes clusters"
        meta.path = "/tmp/s"
        meta.tags = []
        meta.version = "1.0"
        meta.author = "test"
        mock_meta.return_value = meta

        from code_puppy.tools.skills_tools import register_list_or_search_skills

        agent, cap = _make_agent()
        register_list_or_search_skills(agent)
        ctx = MagicMock()

        result = await cap["fn"](ctx, query="kubernetes")
        assert result.total_count == 1

    @pytest.mark.asyncio
    @patch("code_puppy.tools.skills_tools.get_message_bus")
    @patch("code_puppy.plugins.agent_skills.metadata.parse_skill_metadata")
    @patch("code_puppy.plugins.agent_skills.discovery.discover_skills")
    @patch(
        "code_puppy.plugins.agent_skills.config.get_skill_directories",
        return_value=["/tmp"],
    )
    @patch(
        "code_puppy.plugins.agent_skills.config.get_disabled_skills", return_value=set()
    )
    @patch(
        "code_puppy.plugins.agent_skills.config.get_skills_enabled", return_value=True
    )
    async def test_search_by_tag(
        self, mock_en, mock_dis, mock_dirs, mock_disc, mock_meta, mock_bus
    ):
        skill = MagicMock()
        skill.name = "my-skill"
        skill.has_skill_md = True
        skill.path = "/tmp/s"
        mock_disc.return_value = [skill]

        meta = MagicMock()
        meta.name = "my-skill"
        meta.description = "Some skill"
        meta.path = "/tmp/s"
        meta.tags = ["deployment"]
        meta.version = "1.0"
        meta.author = "test"
        mock_meta.return_value = meta

        from code_puppy.tools.skills_tools import register_list_or_search_skills

        agent, cap = _make_agent()
        register_list_or_search_skills(agent)
        ctx = MagicMock()

        result = await cap["fn"](ctx, query="deployment")
        assert result.total_count == 1

    @pytest.mark.asyncio
    @patch("code_puppy.tools.skills_tools.get_message_bus")
    @patch("code_puppy.plugins.agent_skills.metadata.parse_skill_metadata")
    @patch("code_puppy.plugins.agent_skills.discovery.discover_skills")
    @patch(
        "code_puppy.plugins.agent_skills.config.get_skill_directories",
        return_value=["/tmp"],
    )
    @patch(
        "code_puppy.plugins.agent_skills.config.get_disabled_skills", return_value=set()
    )
    @patch(
        "code_puppy.plugins.agent_skills.config.get_skills_enabled", return_value=True
    )
    async def test_search_no_match(
        self, mock_en, mock_dis, mock_dirs, mock_disc, mock_meta, mock_bus
    ):
        skill = MagicMock()
        skill.name = "my-skill"
        skill.has_skill_md = True
        skill.path = "/tmp/s"
        mock_disc.return_value = [skill]

        meta = MagicMock()
        meta.name = "my-skill"
        meta.description = "Some skill"
        meta.path = "/tmp/s"
        meta.tags = []
        meta.version = "1.0"
        meta.author = "test"
        mock_meta.return_value = meta

        from code_puppy.tools.skills_tools import register_list_or_search_skills

        agent, cap = _make_agent()
        register_list_or_search_skills(agent)
        ctx = MagicMock()

        result = await cap["fn"](ctx, query="zzzzz")
        assert result.total_count == 0

    @pytest.mark.asyncio
    @patch("code_puppy.tools.skills_tools.get_message_bus")
    @patch(
        "code_puppy.plugins.agent_skills.metadata.parse_skill_metadata",
        return_value=None,
    )
    @patch("code_puppy.plugins.agent_skills.discovery.discover_skills")
    @patch(
        "code_puppy.plugins.agent_skills.config.get_skill_directories",
        return_value=["/tmp"],
    )
    @patch(
        "code_puppy.plugins.agent_skills.config.get_disabled_skills", return_value=set()
    )
    @patch(
        "code_puppy.plugins.agent_skills.config.get_skills_enabled", return_value=True
    )
    async def test_no_metadata(
        self, mock_en, mock_dis, mock_dirs, mock_disc, mock_meta, mock_bus
    ):
        skill = MagicMock()
        skill.name = "bad-skill"
        skill.has_skill_md = True
        skill.path = "/tmp/bad"
        mock_disc.return_value = [skill]

        from code_puppy.tools.skills_tools import register_list_or_search_skills

        agent, cap = _make_agent()
        register_list_or_search_skills(agent)
        ctx = MagicMock()

        result = await cap["fn"](ctx, query=None)
        assert result.total_count == 0
