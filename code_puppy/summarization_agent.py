import asyncio
import atexit
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import List

from pydantic_ai import Agent

from code_puppy.config import (
    get_global_model_name,
    get_use_dbos,
)
from code_puppy.model_factory import ModelFactory, make_model_settings

# Keep a module-level agent reference to avoid rebuilding per call
_summarization_agent = None
_agent_lock = threading.Lock()

# Safe sync runner for async agent.run calls
# Avoids "event loop is already running" by offloading to a separate thread loop when needed
_thread_pool: ThreadPoolExecutor | None = None

# Reload counter
_reload_count = 0


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


def _run_async_safely(coro):
    """
    Run an async coroutine in a fresh event loop without affecting global state.
    
    Unlike asyncio.run(), this:
    - Doesn't call shutdown_default_executor() (which breaks DBOS)
    - Doesn't modify the global event loop reference
    """
    # Create a new loop but DON'T set it as the current loop
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        # Clean up this loop only, don't touch global state
        try:
            _cancel_all_tasks(loop)
            loop.run_until_complete(loop.shutdown_asyncgens())
        finally:
            loop.close()


def _cancel_all_tasks(loop):
    """Cancel all pending tasks in the loop."""
    to_cancel = asyncio.all_tasks(loop)
    if not to_cancel:
        return
    for task in to_cancel:
        task.cancel()
    loop.run_until_complete(asyncio.gather(*to_cancel, return_exceptions=True))


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

    model_name = get_global_model_name()
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
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
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

    models_config = ModelFactory.load_config()
    model_name = get_global_model_name()
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


def get_summarization_agent(force_reload=True):
    """
    Retrieve the summarization agent with the currently set MODEL_NAME.
    Forces a reload if the model has changed, or if force_reload is passed.
    """
    global _summarization_agent
    with _agent_lock:
        if force_reload or _summarization_agent is None:
            _summarization_agent = reload_summarization_agent()
        return _summarization_agent
