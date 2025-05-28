import os
import pydantic
from pathlib import Path
from pydantic_ai import Agent

from code_puppy.agent_prompts import SYSTEM_PROMPT
from code_puppy.model_factory import ModelFactory

# Environment variables used in this module:
# - MODELS_JSON_PATH: Optional path to a custom models.json configuration file.
#                     If not set, uses the default file in the package directory.
# - MODEL_NAME: The model to use for code generation. Defaults to "gpt-4o".
#               Must match a key in the models.json configuration.

MODELS_JSON_PATH = os.environ.get("MODELS_JSON_PATH", None)


class AgentResponse(pydantic.BaseModel):
    """Represents a response from the agent."""

    output_message: str = pydantic.Field(
        ..., description="The final output message to display to the user"
    )
    awaiting_user_input: bool = pydantic.Field(
        False, description="True if user input is needed to continue the task"
    )


model_name = os.environ.get("MODEL_NAME", "gpt-4o-mini")
if not MODELS_JSON_PATH:
    models_path = Path(__file__).parent / "models.json"
else:
    models_path = Path(MODELS_JSON_PATH)

model = ModelFactory.get_model(model_name, ModelFactory.load_config(models_path))
code_generation_agent = Agent(
    model=model,
    system_prompt=SYSTEM_PROMPT,
    output_type=AgentResponse,
)
