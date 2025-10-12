"""JSON-based agent configuration system."""

import json
from pathlib import Path
from typing import Dict, List, Optional

from .base_agent import BaseAgent


class JSONAgent(BaseAgent):
    """Agent configured from a JSON file."""

    def __init__(self, json_path: str):
        """Initialize agent from JSON file.

        Args:
            json_path: Path to the JSON configuration file.
        """
        super().__init__()
        self.json_path = json_path
        self._config = self._load_config()
        self._validate_config()

    def _load_config(self) -> Dict:
        """Load configuration from JSON file."""
        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            raise ValueError(
                f"Failed to load JSON agent config from {self.json_path}: {e}"
            )

    def _validate_config(self) -> None:
        """Validate required fields in configuration."""
        required_fields = ["name", "description", "system_prompt", "tools"]
        for field in required_fields:
            if field not in self._config:
                raise ValueError(
                    f"Missing required field '{field}' in JSON agent config: {self.json_path}"
                )

        # Validate tools is a list
        if not isinstance(self._config["tools"], list):
            raise ValueError(
                f"'tools' must be a list in JSON agent config: {self.json_path}"
            )

        # Validate system_prompt is string or list
        system_prompt = self._config["system_prompt"]
        if not isinstance(system_prompt, (str, list)):
            raise ValueError(
                f"'system_prompt' must be a string or list in JSON agent config: {self.json_path}"
            )

    @property
    def name(self) -> str:
        """Get agent name from JSON config."""
        return self._config["name"]

    @property
    def display_name(self) -> str:
        """Get display name from JSON config, fallback to name with emoji."""
        return self._config.get("display_name", f"{self.name.title()} 🤖")

    @property
    def description(self) -> str:
        """Get description from JSON config."""
        return self._config["description"]

    def get_system_prompt(self) -> str:
        """Get system prompt from JSON config."""
        system_prompt = self._config["system_prompt"]

        # If it's a list, join with newlines
        if isinstance(system_prompt, list):
            return "\n".join(system_prompt)

        return system_prompt

    def get_available_tools(self) -> List[str]:
        """Get available tools from JSON config."""
        # Filter out any tools that don't exist in our registry
        from code_puppy.tools import get_available_tool_names

        available_tools = get_available_tool_names()

        # Only return tools that are both requested and available
        # Also filter out 'final_result' which is not in our registry
        requested_tools = [
            tool for tool in self._config["tools"] if tool in available_tools
        ]

        return requested_tools

    def get_user_prompt(self) -> Optional[str]:
        """Get custom user prompt from JSON config."""
        return self._config.get("user_prompt")

    def get_tools_config(self) -> Optional[Dict]:
        """Get tool configuration from JSON config."""
        return self._config.get("tools_config")

    def refresh_config(self) -> None:
        """Reload the agent configuration from disk.

        This keeps long-lived agent instances in sync after external edits.
        """
        self._config = self._load_config()
        self._validate_config()

    def get_model_name(self) -> Optional[str]:
        """Get pinned model name from JSON config, if specified.

        Returns:
            Model name to use for this agent, or None to use global default.
        """
        result = self._config.get("model")
        if result is None:
            result = super().get_model_name()
        return result


def discover_json_agents() -> Dict[str, str]:
    """Discover JSON agent files in the user's agents directory.

    Returns:
        Dict mapping agent names to their JSON file paths.
    """
    from code_puppy.config import get_user_agents_directory

    agents = {}
    agents_dir = Path(get_user_agents_directory())

    if not agents_dir.exists() or not agents_dir.is_dir():
        return agents

    # Find all .json files in the agents directory
    for json_file in agents_dir.glob("*.json"):
        try:
            # Try to load and validate the agent
            agent = JSONAgent(str(json_file))
            agents[agent.name] = str(json_file)
        except Exception:
            # Skip invalid JSON agent files
            continue

    return agents
