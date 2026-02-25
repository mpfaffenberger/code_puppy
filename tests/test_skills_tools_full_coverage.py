"""Full coverage tests for tools/skills_tools.py."""

from unittest.mock import MagicMock, patch

import pytest

from code_puppy.tools.skills_tools import (
    register_activate_skill,
    register_list_or_search_skills,
)


def _register_and_get(register_func):
    """Register tool on a mock agent and capture the inner function."""
    agent = MagicMock()
    captured = {}

    def tool_decorator(f):
        captured["fn"] = f
        return f

    agent.tool = tool_decorator
    register_func(agent)
    return captured["fn"]


class TestActivateSkill:
    @pytest.mark.anyio
    async def test_disabled(self):
        fn = _register_and_get(register_activate_skill)
        ctx = MagicMock()
        with patch(
            "code_puppy.plugins.agent_skills.config.get_skills_enabled",
            return_value=False,
        ):
            result = await fn(ctx, skill_name="test")
            assert result.error is not None
            assert "disabled" in result.error

    @pytest.mark.anyio
    async def test_discovery_error(self):
        fn = _register_and_get(register_activate_skill)
        ctx = MagicMock()
        with (
            patch(
                "code_puppy.plugins.agent_skills.config.get_skills_enabled",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.agent_skills.config.get_skill_directories",
                side_effect=Exception("boom"),
            ),
            patch(
                "code_puppy.plugins.agent_skills.discovery.discover_skills",
                side_effect=Exception("boom"),
            ),
        ):
            result = await fn(ctx, skill_name="test")
            assert result.error is not None

    @pytest.mark.anyio
    async def test_skill_not_found(self):
        fn = _register_and_get(register_activate_skill)
        ctx = MagicMock()
        with (
            patch(
                "code_puppy.plugins.agent_skills.config.get_skills_enabled",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.agent_skills.config.get_skill_directories",
                return_value=[],
            ),
            patch(
                "code_puppy.plugins.agent_skills.discovery.discover_skills",
                return_value=[],
            ),
        ):
            result = await fn(ctx, skill_name="nonexistent")
            assert "not found" in result.error

    @pytest.mark.anyio
    async def test_content_load_failure(self):
        fn = _register_and_get(register_activate_skill)
        ctx = MagicMock()
        mock_skill = MagicMock()
        mock_skill.name = "test"
        mock_skill.has_skill_md = True
        mock_skill.path = "/path"
        with (
            patch(
                "code_puppy.plugins.agent_skills.config.get_skills_enabled",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.agent_skills.config.get_skill_directories",
                return_value=[],
            ),
            patch(
                "code_puppy.plugins.agent_skills.discovery.discover_skills",
                return_value=[mock_skill],
            ),
            patch(
                "code_puppy.plugins.agent_skills.metadata.load_full_skill_content",
                return_value=None,
            ),
        ):
            result = await fn(ctx, skill_name="test")
            assert "Failed to load" in result.error

    @pytest.mark.anyio
    async def test_success(self):
        fn = _register_and_get(register_activate_skill)
        ctx = MagicMock()
        mock_skill = MagicMock()
        mock_skill.name = "test"
        mock_skill.has_skill_md = True
        mock_skill.path = "/path"
        with (
            patch(
                "code_puppy.plugins.agent_skills.config.get_skills_enabled",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.agent_skills.config.get_skill_directories",
                return_value=[],
            ),
            patch(
                "code_puppy.plugins.agent_skills.discovery.discover_skills",
                return_value=[mock_skill],
            ),
            patch(
                "code_puppy.plugins.agent_skills.metadata.load_full_skill_content",
                return_value="# Skill content",
            ),
            patch(
                "code_puppy.plugins.agent_skills.metadata.get_skill_resources",
                return_value=[],
            ),
            patch("code_puppy.tools.skills_tools.get_message_bus"),
        ):
            result = await fn(ctx, skill_name="test")
            assert result.error is None
            assert result.content == "# Skill content"


