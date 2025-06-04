import os
import pydantic
from pathlib import Path
from pydantic_ai import Agent

from code_puppy.agent_prompts import SYSTEM_PROMPT
from code_puppy.model_factory import ModelFactory
from code_puppy.tools.common import console

# Environment variables used in this module:
# - MODELS_JSON_PATH: Optional path to a custom models.json configuration file.
#                     If not set, uses the default file in the package directory.
# - MODEL_NAME: The model to use for code generation. Defaults to "gpt-4o".
#               Must match a key in the models.json configuration.

MODELS_JSON_PATH = os.environ.get("MODELS_JSON_PATH", None)

# Load puppy rules if provided
PUPPY_RULES_PATH = Path('.puppy_rules')
PUPPY_RULES = None
if PUPPY_RULES_PATH.exists():
    with open(PUPPY_RULES_PATH, 'r') as f:
        PUPPY_RULES = f.read()

class AgentResponse(pydantic.BaseModel):
    """Represents a response from the agent."""

    output_message: str = pydantic.Field(
        ..., description="The final output message to display to the user"
    )
    awaiting_user_input: bool = pydantic.Field(
        False, description="True if user input is needed to continue the task"
    )

# --- NEW DYNAMIC AGENT LOGIC ---
_LAST_MODEL_NAME = None
_code_generation_agent = None

def reload_code_generation_agent():
    """Force-reload the agent, usually after a model change."""
    global _code_generation_agent, _LAST_MODEL_NAME
    model_name = os.environ.get("MODEL_NAME", "gpt-4o-mini")
    console.print(f'[bold cyan]Loading Model: {model_name}[/bold cyan]')
    models_path = Path(MODELS_JSON_PATH) if MODELS_JSON_PATH else Path(__file__).parent / "models.json"
    model = ModelFactory.get_model(model_name, ModelFactory.load_config(models_path))
    instructions = SYSTEM_PROMPT
    if PUPPY_RULES:
        instructions += f'\n{PUPPY_RULES}'
    _code_generation_agent = Agent(
        model=model,
        instructions=instructions,
        output_type=AgentResponse,
        retries=3,
    )
    _LAST_MODEL_NAME = model_name
    return _code_generation_agent

def get_code_generation_agent(force_reload=False):
    """
    Retrieve the agent with the currently set MODEL_NAME.
    Forces a reload if the model has changed, or if force_reload is passed.
    """
    global _code_generation_agent, _LAST_MODEL_NAME
    model_name = os.environ.get("MODEL_NAME", "gpt-4o-mini")
    if _code_generation_agent is None or _LAST_MODEL_NAME != model_name or force_reload:
        return reload_code_generation_agent()
    return _code_generation_agent
