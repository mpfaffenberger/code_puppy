import os
import pydantic
from pathlib import Path
from pydantic_ai import Agent

from code_puppy.agent_prompts import SYSTEM_PROMPT
from code_puppy.model_factory import ModelFactory


class AgentResponse(pydantic.BaseModel):
    """Represents a response from the agent."""

    output_message: str = pydantic.Field(
        ..., description="The final output message to display to the user"
    )
    awaiting_user_input: bool = pydantic.Field(
        False, description="True if user input is needed to continue the task"
    )


# Get model name from environment variable, default to gemini-2.0-flash
model_name = os.environ.get("MODEL_NAME", "gpt-4o")
# Load models.json from the same directory as this file
models_path = Path(__file__).parent / "models.json"
model = ModelFactory.get_model(model_name, ModelFactory.load_config(models_path))
# Create agent with tool usage explicitly enabled
code_generation_agent = Agent(
    model=model,
    system_prompt=SYSTEM_PROMPT,
    output_type=AgentResponse,
)
