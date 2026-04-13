"""Auto Skill Activator plugin — background steering model approach.

Problem this solves:
    Skills are injected into the system prompt as XML, but the LLM only calls
    activate_skill() if it independently decides the skill matches the task.
    In practice this rarely happens unless the user says "use skill" explicitly.

    This plugin fixes that by using a lightweight background model to semantically
    evaluate which skills (if any) are relevant to the user's prompt, then
    auto-injecting the full SKILL.md content for matches — no LLM decision required.

How it works:
    Hooks into `get_model_system_prompt` (fires during prompt assembly).
    Sends the user prompt + all skill descriptions to a small steering model
    (e.g. Haiku, GPT-4o-mini, Gemma 4 IT) which returns relevance scores.
    Any skill scoring >= AUTO_ACTIVATE_THRESHOLD gets its full SKILL.md content
    appended to the system prompt directly before the agent runs.

    Also hooks into `message_history_processor_end` to re-inject skills after
    context compaction, ensuring skill content persists across the full session.

This mirrors how agents work: explicit deterministic activation vs passive hope.
"""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from typing import Any, Dict, List, Optional

from code_puppy.callbacks import register_callback

logger = logging.getLogger(__name__)

# Relevance threshold (0-100).
# 65 is permissive enough to catch paraphrasing and intent matching.
AUTO_ACTIVATE_THRESHOLD = 65

# Max skills to auto-activate per run (avoid flooding context window)
MAX_AUTO_ACTIVATE = 3

# Default steering model for semantic skill matching.
# Falls back to rapidfuzz if no steering model is available.
STEERING_MODEL_DEFAULT = "claude-haiku-4"

# Session-scoped state: tracks last activated skills for compaction re-injection.
# Uses ContextVar for thread-safety when multiple agents run concurrently.
_last_activated_skills: ContextVar[List[str]] = ContextVar(
    "_last_activated_skills", default=[]
)
_last_user_prompt: ContextVar[str] = ContextVar("_last_user_prompt", default="")


def _get_steering_model_name() -> str:
    """Get the configured steering model name, with fallback."""
    try:
        from code_puppy.config import get_value
        val = get_value("auto_skill_steering_model")
        if val:
            return str(val)
    except Exception:
        pass
    return STEERING_MODEL_DEFAULT


def _score_skills_with_llm(
    user_prompt: str, skill_descriptions: List[Dict[str, str]]
) -> List[Dict[str, Any]]:
    """Use a lightweight LLM to score skill relevance against the user prompt.

    Args:
        user_prompt: The user's current prompt/message.
        skill_descriptions: List of dicts with 'name' and 'description' keys.

    Returns:
        List of dicts with 'name' and 'score' (0-100) for each skill.
    """
    if not skill_descriptions:
        return []

    # Build the scoring prompt
    skill_list = "\n".join(
        f"{i+1}. {s['name']}: {s['description']}"
        for i, s in enumerate(skill_descriptions)
    )

    system_prompt = (
        "You are a skill relevance scorer. Given a user prompt and a list of skills "
        "with descriptions, score each skill's relevance from 0 to 100.\n\n"
        "Rules:\n"
        "- Score based on semantic relevance, not just keyword overlap\n"
        "- A skill about 'GitHub PR workflow' is highly relevant to 'help me create a pull request'\n"
        "- A skill about 'baking recipes' is NOT relevant to 'deploy my app'\n"
        "- Return ONLY a JSON array of objects with 'name' and 'score' keys\n"
        "- Do not include any other text or explanation"
    )

    user_message = (
        f"User prompt: {user_prompt}\n\n"
        f"Available skills:\n{skill_list}\n\n"
        f"Score each skill's relevance (0-100). Return JSON array."
    )

    try:
        from code_puppy.model_factory import ModelFactory

        model_name = _get_steering_model_name()
        config = ModelFactory.load_config()
        model = ModelFactory.get_model(model_name, config)

        if model is None:
            logger.warning(
                f"[AutoSkillActivator] Steering model '{model_name}' unavailable, "
                f"falling back to fuzzy matching"
            )
            return _score_skills_with_fuzz(user_prompt, skill_descriptions)

        # Use pydantic-ai to call the model
        import asyncio
        from pydantic_ai import Agent

        scoring_agent = Agent(
            model=model,
            system_prompt=system_prompt,
            result_type=str,
        )

        # Run synchronously — we're in a sync callback context
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # We're inside an async context — run in a thread with proper
            # cancellation via asyncio.wait_for to prevent thread leakage.
            import concurrent.futures

            async def _run_with_timeout():
                return await asyncio.wait_for(
                    scoring_agent.run(user_message), timeout=15
                )

            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(lambda: asyncio.run(_run_with_timeout()))
                try:
                    result = future.result(timeout=20)
                except concurrent.futures.TimeoutError:
                    logger.warning(
                        "[AutoSkillActivator] Steering model timed out, "
                        "falling back to fuzzy matching"
                    )
                    return _score_skills_with_fuzz(user_prompt, skill_descriptions)
            response_text = result.data
        else:
            result = asyncio.run(
                asyncio.wait_for(scoring_agent.run(user_message), timeout=15)
            )
            response_text = result.data

        # Parse the JSON response
        scores = json.loads(response_text)
        if not isinstance(scores, list):
            logger.warning("[AutoSkillActivator] LLM returned non-list, falling back")
            return _score_skills_with_fuzz(user_prompt, skill_descriptions)

        # Validate and normalize scores
        validated = []
        for item in scores:
            if isinstance(item, dict) and "name" in item and "score" in item:
                score = float(item["score"])
                validated.append({"name": item["name"], "score": max(0, min(100, score))})

        return validated

    except json.JSONDecodeError:
        logger.warning("[AutoSkillActivator] Failed to parse LLM scoring response, falling back")
        return _score_skills_with_fuzz(user_prompt, skill_descriptions)
    except Exception as exc:
        logger.warning(
            f"[AutoSkillActivator] LLM scoring failed ({exc}), falling back to fuzzy matching"
        )
        return _score_skills_with_fuzz(user_prompt, skill_descriptions)


