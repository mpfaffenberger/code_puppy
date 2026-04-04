"""Auto Skill Activator plugin.

Problem this solves:
    Skills are injected into the system prompt as XML, but the LLM only calls
    activate_skill() if it independently decides the skill matches the task.
    In practice this rarely happens unless the user says "use skill" explicitly.

    This plugin fixes that by scoring the user prompt against all installed
    skill descriptions at prompt-assembly time, and auto-injecting the full
    SKILL.md content for any strong matches — no LLM decision required.

How it works:
    Hooks into `get_model_system_prompt` (fires during prompt assembly).
    Scores each skill using rapidfuzz token_set_ratio (already a dependency).
    Any skill scoring >= AUTO_ACTIVATE_THRESHOLD gets its full SKILL.md content
    appended to the system prompt directly before the agent runs.

This mirrors how agents work: explicit deterministic activation vs passive hope.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from code_puppy.callbacks import register_callback

logger = logging.getLogger(__name__)

# Fuzzy match threshold (0-100).
# 65 is permissive enough to catch synonyms/paraphrasing.
AUTO_ACTIVATE_THRESHOLD = 65

# Max skills to auto-activate per run (avoid flooding context window)
MAX_AUTO_ACTIVATE = 3


def _score_prompt_against_skill(user_prompt: str, skill_text: str) -> float:
    """Score how well a user prompt matches a skill using fuzzy token matching.

    Uses rapidfuzz.fuzz.token_set_ratio which handles:
    - Word order differences ("deploy docker" vs "docker deployment")
    - Partial matches ("github PR" matching "GitHub pull request workflow")
    - Case insensitivity

    Falls back to simple word overlap if rapidfuzz is unavailable.
    Returns a score from 0 to 100.
    """
    try:
        from rapidfuzz import fuzz
        return fuzz.token_set_ratio(user_prompt.lower(), skill_text.lower())
    except ImportError:
        user_words = set(user_prompt.lower().split())
        skill_words = set(skill_text.lower().split())
        if not skill_words:
            return 0.0
        return (len(user_words & skill_words) / len(skill_words)) * 100


def _auto_inject_skills(
    model_name: str, default_system_prompt: str, user_prompt: str
) -> Optional[Dict[str, Any]]:
    """get_model_system_prompt callback.

    Scores all installed skills against the user prompt and injects
    full SKILL.md content for matches above AUTO_ACTIVATE_THRESHOLD.
    Returns None if no matches (leaves prompt untouched).
    """
    if not user_prompt or not user_prompt.strip():
        return None

    try:
        from pathlib import Path

        from code_puppy.plugins.agent_skills.config import (
            get_disabled_skills,
            get_skill_directories,
            get_skills_enabled,
        )
        from code_puppy.plugins.agent_skills.discovery import discover_skills
        from code_puppy.plugins.agent_skills.metadata import (
            load_full_skill_content,
            parse_skill_metadata,
        )

        if not get_skills_enabled():
            return None

        skill_dirs = [Path(d) for d in get_skill_directories()]
        discovered = discover_skills(skill_dirs)
        if not discovered:
            return None

        disabled_skills = get_disabled_skills()
        scored: List[tuple] = []

        for skill_info in discovered:
            if skill_info.name in disabled_skills:
                continue
            if not skill_info.has_skill_md:
                continue

            metadata = parse_skill_metadata(skill_info.path)
            if not metadata:
                continue

            # Score against name + description + tags combined
            combined = f"{metadata.name} {metadata.description} {' '.join(metadata.tags)}"
            score = _score_prompt_against_skill(user_prompt, combined)

            if score >= AUTO_ACTIVATE_THRESHOLD:
                scored.append((score, metadata.name, skill_info.path))
                logger.info(
                    f"[AutoSkillActivator] '{metadata.name}' scored {score:.1f} "
                    f"— queued for auto-activation"
                )

        if not scored:
            return None

        # Top N by score
        scored.sort(key=lambda x: x[0], reverse=True)
        top_skills = scored[:MAX_AUTO_ACTIVATE]

        injected: List[str] = []
        activated_names: List[str] = []

        for score, name, skill_path in top_skills:
            content = load_full_skill_content(skill_path)
            if content:
                injected.append(
                    f"\n\n# Auto-Activated Skill: {name} (relevance: {score:.0f}%)\n"
                    f"{content}"
                )
                activated_names.append(name)

        if not injected:
            return None

        logger.info(
            f"[AutoSkillActivator] Auto-activated skills: {', '.join(activated_names)}"
        )

        return {
            "instructions": default_system_prompt + "".join(injected),
            "user_prompt": user_prompt,
            "handled": False,  # Allow other handlers (claude-code, etc.) to also run
        }

    except Exception as exc:
        # Never crash the agent — degrade gracefully
        logger.error(f"[AutoSkillActivator] Unexpected error: {exc}")
        return None


register_callback("get_model_system_prompt", _auto_inject_skills)

logger.info("Auto Skill Activator plugin loaded")
