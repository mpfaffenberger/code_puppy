import os
import pydantic
from pydantic_ai import Agent
from code_agent.agent_prompts import SYSTEM_PROMPT

# Check if we have a valid API key
api_key = os.environ.get("OPENAI_API_KEY", "")

class AgentResponse(pydantic.BaseModel):
    """Represents a response from the agent."""
    output_message: str = pydantic.Field(..., description="The final output message to display to the user")
    awaiting_user_input: bool = pydantic.Field(False, description="True if user input is needed to continue the task")

# Create agent with tool usage explicitly enabled
code_generation_agent = Agent(
    model='openai:gpt-4.1-mini',
    system_prompt=SYSTEM_PROMPT,
    output_type=AgentResponse,
)
