import os
from pathlib import Path

from pydantic_ai import Agent

from code_puppy.model_factory import ModelFactory
from code_puppy.tools.common import console

# Environment variables used in this module:
# - MODELS_JSON_PATH: Optional path to a custom models.json configuration file.
#                     If not set, uses the default file in the package directory.
# - MODEL_NAME: The model to use for code generation. Defaults to "gpt-4o".
#               Must match a key in the models.json configuration.

MODELS_JSON_PATH = os.environ.get("MODELS_JSON_PATH", None)

_LAST_MODEL_NAME = None
_summarization_agent = None


def reload_summarization_agent():
    """Create a specialized agent for summarizing messages when context limit is reached."""
    global _summarization_agent, _LAST_MODEL_NAME
    from code_puppy.config import get_model_name

    model_name = get_model_name()
    console.print(f"[bold cyan]Loading Summarization Model: {model_name}[/bold cyan]")
    models_path = (
        Path(MODELS_JSON_PATH)
        if MODELS_JSON_PATH
        else Path(__file__).parent / "models.json"
    )
    model = ModelFactory.get_model(model_name, ModelFactory.load_config(models_path))

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
    _summarization_agent = agent
    _LAST_MODEL_NAME = model_name
    return _summarization_agent


def get_summarization_agent(force_reload=False):
    """
    Retrieve the summarization agent with the currently set MODEL_NAME.
    Forces a reload if the model has changed, or if force_reload is passed.
    """
    global _summarization_agent, _LAST_MODEL_NAME
    from code_puppy.config import get_model_name

    model_name = get_model_name()
    if _summarization_agent is None or _LAST_MODEL_NAME != model_name or force_reload:
        return reload_summarization_agent()
    return _summarization_agent