class TestListOrSearchSkills:
    @pytest.mark.anyio
    async def test_disabled(self):
        fn = _register_and_get(register_list_or_search_skills)
        ctx = MagicMock()
        with patch(
            "code_puppy.plugins.agent_skills.config.get_skills_enabled",
            return_value=False,
        ):
            result = await fn(ctx)
            assert result.error is not None

    @pytest.mark.anyio
    async def test_discovery_error(self):
        fn = _register_and_get(register_list_or_search_skills)
        ctx = MagicMock()
        with (
            patch(
                "code_puppy.plugins.agent_skills.config.get_skills_enabled",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.agent_skills.config.get_disabled_skills",
                return_value=set(),
            ),
            patch(
                "code_puppy.plugins.agent_skills.config.get_skill_directories",
                side_effect=Exception("boom"),
            ),
        ):
            result = await fn(ctx)
            assert result.error is not None

    @pytest.mark.anyio
    async def test_list_all(self):
        fn = _register_and_get(register_list_or_search_skills)
        ctx = MagicMock()
        mock_skill = MagicMock()
        mock_skill.name = "test"
        mock_skill.has_skill_md = True
        mock_skill.path = "/path"
        mock_meta = MagicMock()
        mock_meta.name = "test"
        mock_meta.description = "A test skill"
        mock_meta.path = "/path"
        mock_meta.tags = ["testing"]
        mock_meta.version = "1.0"
        mock_meta.author = "me"
        with (
            patch(
                "code_puppy.plugins.agent_skills.config.get_skills_enabled",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.agent_skills.config.get_disabled_skills",
                return_value=set(),
            ),
            patch(
                "code_puppy.plugins.agent_skills.config.get_skill_directories",
                return_value=[],
            ),
            patch(
                "code_puppy.plugins.agent_skills.discovery.discover_skills",
                return_value=[mock_skill],
            ),
            patch(
                "code_puppy.plugins.agent_skills.metadata.parse_skill_metadata",
                return_value=mock_meta,
            ),
            patch("code_puppy.tools.skills_tools.get_message_bus"),
        ):
            result = await fn(ctx)
            assert result.error is None
            assert result.total_count == 1

    @pytest.mark.anyio
    async def test_filter_by_query_name(self):
        fn = _register_and_get(register_list_or_search_skills)
        ctx = MagicMock()
        mock_skill = MagicMock()
        mock_skill.name = "weather"
        mock_skill.has_skill_md = True
        mock_skill.path = "/path"
        mock_meta = MagicMock()
        mock_meta.name = "weather"
        mock_meta.description = "Get weather"
        mock_meta.path = "/path"
        mock_meta.tags = []
        mock_meta.version = "1.0"
        mock_meta.author = "me"
        with (
            patch(
                "code_puppy.plugins.agent_skills.config.get_skills_enabled",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.agent_skills.config.get_disabled_skills",
                return_value=set(),
            ),
            patch(
                "code_puppy.plugins.agent_skills.config.get_skill_directories",
                return_value=[],
            ),
            patch(
                "code_puppy.plugins.agent_skills.discovery.discover_skills",
                return_value=[mock_skill],
            ),
            patch(
                "code_puppy.plugins.agent_skills.metadata.parse_skill_metadata",
                return_value=mock_meta,
            ),
            patch("code_puppy.tools.skills_tools.get_message_bus"),
        ):
            result = await fn(ctx, query="weath")
            assert result.total_count == 1

    @pytest.mark.anyio
    async def test_filter_by_query_description(self):
        fn = _register_and_get(register_list_or_search_skills)
        ctx = MagicMock()
        mock_skill = MagicMock()
        mock_skill.name = "x"
        mock_skill.has_skill_md = True
        mock_skill.path = "/path"
        mock_meta = MagicMock()
        mock_meta.name = "x"
        mock_meta.description = "Handles authentication"
        mock_meta.path = "/path"
        mock_meta.tags = []
        mock_meta.version = "1.0"
        mock_meta.author = "me"
        with (
            patch(
                "code_puppy.plugins.agent_skills.config.get_skills_enabled",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.agent_skills.config.get_disabled_skills",
                return_value=set(),
            ),
            patch(
                "code_puppy.plugins.agent_skills.config.get_skill_directories",
                return_value=[],
            ),
            patch(
                "code_puppy.plugins.agent_skills.discovery.discover_skills",
                return_value=[mock_skill],
            ),
            patch(
                "code_puppy.plugins.agent_skills.metadata.parse_skill_metadata",
                return_value=mock_meta,
            ),
            patch("code_puppy.tools.skills_tools.get_message_bus"),
        ):
            result = await fn(ctx, query="auth")
            assert result.total_count == 1

    @pytest.mark.anyio
    async def test_filter_by_query_tag(self):
        fn = _register_and_get(register_list_or_search_skills)
        ctx = MagicMock()
        mock_skill = MagicMock()
        mock_skill.name = "x"
        mock_skill.has_skill_md = True
        mock_skill.path = "/path"
        mock_meta = MagicMock()
        mock_meta.name = "x"
        mock_meta.description = "desc"
        mock_meta.path = "/path"
        mock_meta.tags = ["database"]
        mock_meta.version = "1.0"
        mock_meta.author = "me"
        with (
            patch(
                "code_puppy.plugins.agent_skills.config.get_skills_enabled",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.agent_skills.config.get_disabled_skills",
                return_value=set(),
            ),
            patch(
                "code_puppy.plugins.agent_skills.config.get_skill_directories",
                return_value=[],
            ),
            patch(
                "code_puppy.plugins.agent_skills.discovery.discover_skills",
                return_value=[mock_skill],
            ),
            patch(
                "code_puppy.plugins.agent_skills.metadata.parse_skill_metadata",
                return_value=mock_meta,
            ),
            patch("code_puppy.tools.skills_tools.get_message_bus"),
        ):
            result = await fn(ctx, query="database")
            assert result.total_count == 1

    @pytest.mark.anyio
    async def test_filter_no_match(self):
        fn = _register_and_get(register_list_or_search_skills)
        ctx = MagicMock()
        mock_skill = MagicMock()
        mock_skill.name = "x"
        mock_skill.has_skill_md = True
        mock_skill.path = "/path"
        mock_meta = MagicMock()
        mock_meta.name = "x"
        mock_meta.description = "desc"
        mock_meta.path = "/path"
        mock_meta.tags = []
        mock_meta.version = "1.0"
        mock_meta.author = "me"
        with (
            patch(
                "code_puppy.plugins.agent_skills.config.get_skills_enabled",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.agent_skills.config.get_disabled_skills",
                return_value=set(),
            ),
            patch(
                "code_puppy.plugins.agent_skills.config.get_skill_directories",
                return_value=[],
            ),
            patch(
                "code_puppy.plugins.agent_skills.discovery.discover_skills",
                return_value=[mock_skill],
            ),
            patch(
                "code_puppy.plugins.agent_skills.metadata.parse_skill_metadata",
                return_value=mock_meta,
            ),
            patch("code_puppy.tools.skills_tools.get_message_bus"),
        ):
            result = await fn(ctx, query="zzzzz")
            assert result.total_count == 0

    @pytest.mark.anyio
    async def test_skip_disabled_and_no_skill_md(self):
        fn = _register_and_get(register_list_or_search_skills)
        ctx = MagicMock()
        disabled_skill = MagicMock()
        disabled_skill.name = "disabled_one"
        disabled_skill.has_skill_md = True
        no_md_skill = MagicMock()
        no_md_skill.name = "no_md"
        no_md_skill.has_skill_md = False
        with (
            patch(
                "code_puppy.plugins.agent_skills.config.get_skills_enabled",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.agent_skills.config.get_disabled_skills",
                return_value={"disabled_one"},
            ),
            patch(
                "code_puppy.plugins.agent_skills.config.get_skill_directories",
                return_value=[],
            ),
            patch(
                "code_puppy.plugins.agent_skills.discovery.discover_skills",
                return_value=[disabled_skill, no_md_skill],
            ),
            patch("code_puppy.tools.skills_tools.get_message_bus"),
        ):
            result = await fn(ctx)
            assert result.total_count == 0

    @pytest.mark.anyio
    async def test_skip_none_metadata(self):
        fn = _register_and_get(register_list_or_search_skills)
        ctx = MagicMock()
        mock_skill = MagicMock()
        mock_skill.name = "x"
        mock_skill.has_skill_md = True
        mock_skill.path = "/path"
        with (
            patch(
                "code_puppy.plugins.agent_skills.config.get_skills_enabled",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.agent_skills.config.get_disabled_skills",
                return_value=set(),
            ),
            patch(
                "code_puppy.plugins.agent_skills.config.get_skill_directories",
                return_value=[],
            ),
            patch(
                "code_puppy.plugins.agent_skills.discovery.discover_skills",
                return_value=[mock_skill],
            ),
            patch(
                "code_puppy.plugins.agent_skills.metadata.parse_skill_metadata",
                return_value=None,
            ),
            patch("code_puppy.tools.skills_tools.get_message_bus"),
        ):
            result = await fn(ctx)
            assert result.total_count == 0
