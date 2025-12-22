"""Session title generation agent for creating concise, descriptive session names.

This module provides AI-powered session title generation with fallback mechanisms
and caching to ensure titles are generated once per session.
"""

from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from pydantic_ai import Agent as PydanticAgent

# Module-level caches and resources
_SESSION_FIRST_PROMPT: dict[str, str] = {}
_SESSION_TITLE_CACHE: dict[str, str] = {}
_TITLE_AGENT: Optional[PydanticAgent] = None
_TITLE_THREAD_POOL: Optional[ThreadPoolExecutor] = None

# Configuration constants
_TITLE_AGENT_INSTRUCTIONS = (
    "You generate concise session titles based on a user's first prompt. "
    "Respond with fewer than ten words, title case preferred, and avoid punctuation beyond spaces."
)
_TITLE_PROMPT_TEMPLATE = (
    "User's opening request:\n{prompt}\n\n"
    "Return only the suggested session title (<=10 words)."
)
_MAX_TITLE_PROMPT_CHARS = 500
_MAX_TITLE_WORDS = 10


def _ensure_title_agent() -> PydanticAgent:
    """Lazy initialization of the session title generation agent."""
    global _TITLE_AGENT
    if _TITLE_AGENT is not None:
        return _TITLE_AGENT

    from code_puppy.model_factory import ModelFactory
    from code_puppy.config import get_global_model_name

    models_config = ModelFactory.load_config()
    model_name = get_global_model_name()
    model = ModelFactory.get_model(model_name, models_config)

    _TITLE_AGENT = PydanticAgent(
        model=model,
        instructions=_TITLE_AGENT_INSTRUCTIONS,
        output_type=str,
        retries=1,
    )
    return _TITLE_AGENT


def _ensure_title_thread_pool() -> ThreadPoolExecutor:
    """Lazy initialization of the thread pool for async title generation."""
    global _TITLE_THREAD_POOL
    if _TITLE_THREAD_POOL is None:
        _TITLE_THREAD_POOL = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="session-title-generator"
        )
    return _TITLE_THREAD_POOL


async def _generate_session_title_async(prompt: str) -> str:
    """Generate a session title asynchronously using the AI agent.

    Args:
        prompt: The user's first prompt for the session.

    Returns:
        Generated session title (<=10 words).
    """
    agent = _ensure_title_agent()
    sanitized_prompt = prompt.strip()
    if len(sanitized_prompt) > _MAX_TITLE_PROMPT_CHARS:
        sanitized_prompt = sanitized_prompt[:_MAX_TITLE_PROMPT_CHARS]
    request = _TITLE_PROMPT_TEMPLATE.format(prompt=sanitized_prompt)
    result = await agent.run(request)
    title = (result.output or "").strip()

    # Enforce word limit defensively
    words = title.split()
    if len(words) > _MAX_TITLE_WORDS:
        title = " ".join(words[:_MAX_TITLE_WORDS])
    return title


def _generate_session_title(prompt: str) -> str:
    """Generate a session title synchronously with proper event loop handling.

    Args:
        prompt: The user's first prompt for the session.

    Returns:
        Generated session title (<=10 words).
    """
    loop = asyncio.get_event_loop()
    if loop.is_running():
        pool = _ensure_title_thread_pool()

        def worker() -> str:
            return asyncio.run(_generate_session_title_async(prompt))

        return pool.submit(worker).result()

    return loop.run_until_complete(_generate_session_title_async(prompt))


def maybe_generate_session_title(
    session_name: str, first_prompt: str, autosave_dir: Path
) -> str | None:
    """Generate and cache a session title once per session.

    This function ensures that session titles are generated exactly once:
    1. Checks in-memory cache first
    2. Checks session metadata file for existing title (from restored sessions)
    3. Generates new title via AI if no existing title found
    4. Falls back to truncated prompt if AI generation fails

    Args:
        session_name: Session identifier used for autosave/context naming.
        first_prompt: User's first prompt for the session.
        autosave_dir: Directory where session metadata is stored.

    Returns:
        Generated title, cached title, or None if generation is not possible.
    """
    if not session_name or not (first_prompt or "").strip():
        return None

    # Store and use the first prompt for consistency
    cached_prompt = _SESSION_FIRST_PROMPT.get(session_name)
    if cached_prompt is None:
        _SESSION_FIRST_PROMPT[session_name] = first_prompt
    else:
        first_prompt = cached_prompt

    # Check in-memory cache first (fast path)
    if session_name in _SESSION_TITLE_CACHE:
        return _SESSION_TITLE_CACHE[session_name]

    # Check if session metadata already has a title (e.g., from restored session)
    try:
        metadata_path = autosave_dir / f"{session_name}_meta.json"
        if metadata_path.exists():
            with metadata_path.open("r", encoding="utf-8") as f:
                metadata = json.load(f)
            existing_title = metadata.get("session_title")
            if existing_title:
                # Load existing title into cache and return it
                _SESSION_TITLE_CACHE[session_name] = existing_title
                return existing_title
    except Exception:
        # If we can't read metadata, continue to generation
        pass

    # Generate new title via AI
    try:
        title = _generate_session_title(first_prompt)
        if title:
            _SESSION_TITLE_CACHE[session_name] = title
            return title
    except Exception:
        # Fallback: Use truncated version of user prompt (max 10 words)
        words = first_prompt.strip().split()
        fallback_title = " ".join(words[:_MAX_TITLE_WORDS])
        if fallback_title:
            _SESSION_TITLE_CACHE[session_name] = fallback_title
            return fallback_title
        return None

    # Fallback: Use truncated version of user prompt if AI returned empty
    words = first_prompt.strip().split()
    fallback_title = " ".join(words[:_MAX_TITLE_WORDS])
    if fallback_title:
        _SESSION_TITLE_CACHE[session_name] = fallback_title
        return fallback_title

    return None


def get_cached_session_title(session_name: str) -> str | None:
    """Retrieve a cached session title without triggering generation.

    Args:
        session_name: Session identifier.

    Returns:
        Cached title or None if not found.
    """
    return _SESSION_TITLE_CACHE.get(session_name)