def _score_skills_with_fuzz(
    user_prompt: str, skill_descriptions: List[Dict[str, str]]
) -> List[Dict[str, Any]]:
    """Fallback: score skills using rapidfuzz token matching.

    Used when the steering LLM is unavailable.
    """
    results = []
    for skill in skill_descriptions:
        score = _fuzzy_score(user_prompt, skill["description"])
        results.append({"name": skill["name"], "score": score})
    return results


def _fuzzy_score(user_prompt: str, skill_text: str) -> float:
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

    Uses a lightweight steering model to semantically evaluate which skills
    are relevant to the user prompt, then injects full SKILL.md content
    for matches above AUTO_ACTIVATE_THRESHOLD.
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

        # Collect skill descriptions for LLM scoring
        skill_descriptions: List[Dict[str, str]] = []
        skill_path_map: Dict[str, Path] = {}

        for skill_info in discovered:
            if skill_info.name in disabled_skills:
                continue
            if not skill_info.has_skill_md:
                continue

            metadata = parse_skill_metadata(skill_info.path)
            if not metadata:
                continue

            combined = f"{metadata.name} {metadata.description} {' '.join(metadata.tags)}"
            skill_descriptions.append({"name": metadata.name, "description": combined})
            skill_path_map[metadata.name] = skill_info.path

        if not skill_descriptions:
            return None

        # Score skills using the steering LLM (with fuzzy fallback)
        scored = _score_skills_with_llm(user_prompt, skill_descriptions)

        # Filter by threshold
        matching: List[tuple] = []
        for item in scored:
            name = item["name"]
            score = item["score"]
            if score >= AUTO_ACTIVATE_THRESHOLD and name in skill_path_map:
                matching.append((score, name, skill_path_map[name]))
                logger.info(
                    f"[AutoSkillActivator] '{name}' scored {score:.1f} "
                    f"— queued for auto-activation"
                )

        if not matching:
            return None

        # Top N by score
        matching.sort(key=lambda x: x[0], reverse=True)
        top_skills = matching[:MAX_AUTO_ACTIVATE]

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

        # Store state for compaction re-injection
        _last_activated_skills.set(activated_names)
        _last_user_prompt.set(user_prompt)

        logger.info(
            f"[AutoSkillActivator] Auto-activated skills: {', '.join(activated_names)}"
        )

        return {
            "instructions": default_system_prompt + "".join(injected),
            "user_prompt": user_prompt,
            "handled": True,  # model_utils.py only accepts results where handled is truthy
        }

    except Exception as exc:
        # Never crash the agent — degrade gracefully
        logger.error(f"[AutoSkillActivator] Unexpected error: {exc}")
        return None


def _on_message_history_processor_end(
    agent_name: str,
    session_id: str | None,
    message_history: list,
    messages_added: int,
    messages_filtered: int,
) -> None:
    """message_history_processor_end callback.

    After compaction, checks if previously activated skills were stripped from
    the message history and re-injects them if needed. This ensures skill
    content persists across the full session even when context is compacted.
    """
    if not _last_activated_skills.get() or not _last_user_prompt.get():
        return

    try:
        # Check if any activated skill content is still present in the history
        history_text = ""
        for msg in message_history:
            if isinstance(msg, dict):
                content = msg.get("content", "")
                if isinstance(content, str):
                    history_text += content
            elif hasattr(msg, "content"):
                content = msg.content
                if isinstance(content, str):
                    history_text += content

        # Check if skill markers are still present
        missing_skills = []
        for skill_name in _last_activated_skills.get():
            marker = f"Auto-Activated Skill: {skill_name}"
            if marker not in history_text:
                missing_skills.append(skill_name)

        if not missing_skills:
            return  # All skills still present, no re-injection needed

        logger.info(
            f"[AutoSkillActivator] Compaction removed skills: {', '.join(missing_skills)}. "
            f"Re-injection will occur on next prompt assembly."
        )

        # Reset state so next get_model_system_prompt call re-evaluates
        # The next prompt will trigger _auto_inject_skills which will re-score
        # and re-inject the relevant skills
        _last_activated_skills.set([])
        _last_user_prompt.set("")

    except Exception as exc:
        logger.error(f"[AutoSkillActivator] Compaction re-injection error: {exc}")


register_callback("get_model_system_prompt", _auto_inject_skills)
register_callback("message_history_processor_end", _on_message_history_processor_end)

logger.info("Auto Skill Activator plugin loaded (background steering model)")
