import asyncio
import atexit
import hashlib
import logging
import pathlib
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

from pydantic_ai import Agent

from code_puppy.config import get_summarization_model_name
from code_puppy.model_factory import ModelFactory, make_model_settings

logger = logging.getLogger(__name__)

# Keep a module-level agent reference to avoid rebuilding per call
_summarization_agent = None
_agent_lock = threading.Lock()

# P2-05/PERF-05: track the model name the cached agent was built for
_cached_model_name: Optional[str] = None

# Safe sync runner for async agent.run calls
# Avoids "event loop is already running" by offloading to a separate thread loop when needed
_thread_pool: ThreadPoolExecutor | None = None

# Reload counter
_reload_count = 0


# ---------------------------------------------------------------------------
# P2-05/PERF-05: Model config cache with mtime invalidation
# ---------------------------------------------------------------------------


def _models_config_fingerprint() -> Tuple[float, str]:
    """Compute a lightweight fingerprint of all model config sources.

    Returns (max_mtime, content_hash) — if either changes, the cached
    config is stale and must be reloaded.
    """
    source_paths: list[pathlib.Path] = []

    # Bundled models.json is always loaded
    bundled = pathlib.Path(__file__).parent / "models.json"
    source_paths.append(bundled)

    # Extra model sources (mirrors ModelFactory.load_config)
    try:
        from code_puppy.config import (
            CHATGPT_MODELS_FILE,
            CLAUDE_MODELS_FILE,
            COPILOT_MODELS_FILE,
            EXTRA_MODELS_FILE,
            GEMINI_MODELS_FILE,
        )

        for p in (
            EXTRA_MODELS_FILE,
            CHATGPT_MODELS_FILE,
            CLAUDE_MODELS_FILE,
            GEMINI_MODELS_FILE,
            COPILOT_MODELS_FILE,
        ):
            source_paths.append(pathlib.Path(p))
    except Exception:
        pass

    max_mtime = 0.0
    hasher = hashlib.md5(usedforsecurity=False)
    for sp in source_paths:
        try:
            if sp.exists():
                stat = sp.stat()
                max_mtime = max(max_mtime, stat.st_mtime)
                # Hash file contents (or just size+mtime as a cheap proxy)
                hasher.update(f"{sp}:{stat.st_size}:{stat.st_mtime}".encode())
        except OSError:
            pass

    return max_mtime, hasher.hexdigest()


# Module-level model config cache: (config_dict, fingerprint)
_models_config_cache: Tuple[Optional[Dict[str, Any]], Optional[Tuple[float, str]]] = (
    None,
    None,
)
_models_config_lock = threading.Lock()


def get_cached_models_config() -> Dict[str, Any]:
    """Return the models config, using a cache invalidated by mtime/hash changes.

    This avoids re-reading ``models.json`` and extra model files on every call
    to ``ModelFactory.load_config()`` when nothing has changed. The cache is
    invalidated when any source file's mtime changes.

    Falls back to ``ModelFactory.load_config()`` on any error.
    """
    global _models_config_cache

    fingerprint = _models_config_fingerprint()

    with _models_config_lock:
        cached_config, cached_fp = _models_config_cache
        if cached_config is not None and cached_fp == fingerprint:
            return cached_config

        # Cache miss — reload. Let exceptions propagate so callers
        # (including reload_summarization_agent) see the same errors they
        # would have seen without the cache.
        config = ModelFactory.load_config()
        _models_config_cache = (config, fingerprint)
        return config


def invalidate_models_config_cache() -> None:
    """Force the next ``get_cached_models_config()`` call to reload.

    Call this when settings or model files are known to have changed
    (e.g. after a ``/set`` command that modifies model config).
    """
    global _models_config_cache
    with _models_config_lock:
        _models_config_cache = (None, None)


def _ensure_thread_pool():
    global _thread_pool
    # Check if pool is None OR if it's been shutdown
    if _thread_pool is None or _thread_pool._shutdown:
        _thread_pool = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="summarizer-loop"
        )
    return _thread_pool


def _shutdown_thread_pool():
    global _thread_pool
    if _thread_pool is not None:
        _thread_pool.shutdown(wait=False)
        _thread_pool = None


atexit.register(_shutdown_thread_pool)


async def _run_agent_async(agent: Agent, prompt: str, message_history: List):
    return await agent.run(prompt, message_history=message_history)


