"""Tests for the Auto Skill Activator plugin — background steering model approach.

Tests verify that:
1. Skills are auto-activated when the steering model scores them above threshold
2. Skills are NOT activated when the steering model scores them below threshold
3. Multiple matching skills are ranked by score, capped at MAX_AUTO_ACTIVATE
4. Disabled skills are never auto-activated
5. Plugin degrades gracefully on errors (falls back to fuzzy matching)
6. The `handled: False` flag is always set so other handlers still run
7. Compaction re-injection resets state when skills are stripped
8. Fuzzy fallback works when steering model is unavailable
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_skill_info(name: str, has_skill_md: bool = True) -> MagicMock:
    info = MagicMock()
    info.name = name
    info.has_skill_md = has_skill_md
    info.path = Path(f"/fake/skills/{name}")
    return info


def make_metadata(name: str, description: str, tags: list[str] | None = None) -> MagicMock:
    meta = MagicMock()
    meta.name = name
    meta.description = description
    meta.tags = tags or []
    return meta


def make_llm_response(scores: list[dict[str, Any]]) -> str:
    """Build a mock LLM JSON response for skill scoring."""
    return json.dumps(scores)


# ---------------------------------------------------------------------------
# Import target
# ---------------------------------------------------------------------------

from code_puppy.plugins.auto_skill_activator.register_callbacks import (
    AUTO_ACTIVATE_THRESHOLD,
    MAX_AUTO_ACTIVATE,
    _auto_inject_skills,
    _fuzzy_score,
    _on_message_history_processor_end,
    _score_skills_with_fuzz,
    _score_skills_with_llm,
)


# ---------------------------------------------------------------------------
# Unit: _fuzzy_score (fallback)
# ---------------------------------------------------------------------------

class TestFuzzyScore:
    def test_exact_match_scores_high(self):
        score = _fuzzy_score("deploy docker container", "deploy docker container")
        assert score >= 90

    def test_synonym_scores_above_threshold(self):
        score = _fuzzy_score(
            "deploy my docker container", "deploy docker container deployment"
        )
        assert score >= AUTO_ACTIVATE_THRESHOLD

    def test_unrelated_scores_low(self):
        score = _fuzzy_score(
            "what is the weather today", "github pull request workflow"
        )
        assert score < AUTO_ACTIVATE_THRESHOLD

    def test_empty_prompt_scores_zero(self):
        score = _fuzzy_score("", "github pull request workflow")
        assert score == 0 or score < AUTO_ACTIVATE_THRESHOLD

    def test_case_insensitive(self):
        score_lower = _fuzzy_score("github pr", "GitHub Pull Request")
        score_upper = _fuzzy_score("GITHUB PR", "github pull request")
        assert abs(score_lower - score_upper) <= 5


# ---------------------------------------------------------------------------
# Unit: _score_skills_with_fuzz
# ---------------------------------------------------------------------------

class TestScoreSkillsWithFuzz:
    def test_returns_list_of_scored_skills(self):
        skills = [
            {"name": "github-pr", "description": "GitHub pull request workflow"},
            {"name": "baking", "description": "Bake bread cooking recipe"},
        ]
        result = _score_skills_with_fuzz("create a pull request", skills)
        assert len(result) == 2
        assert all("name" in r and "score" in r for r in result)

    def test_matching_skill_scores_higher(self):
        skills = [
            {"name": "github-pr", "description": "GitHub pull request workflow"},
            {"name": "baking", "description": "Bake bread cooking recipe"},
        ]
        result = _score_skills_with_fuzz("create a pull request", skills)
        github_score = next(r["score"] for r in result if r["name"] == "github-pr")
        baking_score = next(r["score"] for r in result if r["name"] == "baking")
        assert github_score > baking_score

    def test_empty_skills_returns_empty(self):
        result = _score_skills_with_fuzz("create a pull request", [])
        assert result == []


# ---------------------------------------------------------------------------
# Unit: _score_skills_with_llm
# ---------------------------------------------------------------------------

class TestScoreSkillsWithLLM:
    def test_parses_llm_json_response(self):
        skills = [
            {"name": "github-pr", "description": "GitHub pull request workflow"},
            {"name": "baking", "description": "Bake bread cooking recipe"},
        ]
        mock_response = make_llm_response([
            {"name": "github-pr", "score": 92},
            {"name": "baking", "score": 15},
        ])

        with patch(
            "code_puppy.plugins.auto_skill_activator.register_callbacks.ModelFactory"
        ) as mock_factory, patch(
            "code_puppy.plugins.auto_skill_activator.register_callbacks._get_steering_model_name",
            return_value="claude-haiku-4",
        ):
            mock_model = MagicMock()
            mock_factory.get_model.return_value = mock_model
            mock_factory.load_config.return_value = {}

            with patch("pydantic_ai.Agent") as mock_agent_cls:
                mock_agent = MagicMock()
                mock_result = MagicMock()
                mock_result.data = mock_response
                mock_agent.run.return_value = mock_result
                mock_agent_cls.return_value = mock_agent

                with patch("asyncio.get_running_loop", side_effect=RuntimeError):
                    with patch("asyncio.run", return_value=mock_result):
                        result = _score_skills_with_llm("create a PR", skills)

        assert len(result) == 2
        assert result[0]["name"] == "github-pr"
        assert result[0]["score"] == 92

    def test_falls_back_to_fuzz_on_llm_failure(self):
        skills = [
            {"name": "github-pr", "description": "GitHub pull request workflow"},
        ]
        with patch(
            "code_puppy.plugins.auto_skill_activator.register_callbacks.ModelFactory"
        ) as mock_factory:
            mock_factory.get_model.return_value = None  # Model unavailable
            mock_factory.load_config.return_value = {}

            with patch(
                "code_puppy.plugins.auto_skill_activator.register_callbacks._get_steering_model_name",
                return_value="claude-haiku-4",
            ):
                result = _score_skills_with_llm("create a PR", skills)

        # Should fall back to fuzzy scoring
        assert len(result) == 1
        assert result[0]["name"] == "github-pr"
        assert result[0]["score"] >= 0

    def test_falls_back_on_bad_json(self):
        skills = [
            {"name": "github-pr", "description": "GitHub pull request workflow"},
        ]
        with patch(
            "code_puppy.plugins.auto_skill_activator.register_callbacks.ModelFactory"
        ) as mock_factory, patch(
            "code_puppy.plugins.auto_skill_activator.register_callbacks._get_steering_model_name",
            return_value="claude-haiku-4",
        ):
            mock_model = MagicMock()
            mock_factory.get_model.return_value = mock_model
            mock_factory.load_config.return_value = {}

            with patch("pydantic_ai.Agent") as mock_agent_cls:
                mock_agent = MagicMock()
                mock_result = MagicMock()
                mock_result.data = "not valid json"
                mock_agent.run.return_value = mock_result
                mock_agent_cls.return_value = mock_agent

                with patch("asyncio.get_running_loop", side_effect=RuntimeError):
                    with patch("asyncio.run", return_value=mock_result):
                        result = _score_skills_with_llm("create a PR", skills)

        # Should fall back to fuzzy scoring
        assert len(result) == 1
        assert result[0]["name"] == "github-pr"

    def test_empty_skills_returns_empty(self):
        result = _score_skills_with_llm("create a PR", [])
        assert result == []


# ---------------------------------------------------------------------------
# Unit: _auto_inject_skills
# ---------------------------------------------------------------------------

class TestAutoInjectSkills:
    """Tests for the main callback function."""

    def _run(
        self,
        user_prompt: str,
        skills_enabled: bool = True,
        discovered: list | None = None,
        disabled: set | None = None,
        skill_contents: dict | None = None,
        metadata_map: dict | None = None,
        llm_scores: list[dict] | None = None,
    ):
        """Helper to run _auto_inject_skills with mocked dependencies."""
        discovered = discovered or []
        disabled = disabled or set()
        skill_contents = skill_contents or {}
        metadata_map = metadata_map or {}

        # Default LLM scores: use fuzzy fallback
        if llm_scores is None:
            # Mock _score_skills_with_llm to return the fuzzy scores
            pass

        with (
            patch(
                "code_puppy.plugins.agent_skills.config.get_skills_enabled",
                return_value=skills_enabled,
            ),
            patch(
                "code_puppy.plugins.agent_skills.config.get_skill_directories",
                return_value=["/fake/skills"],
            ),
            patch(
                "code_puppy.plugins.agent_skills.config.get_disabled_skills",
                return_value=disabled,
            ),
            patch(
                "code_puppy.plugins.agent_skills.discovery.discover_skills",
                return_value=discovered,
            ),
            patch(
                "code_puppy.plugins.agent_skills.metadata.parse_skill_metadata",
                side_effect=lambda path: metadata_map.get(path.name),
            ),
            patch(
                "code_puppy.plugins.agent_skills.metadata.load_full_skill_content",
                side_effect=lambda path: skill_contents.get(path.name),
            ),
            patch(
                "code_puppy.plugins.auto_skill_activator.register_callbacks._score_skills_with_llm",
                return_value=llm_scores or [],
            ),
        ):
            return _auto_inject_skills("gpt-4o", "BASE SYSTEM PROMPT", user_prompt)

    # --- Basic activation ---

    def test_matching_skill_is_injected(self):
        skill = make_skill_info("github-pr")
        meta = make_metadata("github-pr", "GitHub pull request workflow create branch review")
        result = self._run(
            user_prompt="help me create a pull request on github",
            discovered=[skill],
            metadata_map={"github-pr": meta},
            skill_contents={"github-pr": "# GitHub PR Skill\nSteps: ..."},
            llm_scores=[{"name": "github-pr", "score": 92}],
        )
        assert result is not None
        assert "Auto-Activated Skill: github-pr" in result["instructions"]
        assert "GitHub PR Skill" in result["instructions"]
        assert "BASE SYSTEM PROMPT" in result["instructions"]

    def test_unrelated_prompt_returns_none(self):
        skill = make_skill_info("github-pr")
        meta = make_metadata("github-pr", "GitHub pull request workflow create branch review")
        result = self._run(
            user_prompt="what is the capital of France",
            discovered=[skill],
            metadata_map={"github-pr": meta},
            skill_contents={"github-pr": "# GitHub PR Skill\n..."},
            llm_scores=[{"name": "github-pr", "score": 20}],
        )
        assert result is None

    def test_empty_prompt_returns_none(self):
        result = self._run(user_prompt="")
        assert result is None

    def test_whitespace_prompt_returns_none(self):
        result = self._run(user_prompt="   ")
        assert result is None

    # --- Skills disabled ---

    def test_skills_globally_disabled_returns_none(self):
        skill = make_skill_info("github-pr")
        meta = make_metadata("github-pr", "GitHub pull request workflow")
        result = self._run(
            user_prompt="create a pull request",
            skills_enabled=False,
            discovered=[skill],
            metadata_map={"github-pr": meta},
            skill_contents={"github-pr": "# GitHub PR Skill"},
            llm_scores=[{"name": "github-pr", "score": 90}],
        )
        assert result is None

    def test_disabled_skill_not_activated(self):
        skill = make_skill_info("github-pr")
        meta = make_metadata("github-pr", "GitHub pull request workflow create branch review")
        result = self._run(
            user_prompt="help me create a pull request on github",
            discovered=[skill],
            disabled={"github-pr"},
            metadata_map={"github-pr": meta},
            skill_contents={"github-pr": "# GitHub PR Skill"},
            llm_scores=[{"name": "github-pr", "score": 90}],
        )
        assert result is None

    def test_skill_without_skill_md_skipped(self):
        skill = make_skill_info("broken-skill", has_skill_md=False)
        result = self._run(
            user_prompt="help me create a pull request on github",
            discovered=[skill],
        )
        assert result is None

    # --- Multiple skills, ranking and cap ---

    def test_top_n_skills_activated_by_score(self):
        skills = [make_skill_info(f"skill-{i}") for i in range(5)]
        metadata_map = {
            "skill-0": make_metadata("skill-0", "github pull request code review workflow"),
            "skill-1": make_metadata("skill-1", "bake bread cooking recipe"),
            "skill-2": make_metadata("skill-2", "github PR branch merge review"),
            "skill-3": make_metadata("skill-3", "database sql query optimization"),
            "skill-4": make_metadata("skill-4", "github issues tracker bug report"),
        }
        skill_contents = {f"skill-{i}": f"# Skill {i} Content" for i in range(5)}
        llm_scores = [
            {"name": "skill-0", "score": 95},
            {"name": "skill-1", "score": 10},
            {"name": "skill-2", "score": 88},
            {"name": "skill-3", "score": 15},
            {"name": "skill-4", "score": 72},
        ]

        result = self._run(
            user_prompt="create a github pull request and review the code",
            discovered=skills,
            metadata_map=metadata_map,
            skill_contents=skill_contents,
            llm_scores=llm_scores,
        )
        assert result is not None
        # Cooking/database/unrelated skills should NOT be injected
        assert "bake bread" not in result["instructions"]
        assert "sql query" not in result["instructions"]

    def test_max_auto_activate_cap_respected(self):
        n = MAX_AUTO_ACTIVATE + 2
        skills = [make_skill_info(f"skill-{i}") for i in range(n)]
        metadata_map = {
            f"skill-{i}": make_metadata(
                f"skill-{i}", "github pull request workflow review branch merge"
            )
            for i in range(n)
        }
        skill_contents = {f"skill-{i}": f"# Skill {i} Content" for i in range(n)}
        llm_scores = [
            {"name": f"skill-{i}", "score": 90 - i} for i in range(n)
        ]

        result = self._run(
            user_prompt="create a github pull request and review the code",
            discovered=skills,
            metadata_map=metadata_map,
            skill_contents=skill_contents,
            llm_scores=llm_scores,
        )
        assert result is not None
        # Count how many were injected
        injected_count = result["instructions"].count("Auto-Activated Skill:")
        assert injected_count <= MAX_AUTO_ACTIVATE

    # --- Return structure ---

    def test_handled_is_always_false(self):
        """handled=False ensures claude-code and other handlers still run."""
        skill = make_skill_info("github-pr")
        meta = make_metadata("github-pr", "GitHub pull request workflow create branch review")
        result = self._run(
            user_prompt="help me create a pull request on github",
            discovered=[skill],
            metadata_map={"github-pr": meta},
            skill_contents={"github-pr": "# GitHub PR Skill"},
            llm_scores=[{"name": "github-pr", "score": 90}],
        )
        assert result is not None
        assert result["handled"] is False

    def test_user_prompt_preserved_in_result(self):
        skill = make_skill_info("github-pr")
        meta = make_metadata("github-pr", "GitHub pull request workflow create branch review")
        user_prompt = "help me create a pull request on github"
        result = self._run(
            user_prompt=user_prompt,
            discovered=[skill],
            metadata_map={"github-pr": meta},
            skill_contents={"github-pr": "# GitHub PR Skill"},
            llm_scores=[{"name": "github-pr", "score": 90}],
        )
        assert result is not None
        assert result["user_prompt"] == user_prompt

    # --- Error resilience ---

    def test_exception_in_skill_discovery_returns_none(self):
        with patch(
            "code_puppy.plugins.agent_skills.config.get_skills_enabled",
            return_value=True,
        ), patch(
            "code_puppy.plugins.agent_skills.config.get_skill_directories",
            return_value=["/fake/skills"],
        ), patch(
            "code_puppy.plugins.agent_skills.config.get_disabled_skills",
            side_effect=RuntimeError("Config unavailable"),
        ):
            result = _auto_inject_skills("gpt-4o", "BASE PROMPT", "create a pull request")
            assert result is None

    def test_no_skills_discovered_returns_none(self):
        result = self._run(
            user_prompt="create a github pull request",
            discovered=[],
        )
        assert result is None


# ---------------------------------------------------------------------------
# Unit: _on_message_history_processor_end (compaction re-injection)
# ---------------------------------------------------------------------------

class TestCompactionReInjection:
    """Tests for the compaction re-injection hook."""

    def test_resets_state_when_skills_stripped(self):
        """When compaction removes skill content, state should be reset."""
        import code_puppy.plugins.auto_skill_activator.register_callbacks as mod

        # Set up state as if skills were previously activated
        mod._last_activated_skills = ["github-pr", "docker-deploy"]
        mod._last_user_prompt = "help me create a PR"

        # Message history WITHOUT the skill markers (compacted away)
        history = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "help me create a PR"},
        ]

        _on_message_history_processor_end(
            agent_name="code-puppy",
            session_id="test-session",
            message_history=history,
            messages_added=1,
            messages_filtered=0,
        )

        # State should be reset so next prompt re-evaluates
        assert mod._last_activated_skills == []
        assert mod._last_user_prompt == ""

    def test_no_reset_when_skills_still_present(self):
        """When skills are still in history after compaction, state persists."""
        import code_puppy.plugins.auto_skill_activator.register_callbacks as mod

        mod._last_activated_skills = ["github-pr"]
        mod._last_user_prompt = "help me create a PR"

        # Message history WITH the skill marker still present
        history = [
            {"role": "system", "content": "Auto-Activated Skill: github-pr\n# GitHub PR Skill"},
            {"role": "user", "content": "help me create a PR"},
        ]

        _on_message_history_processor_end(
            agent_name="code-puppy",
            session_id="test-session",
            message_history=history,
            messages_added=1,
            messages_filtered=0,
        )

        # State should NOT be reset
        assert mod._last_activated_skills == ["github-pr"]
        assert mod._last_user_prompt == "help me create a PR"

    def test_no_op_when_no_previous_activation(self):
        """When no skills were previously activated, hook is a no-op."""
        import code_puppy.plugins.auto_skill_activator.register_callbacks as mod

        mod._last_activated_skills = []
        mod._last_user_prompt = ""

        # Should not raise
        _on_message_history_processor_end(
            agent_name="code-puppy",
            session_id="test-session",
            message_history=[],
            messages_added=0,
            messages_filtered=0,
        )

    def test_handles_exception_gracefully(self):
        """Hook should never crash even with bad message history."""
        import code_puppy.plugins.auto_skill_activator.register_callbacks as mod

        mod._last_activated_skills = ["github-pr"]
        mod._last_user_prompt = "help me"

        # Pass something that might cause an error
        _on_message_history_processor_end(
            agent_name="code-puppy",
            session_id=None,
            message_history=None,  # type: ignore
            messages_added=0,
            messages_filtered=0,
        )

        # Should not crash — state may be reset as a safety measure
