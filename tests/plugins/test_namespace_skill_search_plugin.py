"""Tests for the namespace_skill_search plugin."""

from __future__ import annotations

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


def _skill(name, description="desc", tags=None):
    meta = MagicMock()
    meta.name = name
    meta.description = description
    meta.tags = tags or []
    return meta


_PATCH_TARGET = (
    "code_puppy.plugins.namespace_skill_search.namespaces.list_enabled_skill_metadata"
)


class TestBuildNamespaces:
    def test_empty_when_no_skills(self):
        from code_puppy.plugins.namespace_skill_search.namespaces import (
            build_namespaces,
        )

        with patch(_PATCH_TARGET, return_value=[]):
            assert build_namespaces() == {}

    def test_groups_by_first_tag(self):
        from code_puppy.plugins.namespace_skill_search.namespaces import (
            build_namespaces,
        )

        skills = [
            _skill("a", tags=["finance", "sales"]),
            _skill("b", tags=["finance"]),
            _skill("c", tags=["ops"]),
        ]
        with patch(_PATCH_TARGET, return_value=skills):
            namespaces = build_namespaces()

        assert set(namespaces.keys()) == {"finance", "ops"}
        assert len(namespaces["finance"]) == 2
        assert len(namespaces["ops"]) == 1

    def test_untagged_skill_lands_in_general(self):
        from code_puppy.plugins.namespace_skill_search.namespaces import (
            build_namespaces,
        )

        with patch(_PATCH_TARGET, return_value=[_skill("untagged", tags=[])]):
            namespaces = build_namespaces()

        assert list(namespaces.keys()) == ["General"]

    def test_blank_first_tag_falls_back_to_general(self):
        from code_puppy.plugins.namespace_skill_search.namespaces import (
            build_namespaces,
        )

        with patch(_PATCH_TARGET, return_value=[_skill("blank", tags=["  "])]):
            namespaces = build_namespaces()

        assert list(namespaces.keys()) == ["General"]


class TestBuildNamespaceSummary:
    def test_none_when_no_skills(self):
        from code_puppy.plugins.namespace_skill_search.namespaces import (
            build_namespace_summary,
        )

        with patch(_PATCH_TARGET, return_value=[]):
            assert build_namespace_summary() is None

    def test_summary_contains_namespace_and_count(self):
        from code_puppy.plugins.namespace_skill_search.namespaces import (
            build_namespace_summary,
        )

        skills = [_skill("a", tags=["finance"]), _skill("b", tags=["finance"])]
        with patch(_PATCH_TARGET, return_value=skills):
            summary = build_namespace_summary()

        assert "finance" in summary.lower()
        assert "2 skills available across 1 namespaces" in summary
        assert "browse_skill_namespace" in summary

    def test_oversized_namespace_is_flagged(self):
        from code_puppy.plugins.namespace_skill_search.namespaces import (
            build_namespace_summary,
        )

        skills = [_skill(f"s{i}", tags=["huge"]) for i in range(11)]
        with patch(_PATCH_TARGET, return_value=skills):
            summary = build_namespace_summary()

        assert "oversized namespace" in summary

    def test_small_namespace_is_not_flagged(self):
        from code_puppy.plugins.namespace_skill_search.namespaces import (
            build_namespace_summary,
        )

        skills = [_skill("solo", tags=["tiny"])]
        with patch(_PATCH_TARGET, return_value=skills):
            summary = build_namespace_summary()

        assert "oversized namespace" not in summary


