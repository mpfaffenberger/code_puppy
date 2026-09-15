"""Coverage and seam tests for the optional skills tools."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.tools.skills_tools import (
    register_activate_skill,
    register_list_or_search_skills,
)


def _register_and_get(register_func):
    agent = MagicMock()
    captured = {}

    def tool_decorator(func):
        captured["fn"] = func
        return func

    agent.tool = tool_decorator
    register_func(agent)
    return captured["fn"]


@pytest.fixture
def provider():
    result = MagicMock()
    result.is_enabled.return_value = True
    result.get_disabled_skill_names.return_value = set()
    result.list_enabled_skills.return_value = []
    result.find_enabled_skill_path.return_value = None
    result.load_skill_content.return_value = None
    result.get_skill_resources.return_value = []
    return result


class TestActivateSkill:
    @pytest.mark.anyio
    async def test_no_plugin(self):
        fn = _register_and_get(register_activate_skill)
        with patch(
            "code_puppy.tools.skills_tools.get_skill_provider", return_value=None
        ):
            result = await fn(MagicMock(), skill_name="test")
        assert result.error == "Skills integration is unavailable."

    @pytest.mark.anyio
    async def test_globally_disabled(self, provider):
        fn = _register_and_get(register_activate_skill)
        provider.is_enabled.return_value = False
        with patch(
            "code_puppy.tools.skills_tools.get_skill_provider", return_value=provider
        ):
            result = await fn(MagicMock(), skill_name="test")
        assert "disabled" in result.error

    @pytest.mark.anyio
    async def test_discovery_error(self, provider):
        fn = _register_and_get(register_activate_skill)
        provider.find_enabled_skill_path.side_effect = RuntimeError("boom")
        with patch(
            "code_puppy.tools.skills_tools.get_skill_provider", return_value=provider
        ):
            result = await fn(MagicMock(), skill_name="test")
        assert result.error == "Failed to discover skills: boom"

    @pytest.mark.anyio
    async def test_skill_not_found(self, provider):
        fn = _register_and_get(register_activate_skill)
        with patch(
            "code_puppy.tools.skills_tools.get_skill_provider", return_value=provider
        ):
            result = await fn(MagicMock(), skill_name="missing")
        assert "not found or disabled" in result.error

    @pytest.mark.anyio
    async def test_content_load_failure(self, provider):
        fn = _register_and_get(register_activate_skill)
        provider.find_enabled_skill_path.return_value = Path("/skill")
        with patch(
            "code_puppy.tools.skills_tools.get_skill_provider", return_value=provider
        ):
            result = await fn(MagicMock(), skill_name="test")
        assert result.error == "Failed to load content for skill 'test'"

    @pytest.mark.anyio
    async def test_success(self, provider):
        fn = _register_and_get(register_activate_skill)
        provider.find_enabled_skill_path.return_value = Path("/skill")
        provider.load_skill_content.return_value = "# Skill content"
        provider.get_skill_resources.return_value = [Path("/skill/reference.md")]
        with (
            patch(
                "code_puppy.tools.skills_tools.get_skill_provider",
                return_value=provider,
            ),
            patch("code_puppy.tools.skills_tools.get_message_bus") as bus,
        ):
            result = await fn(MagicMock(), skill_name="test")
        assert result.error is None
        assert result.content == "# Skill content"
        assert result.resources == ["/skill/reference.md"]
        bus.return_value.emit.assert_called_once()


class TestListOrSearchSkills:
    @pytest.mark.anyio
    async def test_no_plugin(self):
        fn = _register_and_get(register_list_or_search_skills)
        with patch(
            "code_puppy.tools.skills_tools.get_skill_provider", return_value=None
        ):
            result = await fn(MagicMock())
        assert result.error == "Skills integration is unavailable."

    @pytest.mark.anyio
    async def test_globally_disabled(self, provider):
        fn = _register_and_get(register_list_or_search_skills)
        provider.is_enabled.return_value = False
        with patch(
            "code_puppy.tools.skills_tools.get_skill_provider", return_value=provider
        ):
            result = await fn(MagicMock())
        assert "disabled" in result.error

    @pytest.mark.anyio
    async def test_discovery_error(self, provider):
        fn = _register_and_get(register_list_or_search_skills)
        provider.list_enabled_skills.side_effect = RuntimeError("boom")
        with patch(
            "code_puppy.tools.skills_tools.get_skill_provider", return_value=provider
        ):
            result = await fn(MagicMock())
        assert result.error == "Failed to discover skills: boom"

    @pytest.mark.anyio
    async def test_list_all(self, provider):
        fn = _register_and_get(register_list_or_search_skills)
        provider.list_enabled_skills.return_value = [
            {
                "name": "test",
                "description": "A test skill",
                "path": "/skill",
                "tags": ["testing"],
                "version": "1.0",
                "author": "me",
            }
        ]
        with (
            patch(
                "code_puppy.tools.skills_tools.get_skill_provider",
                return_value=provider,
            ),
            patch("code_puppy.tools.skills_tools.get_message_bus") as bus,
        ):
            result = await fn(MagicMock())
        assert result.error is None
        assert result.total_count == 1
        assert result.skills[0]["name"] == "test"
        bus.return_value.emit.assert_called_once()

    @pytest.mark.parametrize(
        "name,description,tags,query,expected_count",
        [
            ("weather", "Get weather", [], "weath", 1),
            ("x", "Handles authentication", [], "auth", 1),
            ("x", "desc", ["database"], "database", 1),
            ("x", "desc", [], "zzzzz", 0),
            ("code-puppy", "architecture", [], "code puppy architecture", 1),
        ],
    )
    @pytest.mark.anyio
    async def test_filter_by_query(
        self, provider, name, description, tags, query, expected_count
    ):
        fn = _register_and_get(register_list_or_search_skills)
        provider.list_enabled_skills.return_value = [
            {
                "name": name,
                "description": description,
                "path": "/skill",
                "tags": tags,
                "version": None,
                "author": None,
            }
        ]
        with (
            patch(
                "code_puppy.tools.skills_tools.get_skill_provider",
                return_value=provider,
            ),
            patch("code_puppy.tools.skills_tools.get_message_bus"),
        ):
            result = await fn(MagicMock(), query=query)
        assert result.total_count == expected_count