class SummarizationError(Exception):
    """Raised when summarization fails with details about the failure."""

    def __init__(self, message: str, original_error: Exception | None = None):
        self.original_error = original_error
        super().__init__(message)


def run_summarization_sync(prompt: str, message_history: List) -> List:
    """Run the summarization agent synchronously.

    Raises:
        SummarizationError: If summarization fails for any reason.
    """
    try:
        agent = get_summarization_agent()
    except Exception as e:
        raise SummarizationError(
            f"Failed to initialize summarization agent: {type(e).__name__}: {e}",
            original_error=e,
        ) from e

    # Handle claude-code models: prepend system prompt to user prompt
    from code_puppy.model_utils import prepare_prompt_for_model

    model_name = get_summarization_model_name()
    prepared = prepare_prompt_for_model(
        model_name, _get_summarization_instructions(), prompt
    )
    prompt = prepared.user_prompt

    def _run_in_thread():
        """
        Run the async agent in a dedicated thread with its own event loop.
        Uses run_until_complete instead of asyncio.run to avoid shutting down
        the default executor (which breaks DBOS in the main thread).
        Does NOT touch global event loop state.
        """
        loop = asyncio.new_event_loop()
        try:
            coro = agent.run(prompt, message_history=message_history)
            return loop.run_until_complete(coro)
        finally:
            # Clean up without shutting down the default executor
            try:
                # Cancel pending tasks
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
                loop.run_until_complete(loop.shutdown_asyncgens())
            finally:
                loop.close()

    try:
        # Always use thread pool since we're likely in an existing event loop
        pool = _ensure_thread_pool()
        result = pool.submit(_run_in_thread).result()
        return result.new_messages()
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e) if str(e) else "(no details available)"
        raise SummarizationError(
            f"LLM call failed during summarization: [{error_type}] {error_msg}",
            original_error=e,
        ) from e


def _get_summarization_instructions() -> str:
    """Get the system instructions for the summarization agent."""
    return """You are a message summarization expert. Your task is to summarize conversation messages
while preserving important context and information. The summaries should be concise but capture the essential content
and intent of the original messages. This is to help manage token usage in a conversation history
while maintaining context for the AI to continue the conversation effectively.

When summarizing:
1. Keep summary concise but informative
2. Preserve important context and key information and decisions
3. Keep any important technical details
4. Don't summarize the system message
5. Make sure all tool calls and responses are summarized, as they are vital
6. Focus on token usage efficiency and system message preservation"""


def reload_summarization_agent():
    """Create a specialized agent for summarizing messages when context limit is reached."""
    from code_puppy.model_utils import prepare_prompt_for_model

    # Always bust the cache on explicit reload — the caller expects fresh config
    invalidate_models_config_cache()
    models_config = get_cached_models_config()
    model_name = get_summarization_model_name()
    model = ModelFactory.get_model(model_name, models_config)

    # Handle claude-code models: swap instructions (prompt prepending happens in run_summarization_sync)
    instructions = _get_summarization_instructions()
    prepared = prepare_prompt_for_model(
        model_name, instructions, "", prepend_system_to_user=False
    )
    instructions = prepared.instructions

    model_settings = make_model_settings(model_name)

    agent = Agent(
        model=model,
        instructions=instructions,
        output_type=str,
        retries=1,  # Fewer retries for summarization
        model_settings=model_settings,
    )
    # NOTE: We intentionally DON'T wrap in DBOSAgent here.
    # Summarization is a simple one-shot call that doesn't need durable execution,
    # and DBOSAgent causes async event loop conflicts with run_sync().
    return agent


def get_summarization_agent(force_reload=False):
    """Retrieve the summarization agent, caching across calls.

    P2-05/PERF-05: The default is now ``force_reload=False``. The agent is
    rebuilt only when:
    - ``force_reload=True`` is explicitly passed
    - The summarization model name has changed since the last build
    - No agent has been built yet (first call)

    Args:
        force_reload: When True, unconditionally rebuild the agent.

    Returns:
        A ``pydantic_ai.Agent`` configured for summarization.
    """
    global _summarization_agent, _cached_model_name
    current_model = get_summarization_model_name()
    with _agent_lock:
        needs_reload = (
            force_reload
            or _summarization_agent is None
            or _cached_model_name != current_model
        )
        if needs_reload:
            _summarization_agent = reload_summarization_agent()
            _cached_model_name = current_model
        return _summarization_agent
