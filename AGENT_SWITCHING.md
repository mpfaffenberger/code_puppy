# Agent Switching Feature

Code Puppy supports a simple agent switching system with extensible architecture. Currently there is one default agent, but the system is designed to easily support adding more specialized agents in the future.

## Available Agents

### Code-Puppy 🐶 (Default)
- **Name**: `code-puppy`
- **Specialty**: General-purpose coding assistant
- **Personality**: Playful, sarcastic, pedantic about code quality
- **Tools**: Full access to all tools
- **Best for**: All coding tasks, file management, execution

## Usage

### Check Current Agent
```bash
/agent
```

This will show:
- Current active agent
- All available agents with descriptions
- Usage instructions

### Switch to a Specific Agent
```bash
/agent <agent-name>
```

Examples:
```bash
/agent code-puppy    # Switch to Code-Puppy (currently the only agent)
```

### Check Current Agent in Status
```bash
/show
```

This will display the current agent along with other system information.

## Agent System Architecture

The agent switching system is built with extensibility in mind:

### Agent Configuration
Agents are defined in `code_puppy/agents/` with each agent implementing the `BaseAgent` interface:

- `name`: Unique identifier
- `display_name`: Human-readable name with emoji
- `description`: Brief description of the agent's purpose
- `get_system_prompt()`: Returns the agent-specific system prompt
- `get_available_tools()`: Returns list of tool names the agent should have access to

### Adding New Python Agents
To add a new Python agent:

1. Create a new file in `code_puppy/agents/` (e.g., `new_agent.py`)
2. Implement a class that inherits from `BaseAgent`
3. Define the required properties and methods
4. The agent will be automatically discovered and available

Example agent implementation:

```python
from .base_agent import BaseAgent

class MyCustomAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "my-agent"
    
    @property
    def display_name(self) -> str:
        return "My Custom Agent ✨"
    
    @property
    def description(self) -> str:
        return "A custom agent for specialized tasks"
    
    def get_system_prompt(self) -> str:
        return "Your custom system prompt here..."
    
    def get_available_tools(self) -> list[str]:
        return [
            "list_files",
            "read_file", 
            "grep",
            "edit_file",
            "delete_file",
            "agent_run_shell_command",
            "agent_share_your_reasoning"
        ]  # Specify which tools this agent should have access to
```

### Adding New JSON Agents
To add a new JSON agent:

1. Create a JSON file in your user agents directory ending with `-agent.json`
2. The file will be automatically discovered on next startup

**JSON Agent Format:**
```json
{
  "name": "my-custom-agent",
  "display_name": "My Custom Agent 🔧",
  "description": "A specialized agent for my specific needs",
  "system_prompt": "You are a helpful assistant specialized in...",
  "tools": [
    "list_files",
    "read_file",
    "edit_file"
  ],
  "user_prompt": "Enter your request:",
  "tools_config": {
    "timeout": 60
  },
  "model_settings": {
    "temperature": 0.7
  }
}
```

**Required Fields:**
- `name`: Unique identifier for the agent
- `description`: Brief description of the agent's purpose
- `system_prompt`: The agent's system prompt (string or array of strings)
- `tools`: Array of tool names the agent should have access to

**Optional Fields:**
- `display_name`: Custom display name (defaults to formatted name + 🤖)
- `user_prompt`: Custom prompt shown to user
- `tools_config`: Tool-specific configuration
- `model_settings`: Model-specific settings

**System Prompt Formats:**
- **String**: Single prompt text
- **Array**: Multiple lines joined with newlines

### Tool Access Control
Agents explicitly define which tools they have access to through `get_available_tools()`:

**Available Tools:**
- `list_files`: Directory and file listing
- `read_file`: File content reading
- `grep`: Text search across files
- `edit_file`: File editing and creation
- `delete_file`: File deletion
- `agent_run_shell_command`: Shell command execution
- `agent_share_your_reasoning`: Share reasoning with user

**Examples:**
- Read-only agent: `["list_files", "read_file", "grep"]`
- File editor agent: `["list_files", "read_file", "edit_file"]`
- Full access agent: All tools (like Code-Puppy)

### Configuration Persistence
The current agent selection is saved in the configuration file and persists between sessions.

## Implementation Details

### Agent Discovery
The system automatically discovers agents by:
1. **Python Agents**: Scanning the `code_puppy/agents/` directory for Python files containing classes that inherit from `BaseAgent`
2. **JSON Agents**: Scanning the user's agents directory for JSON files ending with `-agent.json`
3. Instantiating and registering these agents

**User Agents Directory:**
- **All platforms**: `~/.code_puppy/agents/`

### Caching
Agent configurations are cached to improve performance. The cache can be cleared manually if needed.

### Integration Points
- **Main Agent (`agent.py`)**: Modified to load agent-specific system prompts and tool exclusions
- **Tools System**: Updated to support dynamic tool exclusion based on current agent
- **Command Handler**: Provides `/agent` command interface
- **Configuration**: Seamlessly integrated with existing config system

## Future Extensibility

While Code-Puppy currently ships with one default agent, the architecture supports:

- **Specialized Agents**: Code reviewers, debuggers, architects, documentation writers
- **Domain-Specific Agents**: Web development, data science, DevOps, mobile development
- **Personality Variations**: Different communication styles and approaches
- **Context-Aware Agents**: Agents that adapt based on project type or file extensions
- **User-Defined Agents**: JSON-based agents for custom workflows and specialized tasks
- **Team Agents**: Shared JSON agents for team-specific coding standards and practices

The agent switching feature provides a foundation for Code Puppy to grow into a more versatile and specialized coding assistant ecosystem!
