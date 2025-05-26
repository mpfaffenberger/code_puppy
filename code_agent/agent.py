import os
import pydantic
from pydantic_ai import Agent
from typing import Optional
from code_agent.agent_prompts import SYSTEM_PROMPT

# Check if we have a valid API key
api_key = os.environ.get("OPENAI_API_KEY", "")

class AgentResponse(pydantic.BaseModel):
    """Represents a response from the agent."""
    output_message: str = pydantic.Field(..., description="The final output message to display to the user")
    needs_user_input_to_continue: Optional[bool] = pydantic.Field(False, description="Set to True if the agent needs user input to continue")
    should_continue: bool = pydantic.Field(False, description="Set to True if you haven't finished your current plan yet")

# Create agent with tool usage explicitly enabled
code_generation_agent = Agent(
    model='openai:gpt-4o',  # This can be any model capable of code generation
    system_prompt=SYSTEM_PROMPT,
    output_type=AgentResponse,
)
