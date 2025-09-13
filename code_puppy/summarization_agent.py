import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List

from pydantic_ai import Agent

from code_puppy.config import get_model_name
from code_puppy.model_factory import ModelFactory

# Keep a module-level agent reference to avoid rebuilding per call
_summarization_agent = None

# Safe sync runner for async agent.run calls
# Avoids "event loop is already running" by offloading to a separate thread loop when needed
_thread_pool: ThreadPoolExecutor | None = None


def _ensure_thread_pool():
    global _thread_pool
    if _thread_pool is None:
        _thread_pool = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="summarizer-loop"
        )
    return _thread_pool


async def _run_agent_async(agent: Agent, prompt: str, message_history: List):
    return await agent.run(prompt, message_history=message_history)


def run_summarization_sync(prompt: str, message_history: List) -> List:
    agent = get_summarization_agent()
    try:
        # Try to detect if we're already in an event loop
        asyncio.get_running_loop()

        # We're in an event loop: offload to a dedicated thread with its own loop
        def _worker(prompt_: str):
            return asyncio.run(
                _run_agent_async(agent, prompt_, message_history=message_history)
            )

        pool = _ensure_thread_pool()
        result = pool.submit(_worker, prompt).result()
    except RuntimeError:
        # No running loop, safe to run directly
        result = asyncio.run(
            _run_agent_async(agent, prompt, message_history=message_history)
        )
    return result.new_messages()


def reload_summarization_agent():
    """Create a specialized agent for summarizing messages when context limit is reached."""
    models_config = ModelFactory.load_config()
    model_name = get_model_name()
    model = ModelFactory.get_model(model_name, models_config)

    # Specialized instructions for summarization
    instructions = """You are a message summarization expert. Your task is to summarize conversation messages
while preserving important context and information. The summaries should be concise but capture the essential
content and intent of the original messages. This is to help manage token usage in a conversation history
while maintaining context for the AI to continue the conversation effectively.

When summarizing:
1. Keep summary brief but informative
2. Preserve key information and decisions
3. Keep any important technical details
4. Don't summarize the system message
5. Make sure all tool calls and responses are summarized, as they are vital"""

    agent = Agent(
        model=model,
        instructions=instructions,
        output_type=str,
        retries=1,  # Fewer retries for summarization
    )
    return agent


def get_summarization_agent(force_reload=True):
    """
    Retrieve the summarization agent with the currently set MODEL_NAME.
    Forces a reload if the model has changed, or if force_reload is passed.
    """
    global _summarization_agent
    if force_reload or _summarization_agent is None:
        _summarization_agent = reload_summarization_agent()
    return _summarization_agent