class TestBrowseSkillNamespace:
    @pytest.mark.asyncio
    async def test_no_skills_returns_error(self):
        from code_puppy.plugins.namespace_skill_search.search_tool import (
            register_browse_skill_namespace,
        )

        agent, cap = _make_agent()
        register_browse_skill_namespace(agent)
        ctx = MagicMock()

        with patch(_PATCH_TARGET, return_value=[]):
            result = await cap["fn"](ctx)

        assert result.mode == "directory"
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_directory_mode_lists_namespaces(self):
        from code_puppy.plugins.namespace_skill_search.search_tool import (
            register_browse_skill_namespace,
        )

        skills = [_skill("a", tags=["finance"]), _skill("b", tags=["ops"])]
        agent, cap = _make_agent()
        register_browse_skill_namespace(agent)
        ctx = MagicMock()

        with patch(_PATCH_TARGET, return_value=skills):
            result = await cap["fn"](ctx)

        assert result.mode == "directory"
        assert set(result.namespaces) == {"finance", "ops"}
        assert result.total_skills == 2

    @pytest.mark.asyncio
    async def test_namespace_mode_lists_matching_skills(self):
        from code_puppy.plugins.namespace_skill_search.search_tool import (
            register_browse_skill_namespace,
        )

        skills = [
            _skill("a", description="alpha", tags=["finance"]),
            _skill("b", description="beta", tags=["ops"]),
        ]
        agent, cap = _make_agent()
        register_browse_skill_namespace(agent)
        ctx = MagicMock()

        with patch(_PATCH_TARGET, return_value=skills):
            result = await cap["fn"](ctx, namespace="finance")

        assert result.mode == "namespace"
        assert result.total_skills == 1
        assert result.skills[0]["name"] == "a"

    @pytest.mark.asyncio
    async def test_namespace_mode_is_case_insensitive(self):
        from code_puppy.plugins.namespace_skill_search.search_tool import (
            register_browse_skill_namespace,
        )

        skills = [_skill("a", tags=["Finance"])]
        agent, cap = _make_agent()
        register_browse_skill_namespace(agent)
        ctx = MagicMock()

        with patch(_PATCH_TARGET, return_value=skills):
            result = await cap["fn"](ctx, namespace="finance")

        assert result.total_skills == 1

    @pytest.mark.asyncio
    async def test_namespace_mode_unknown_namespace_errors(self):
        from code_puppy.plugins.namespace_skill_search.search_tool import (
            register_browse_skill_namespace,
        )

        skills = [_skill("a", tags=["finance"])]
        agent, cap = _make_agent()
        register_browse_skill_namespace(agent)
        ctx = MagicMock()

        with patch(_PATCH_TARGET, return_value=skills):
            result = await cap["fn"](ctx, namespace="nonexistent")

        assert result.mode == "namespace"
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_namespace_mode_with_query_filters_further(self):
        from code_puppy.plugins.namespace_skill_search.search_tool import (
            register_browse_skill_namespace,
        )

        skills = [
            _skill(
                "variance-analysis", description="variance reporting", tags=["finance"]
            ),
            _skill("gl-daily", description="general ledger", tags=["finance"]),
        ]
        agent, cap = _make_agent()
        register_browse_skill_namespace(agent)
        ctx = MagicMock()

        with patch(_PATCH_TARGET, return_value=skills):
            result = await cap["fn"](ctx, namespace="finance", query="variance")

        assert result.total_skills == 1
        assert result.skills[0]["name"] == "variance-analysis"

    @pytest.mark.asyncio
    async def test_search_mode_matches_across_namespaces(self):
        from code_puppy.plugins.namespace_skill_search.search_tool import (
            register_browse_skill_namespace,
        )

        skills = [
            _skill("a", description="handles variance", tags=["finance"]),
            _skill("b", description="handles deploys", tags=["ops"]),
        ]
        agent, cap = _make_agent()
        register_browse_skill_namespace(agent)
        ctx = MagicMock()

        with patch(_PATCH_TARGET, return_value=skills):
            result = await cap["fn"](ctx, query="variance")

        assert result.mode == "search"
        assert result.total_skills == 1
        assert result.skills[0]["name"] == "a"
        assert result.skills[0]["namespace"] == "finance"

    @pytest.mark.asyncio
    async def test_search_mode_no_match(self):
        from code_puppy.plugins.namespace_skill_search.search_tool import (
            register_browse_skill_namespace,
        )

        skills = [_skill("a", description="handles variance", tags=["finance"])]
        agent, cap = _make_agent()
        register_browse_skill_namespace(agent)
        ctx = MagicMock()

        with patch(_PATCH_TARGET, return_value=skills):
            result = await cap["fn"](ctx, query="zzzzz-nomatch")

        assert result.mode == "search"
        assert result.total_skills == 0


class TestRegisterCallbacksModule:
    def test_register_tools_returns_browse_skill_namespace(self):
        from code_puppy.plugins.namespace_skill_search.register_callbacks import (
            _register_tools,
        )

        tools = _register_tools()
        assert tools[0]["name"] == "browse_skill_namespace"

    def test_advertise_to_all_agents(self):
        from code_puppy.plugins.namespace_skill_search.register_callbacks import (
            _advertise_to_all_agents,
        )

        assert _advertise_to_all_agents() == ["browse_skill_namespace"]
        assert _advertise_to_all_agents(agent_name="anything") == [
            "browse_skill_namespace"
        ]

    def test_on_load_prompt_delegates_to_namespace_summary(self):
        from code_puppy.plugins.namespace_skill_search.register_callbacks import (
            _on_load_prompt,
        )

        with patch(_PATCH_TARGET, return_value=[]):
            assert _on_load_prompt() is None

        with patch(_PATCH_TARGET, return_value=[_skill("a", tags=["x"])]):
            assert "Skill Namespaces" in _on_load_prompt()
