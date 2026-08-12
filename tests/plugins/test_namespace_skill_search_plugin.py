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

    def test_mixed_case_first_tag_collapses_to_one_namespace(self):
        """ "finance" and "Finance" must not fragment into two namespaces."""
        from code_puppy.plugins.namespace_skill_search.namespaces import (
            build_namespaces,
        )

        skills = [
            _skill("a", tags=["finance"]),
            _skill("b", tags=["Finance"]),
            _skill("c", tags=["FINANCE"]),
        ]
        with patch(_PATCH_TARGET, return_value=skills):
            namespaces = build_namespaces()

        assert len(namespaces) == 1
        (only_key,) = namespaces.keys()
        assert only_key == "finance"  # first-seen casing wins
        assert len(namespaces[only_key]) == 3

    def test_duplicate_skill_name_across_namespaces_is_not_deduped(self):
        """Documents current behavior: duplicates are surfaced, not merged
        or dropped -- see the warning line asserted in
        TestBuildNamespaceSummary.test_duplicate_names_are_flagged."""
        from code_puppy.plugins.namespace_skill_search.namespaces import (
            build_namespaces,
        )

        skills = [
            _skill("shared-name", tags=["finance"]),
            _skill("shared-name", tags=["ops"]),
        ]
        with patch(_PATCH_TARGET, return_value=skills):
            namespaces = build_namespaces()

        total = sum(len(v) for v in namespaces.values())
        assert total == 2


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

    def test_duplicate_names_are_flagged(self):
        from code_puppy.plugins.namespace_skill_search.namespaces import (
            build_namespace_summary,
        )

        skills = [
            _skill("shared-name", tags=["finance"]),
            _skill("shared-name", tags=["ops"]),
        ]
        with patch(_PATCH_TARGET, return_value=skills):
            summary = build_namespace_summary()

        assert "shared-name" in summary
        assert "ambiguous" in summary

    def test_unique_names_are_not_flagged(self):
        from code_puppy.plugins.namespace_skill_search.namespaces import (
            build_namespace_summary,
        )

        skills = [_skill("a", tags=["finance"]), _skill("b", tags=["ops"])]
        with patch(_PATCH_TARGET, return_value=skills):
            summary = build_namespace_summary()

        assert "ambiguous" not in summary


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

    @pytest.mark.asyncio
    async def test_search_mode_empty_string_query_means_no_filter(self):
        """query="" (explicit empty string) must return everything, not
        nothing -- distinct code path from query=None (mode 1/directory)."""
        from code_puppy.plugins.namespace_skill_search.search_tool import (
            register_browse_skill_namespace,
        )

        skills = [
            _skill("a", tags=["finance"]),
            _skill("b", tags=["ops"]),
        ]
        agent, cap = _make_agent()
        register_browse_skill_namespace(agent)
        ctx = MagicMock()

        with patch(_PATCH_TARGET, return_value=skills):
            result = await cap["fn"](ctx, query="")

        assert result.mode == "search"
        assert result.total_skills == 2

    @pytest.mark.asyncio
    async def test_catalog_read_failure_is_reported_not_raised(self):
        from code_puppy.plugins.namespace_skill_search.search_tool import (
            register_browse_skill_namespace,
        )

        agent, cap = _make_agent()
        register_browse_skill_namespace(agent)
        ctx = MagicMock()

        with patch(_PATCH_TARGET, side_effect=OSError("disk on fire")):
            result = await cap["fn"](ctx)

        assert result.mode == "directory"
        assert result.error is not None
        assert "disk on fire" in result.error


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


class TestMaybeDisableFrontmatter:
    """The frontmatter migration runs as a `startup` callback, not at
    import time, specifically so it's directly callable/testable like
    this -- see the design note in register_callbacks.py."""

    _CONFIG_MODULE = "code_puppy.plugins.namespace_skill_search.register_callbacks"

    def test_noop_if_already_migrated(self):
        from code_puppy.plugins.namespace_skill_search.register_callbacks import (
            _maybe_disable_frontmatter,
        )

        with (
            patch(f"{self._CONFIG_MODULE}.get_value", return_value="true"),
            patch(f"{self._CONFIG_MODULE}.get_frontmatter_in_system_prompt") as get_fm,
            patch(f"{self._CONFIG_MODULE}.set_frontmatter_in_system_prompt") as set_fm,
            patch(f"{self._CONFIG_MODULE}.set_config_value") as set_cfg,
        ):
            _maybe_disable_frontmatter()

        get_fm.assert_not_called()
        set_fm.assert_not_called()
        set_cfg.assert_not_called()

    def test_flips_frontmatter_off_on_first_run_when_currently_on(self):
        from code_puppy.plugins.namespace_skill_search.register_callbacks import (
            _maybe_disable_frontmatter,
            _MIGRATION_MARKER_KEY,
        )

        with (
            patch(f"{self._CONFIG_MODULE}.get_value", return_value=None),
            patch(
                f"{self._CONFIG_MODULE}.get_frontmatter_in_system_prompt",
                return_value=True,
            ),
            patch(f"{self._CONFIG_MODULE}.set_frontmatter_in_system_prompt") as set_fm,
            patch(f"{self._CONFIG_MODULE}.set_config_value") as set_cfg,
        ):
            _maybe_disable_frontmatter()

        set_fm.assert_called_once_with(False)
        set_cfg.assert_called_once_with(_MIGRATION_MARKER_KEY, "true")

    def test_records_marker_without_flipping_when_already_off(self):
        """If frontmatter is already False on first run, don't call
        set_frontmatter_in_system_prompt at all -- just record that this
        plugin has now run, so a later user opt-in is never fought."""
        from code_puppy.plugins.namespace_skill_search.register_callbacks import (
            _maybe_disable_frontmatter,
            _MIGRATION_MARKER_KEY,
        )

        with (
            patch(f"{self._CONFIG_MODULE}.get_value", return_value=None),
            patch(
                f"{self._CONFIG_MODULE}.get_frontmatter_in_system_prompt",
                return_value=False,
            ),
            patch(f"{self._CONFIG_MODULE}.set_frontmatter_in_system_prompt") as set_fm,
            patch(f"{self._CONFIG_MODULE}.set_config_value") as set_cfg,
        ):
            _maybe_disable_frontmatter()

        set_fm.assert_not_called()
        set_cfg.assert_called_once_with(_MIGRATION_MARKER_KEY, "true")

    def test_registered_on_startup_callback_not_import_time(self):
        """Static source check, deliberately not a reload-based test:
        reloading this module would re-run its *real* top-level
        `register_callback(...)` calls a second time against the live,
        process-wide callback registry (shared with every other test
        module in this session), which is exactly the kind of global-state
        pollution this plugin's design goes out of its way to avoid
        elsewhere (see the migration-marker rationale). A source-level
        assertion enforces the same invariant -- "the frontmatter flip is
        wired through the `startup` callback, not executed at module
        scope" -- without that risk.
        """
        import inspect

        import code_puppy.plugins.namespace_skill_search.register_callbacks as mod

        source = inspect.getsource(mod)
        assert 'register_callback("startup", _maybe_disable_frontmatter)' in source

        # The migration function must never be called bare at module scope — only
        # through the registry, never eagerly on import.
        for line in source.splitlines():
            stripped = line.strip()
            assert stripped != "_maybe_disable_frontmatter()"
