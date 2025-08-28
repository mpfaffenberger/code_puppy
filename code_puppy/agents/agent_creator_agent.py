"""Agent Creator - helps users create new JSON agents."""

import json
import os
from typing import Dict, List, Optional

from .base_agent import BaseAgent
from code_puppy.config import get_user_agents_directory
from code_puppy.tools import get_available_tool_names


class AgentCreatorAgent(BaseAgent):
    """Specialized agent for creating JSON agent configurations."""

    @property
    def name(self) -> str:
        return "agent-creator"

    @property
    def display_name(self) -> str:
        return "Agent Creator 🏗️"

    @property
    def description(self) -> str:
        return "Helps you create new JSON agent configurations with proper schema validation"

    def get_system_prompt(self) -> str:
        available_tools = get_available_tool_names()
        agents_dir = get_user_agents_directory()

        return f"""You are the Agent Creator! 🏗️ Your mission is to help users create awesome JSON agent files.

You specialize in:
- Guiding users through the JSON agent schema
- Validating agent configurations
- Creating properly structured JSON agent files
- Explaining agent capabilities and best practices

## JSON Agent Schema

Here's the complete schema for JSON agent files:

```json
{{
  "name": "agent-name",              // REQUIRED: Unique identifier (no spaces, use hyphens)
  "display_name": "Agent Name 🤖",   // OPTIONAL: Pretty name with emoji
  "description": "What this agent does", // REQUIRED: Clear description
  "system_prompt": "Instructions...",    // REQUIRED: Agent instructions (string or array)
  "tools": ["tool1", "tool2"],        // REQUIRED: Array of tool names
  "user_prompt": "How can I help?",     // OPTIONAL: Custom greeting
  "tools_config": {{                    // OPTIONAL: Tool configuration
    "timeout": 60
  }}
}}
```

### Required Fields:
- `name`: Unique identifier (kebab-case recommended)
- `description`: What the agent does
- `system_prompt`: Agent instructions (string or array of strings)
- `tools`: Array of available tool names

### Optional Fields:
- `display_name`: Pretty display name (defaults to title-cased name + 🤖)
- `user_prompt`: Custom user greeting
- `tools_config`: Tool configuration object

### Available Tools:
{", ".join(f"- {tool}" for tool in available_tools)}

### System Prompt Formats:

**String format:**
```json
"system_prompt": "You are a helpful coding assistant that specializes in Python."
```

**Array format (recommended for multi-line prompts):**
```json
"system_prompt": [
  "You are a helpful coding assistant.",
  "You specialize in Python development.",
  "Always provide clear explanations."
]
```

## Agent Creation Process

1. **Ask for agent details**: name, description, purpose
2. **Help select appropriate tools** based on agent's purpose
3. **Craft system prompt** that defines agent behavior
4. **Generate complete JSON** with proper structure
5. **Save to agents directory**: `{agents_dir}`
6. **Validate and test** the new agent

## Best Practices

- Use descriptive names with hyphens (e.g., "python-tutor", "code-reviewer")
- Include relevant emoji in display_name for personality
- Keep system prompts focused and specific
- Only include tools the agent actually needs
- Test agents after creation

## Example Agents

**Python Tutor:**
```json
{{
  "name": "python-tutor",
  "display_name": "Python Tutor 🐍",
  "description": "Teaches Python programming concepts with examples",
  "system_prompt": [
    "You are a patient Python programming tutor.",
    "You explain concepts clearly with practical examples.",
    "You help beginners learn Python step by step.",
    "Always encourage learning and provide constructive feedback."
  ],
  "tools": ["read_file", "edit_file", "agent_share_your_reasoning"],
  "user_prompt": "What Python concept would you like to learn today?"
}}
```

**Code Reviewer:**
```json
{{
  "name": "code-reviewer",
  "display_name": "Code Reviewer 🔍",
  "description": "Reviews code for best practices, bugs, and improvements",
  "system_prompt": [
    "You are a senior software engineer doing code reviews.",
    "You focus on code quality, security, and maintainability.",
    "You provide constructive feedback with specific suggestions.",
    "You follow language-specific best practices and conventions."
  ],
  "tools": ["list_files", "read_file", "grep", "agent_share_your_reasoning"],
  "user_prompt": "Which code would you like me to review?"
}}
```

You're fun, enthusiastic, and love helping people create amazing agents! 🚀

Be interactive - ask questions, suggest improvements, and guide users through the process step by step.
After creating an agent, always explain how to use it with `/agent agent-name`.
"""

    def get_available_tools(self) -> List[str]:
        """Get all tools needed for agent creation."""
        return ["list_files", "read_file", "edit_file", "agent_share_your_reasoning"]

    def validate_agent_json(self, agent_config: Dict) -> List[str]:
        """Validate a JSON agent configuration.

        Args:
            agent_config: The agent configuration dictionary

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Check required fields
        required_fields = ["name", "description", "system_prompt", "tools"]
        for field in required_fields:
            if field not in agent_config:
                errors.append(f"Missing required field: '{field}'")

        if not errors:  # Only validate content if required fields exist
            # Validate name format
            name = agent_config.get("name", "")
            if not name or not isinstance(name, str):
                errors.append("'name' must be a non-empty string")
            elif " " in name:
                errors.append("'name' should not contain spaces (use hyphens instead)")

            # Validate tools is a list
            tools = agent_config.get("tools")
            if not isinstance(tools, list):
                errors.append("'tools' must be a list")
            else:
                available_tools = get_available_tool_names()
                invalid_tools = [tool for tool in tools if tool not in available_tools]
                if invalid_tools:
                    errors.append(
                        f"Invalid tools: {invalid_tools}. Available: {available_tools}"
                    )

            # Validate system_prompt
            system_prompt = agent_config.get("system_prompt")
            if not isinstance(system_prompt, (str, list)):
                errors.append("'system_prompt' must be a string or list of strings")
            elif isinstance(system_prompt, list):
                if not all(isinstance(item, str) for item in system_prompt):
                    errors.append("All items in 'system_prompt' list must be strings")

        return errors

    def get_agent_file_path(self, agent_name: str) -> str:
        """Get the full file path for an agent JSON file.

        Args:
            agent_name: The agent name

        Returns:
            Full path to the agent JSON file
        """
        agents_dir = get_user_agents_directory()
        return os.path.join(agents_dir, f"{agent_name}.json")

    def create_agent_json(self, agent_config: Dict) -> tuple[bool, str]:
        """Create a JSON agent file.

        Args:
            agent_config: The agent configuration dictionary

        Returns:
            Tuple of (success, message)
        """
        # Validate the configuration
        errors = self.validate_agent_json(agent_config)
        if errors:
            return False, "Validation errors:\n" + "\n".join(
                f"- {error}" for error in errors
            )

        # Get file path
        agent_name = agent_config["name"]
        file_path = self.get_agent_file_path(agent_name)

        # Check if file already exists
        if os.path.exists(file_path):
            return False, f"Agent '{agent_name}' already exists at {file_path}"

        # Create the JSON file
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(agent_config, f, indent=2, ensure_ascii=False)
            return True, f"Successfully created agent '{agent_name}' at {file_path}"
        except Exception as e:
            return False, f"Failed to create agent file: {e}"

    def get_user_prompt(self) -> Optional[str]:
        """Get the initial user prompt."""
        return "Hi! I'm the Agent Creator 🏗️ Let's build an awesome agent together!"
