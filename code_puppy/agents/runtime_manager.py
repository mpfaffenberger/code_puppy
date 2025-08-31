"""
Runtime agent manager that ensures proper agent instance updates.

This module provides a wrapper around the agent singleton that ensures
all references to the agent are properly updated when it's reloaded.
"""

from typing import Optional, Any
from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from code_puppy.messaging.message_queue import emit_info, emit_warning


class RuntimeAgentManager:
    """
    Manages the runtime agent instance and ensures proper updates.
    
    This class acts as a proxy that always returns the current agent instance,
    ensuring that when the agent is reloaded, all code using this manager
    automatically gets the updated instance.
    """
    
    def __init__(self):
        """Initialize the runtime agent manager."""
        self._agent: Optional[Agent] = None
        self._last_model_name: Optional[str] = None
        
    def get_agent(self, force_reload: bool = False) -> Agent:
        """
        Get the current agent instance.
        
        This method always returns the most recent agent instance,
        automatically handling reloads when the model changes.
        
        Args:
            force_reload: If True, force a reload of the agent
            
        Returns:
            The current agent instance
        """
        from code_puppy.agent import get_code_generation_agent
        
        # Always get the current singleton - this ensures we have the latest
        current_agent = get_code_generation_agent(force_reload=force_reload)
        self._agent = current_agent
        
        return self._agent
    
    def reload_agent(self) -> Agent:
        """
        Force reload the agent.
        
        This is typically called after MCP servers are started/stopped.
        
        Returns:
            The newly loaded agent instance
        """
        emit_info("[bold cyan]Reloading agent with updated configuration...[/bold cyan]")
        return self.get_agent(force_reload=True)
    
    async def run_with_mcp(self, prompt: str, usage_limits: Optional[UsageLimits] = None, **kwargs) -> Any:
        """
        Run the agent with MCP servers.
        
        This method ensures we're always using the current agent instance.
        
        Args:
            prompt: The user prompt to process
            usage_limits: Optional usage limits for the agent
            **kwargs: Additional arguments to pass to agent.run (e.g., message_history)
            
        Returns:
            The agent's response
        """
        agent = self.get_agent()
        
        try:
            async with agent.run_mcp_servers():
                return await agent.run(prompt, usage_limits=usage_limits, **kwargs)
        except Exception as mcp_error:
            emit_warning(f"MCP server error: {str(mcp_error)}")
            emit_warning("Running without MCP servers...")
            # Run without MCP servers as fallback
            return await agent.run(prompt, usage_limits=usage_limits, **kwargs)
    
    async def run(self, prompt: str, usage_limits: Optional[UsageLimits] = None, **kwargs) -> Any:
        """
        Run the agent without explicitly managing MCP servers.
        
        Args:
            prompt: The user prompt to process
            usage_limits: Optional usage limits for the agent
            **kwargs: Additional arguments to pass to agent.run (e.g., message_history)
            
        Returns:
            The agent's response
        """
        agent = self.get_agent()
        return await agent.run(prompt, usage_limits=usage_limits, **kwargs)
    
    def __getattr__(self, name: str) -> Any:
        """
        Proxy all other attribute access to the current agent.
        
        This allows the manager to be used as a drop-in replacement
        for direct agent access.
        
        Args:
            name: The attribute name to access
            
        Returns:
            The attribute from the current agent
        """
        agent = self.get_agent()
        return getattr(agent, name)


# Global singleton instance
_runtime_manager: Optional[RuntimeAgentManager] = None


def get_runtime_agent_manager() -> RuntimeAgentManager:
    """
    Get the global runtime agent manager instance.
    
    Returns:
        The singleton RuntimeAgentManager instance
    """
    global _runtime_manager
    if _runtime_manager is None:
        _runtime_manager = RuntimeAgentManager()
    return _runtime_manager