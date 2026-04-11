"""Tests for the Auto Skill Activator plugin.

Tests verify that:
1. Skills are auto-activated when user prompt matches description above threshold
2. Skills are NOT activated when prompt is unrelated (below threshold)
3. Multiple matching skills are ranked by score, capped at MAX_AUTO_ACTIVATE
4. Disabled skills are never auto-activated
5. Plugin degrades gracefully on errors
6. The `handled: False` flag is always set so other handlers still run
"""

from __future__ import annotations

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


# ---------------------------------------------------------------------------
# Import target
# ---------------------------------------------------------------------------

from code_puppy.plugins.auto_skill_activator.register_callbacks import (
    AUTO_ACTIVATE_THRESHOLD,
    MAX_AUTO_ACTIVATE,
    _auto_inject_skills,
    _score_prompt_against_skill,
)


# ---------------------------------------------------------------------------
# Unit: _score_prompt_against_skill
# ---------------------------------------------------------------------------

class TestScorePromptAgainstSkill:
    def test_exact_match_scores_high(self):
        score = _score_prompt_against_skill("deploy docker container", "deploy docker container")
        assert score >= 90

    def test_synonym_scores_above_threshold(self):
        score = _score_prompt_against_skill(
            "deploy my docker container", "deploy docker container deployment"
        )
        assert score >= AUTO_ACTIVATE_THRESHOLD

    def test_unrelated_scores_low(self):
        score = _score_prompt_against_skill(
            "what is the weather today", "github pull request workflow"
        )
        assert score < AUTO_ACTIVATE_THRESHOLD

    def test_empty_prompt_scores_zero(self):
        score = _score_prompt_against_skill("", "github pull request workflow")
        assert score == 0 or score < AUTO_ACTIVATE_THRESHOLD

    def test_case_insensitive(self):
        score_lower = _score_prompt_against_skill("github pr", "GitHub Pull Request")
        score_upper = _score_prompt_against_skill("GITHUB PR", "github pull request")
        assert abs(score_lower - score_upper) <= 5


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
    ):
        """Helper to run _auto_inject_skills with mocked dependencies."""
        discovered = discovered or []
        disabled = disabled or set()
        skill_contents = skill_contents or {}
        metadata_map = metadata_map or {}

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
        # Only 2 are relevant to the prompt
        metadata_map = {
            "skill-0": make_metadata("skill-0", "github pull request code review workflow"),
            "skill-1": make_metadata("skill-1", "bake bread cooking recipe"),
            "skill-2": make_metadata("skill-2", "github PR branch merge review"),
            "skill-3": make_metadata("skill-3", "database sql query optimization"),
            "skill-4": make_metadata("skill-4", "github issues tracker bug report"),
        }
        skill_contents = {f"skill-{i}": f"# Skill {i} Content" for i in range(5)}

        result = self._run(
            user_prompt="create a github pull request and review the code",
            discovered=skills,
            metadata_map=metadata_map,
            skill_contents=skill_contents,
        )
        assert result is not None
        # Cooking/database/unrelated skills should NOT be injected
        assert "bake bread" not in result["instructions"]
        assert "sql query" not in result["instructions"]

    def test_max_auto_activate_cap_respected(self):
        # Create MAX_AUTO_ACTIVATE + 2 highly matching skills
        n = MAX_AUTO_ACTIVATE + 2
        skills = [make_skill_info(f"skill-{i}") for i in range(n)]
        metadata_map = {
            f"skill-{i}": make_metadata(
                f"skill-{i}", "github pull request workflow review branch merge"
            )
            for i in range(n)
        }
        skill_contents = {f"skill-{i}": f"# Skill {i} Content" for i in range(n)}

        result = self._run(
            user_prompt="create a github pull request and review the code",
            discovered=skills,
            metadata_map=metadata_map,
            skill_contents=skill_contents,
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
