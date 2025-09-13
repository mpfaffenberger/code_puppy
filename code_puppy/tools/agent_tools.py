# agent_tools.py

from typing import List
from pydantic import BaseModel
from pydantic_ai import RunContext

from code_puppy.messaging import (
    emit_info,
    emit_divider,
    emit_system_message,
    emit_error,
)
from code_puppy.tools.common import generate_group_id
from code_puppy.agents.agent_manager import get_available_agents, load_agent_config

# Import Agent from pydantic_ai to create temporary agents for invocation
from pydantic_ai import Agent
from code_puppy.model_factory import ModelFactory
from code_puppy.config import get_model_name


class AgentInfo(BaseModel):
    """Information about an available agent."""

    name: str
    display_name: str


class ListAgentsOutput(BaseModel):
    """Output for the list_agents tool."""

    agents: List[AgentInfo]
    error: str | None = None


class AgentInvokeOutput(BaseModel):
    """Output for the invoke_agent tool."""

    response: str | None
    agent_name: str
    error: str | None = None


def register_list_agents(agent):
    """Register the list_agents tool with the provided agent.

    Args:
        agent: The agent to register the tool with
    """

    @agent.tool
    def list_agents(context: RunContext) -> ListAgentsOutput:
        """List all available sub-agents that can be invoked.

        Returns:
            ListAgentsOutput: A list of available agents with their names and display names.
        """
        # Generate a group ID for this tool execution
        group_id = generate_group_id("list_agents")

        emit_info(
            "\n[bold white on blue] LIST AGENTS [/bold white on blue]",
            message_group=group_id,
        )
        emit_divider(message_group=group_id)

        try:
            # Get available agents from the agent manager
            agents_dict = get_available_agents()

            # Convert to list of AgentInfo objects
            agents = [
                AgentInfo(name=name, display_name=display_name)
                for name, display_name in agents_dict.items()
            ]

            # Display the agents in the console
            for agent_item in agents:
                emit_system_message(
                    f"- [bold]{agent_item.name}[/bold]: {agent_item.display_name}",
                    message_group=group_id,
                )

            emit_divider(message_group=group_id)
            return ListAgentsOutput(agents=agents)

        except Exception as e:
            error_msg = f"Error listing agents: {str(e)}"
            emit_error(error_msg, message_group=group_id)
            emit_divider(message_group=group_id)
            return ListAgentsOutput(agents=[], error=error_msg)

    return list_agents


def register_invoke_agent(agent):
    """Register the invoke_agent tool with the provided agent.

    Args:
        agent: The agent to register the tool with
    """

    @agent.tool
    def invoke_agent(
        context: RunContext, agent_name: str, prompt: str
    ) -> AgentInvokeOutput:
        """Invoke a specific sub-agent with a given prompt.

        Args:
            agent_name: The name of the agent to invoke
            prompt: The prompt to send to the agent

        Returns:
            AgentInvokeOutput: The agent's response to the prompt
        """
        # Generate a group ID for this tool execution
        group_id = generate_group_id("invoke_agent", agent_name)

        emit_info(
            f"\n[bold white on blue] INVOKE AGENT [/bold white on blue] {agent_name}",
            message_group=group_id,
        )
        emit_divider(message_group=group_id)
        emit_system_message(f"Prompt: {prompt}", message_group=group_id)
        emit_divider(message_group=group_id)

        try:
            # Load the specified agent config
            agent_config = load_agent_config(agent_name)

            # Get the current model for creating a temporary agent
            model_name = get_model_name()
            models_config = ModelFactory.load_config()

            # Only proceed if we have a valid model configuration
            if model_name not in models_config:
                raise ValueError(f"Model '{model_name}' not found in configuration")

            model = ModelFactory.get_model(model_name, models_config)

            # Create a temporary agent instance to avoid interfering with current agent state
            instructions = agent_config.get_system_prompt()
            temp_agent = Agent(
                model=model,
                instructions=instructions,
                output_type=str,
                retries=3,
            )

            # Register the tools that the agent needs
            from code_puppy.tools import register_tools_for_agent

            agent_tools = agent_config.get_available_tools()
            register_tools_for_agent(temp_agent, agent_tools)

            # Run the temporary agent with the provided prompt
            result = temp_agent.run_sync(prompt)

            # Extract the response from the result
            response = result.output

            emit_system_message(f"Response: {response}", message_group=group_id)
            emit_divider(message_group=group_id)

            return AgentInvokeOutput(response=response, agent_name=agent_name)

        except Exception as e:
            error_msg = f"Error invoking agent '{agent_name}': {str(e)}"
            emit_error(error_msg, message_group=group_id)
            emit_divider(message_group=group_id)
            return AgentInvokeOutput(
                response=None, agent_name=agent_name, error=error_msg
            )

    return invoke_agent
