import os

from pydantic_ai import Agent
from code_agent.agent_prompts import SYSTEM_PROMPT

# Check if we have a valid API key
api_key = os.environ.get("OPENAI_API_KEY", "")

# Create agent with tool usage explicitly enabled
code_generation_agent = Agent(
    model='openai:gpt-4o',  # This can be any model capable of code generation
    system_prompt=SYSTEM_PROMPT,
    retries=1,
    stream=True,
)
