# 🐶 Code Puppy 🐶
![Build Status](https://img.shields.io/badge/build-passing-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-95%25-brightgreen)
  <a href="https://github.com/mpfaffenberger/code_puppy"><img src="https://img.shields.io/pypi/pyversions/pydantic-ai.svg" alt="versions"></a>
  <a href="https://github.com/mpfaffenberger/code_puppy/blob/main/LICENSE"><img src="https://img.shields.io/github/license/pydantic/pydantic-ai.svg?v" alt="license"></a>

*"Who needs an IDE?"* - someone, probably.

## Overview

*This project was coded angrily in reaction to Windsurf and Cursor removing access to models and raising prices.* 

*You could also run 50 code puppies at once if you were insane enough.*

*Would you rather plow a field with one ox or 1024 puppies?* 
    - If you pick the ox, better slam that back button in your browser.
    

Code Puppy is an AI-powered code generation agent, designed to understand programming tasks, generate high-quality code, and explain its reasoning similar to tools like Windsurf and Cursor. 

## Quick start

`uvx code-puppy -i`


## Features

- **Multi-language support**: Capable of generating code in various programming languages.
- **Interactive CLI**: A command-line interface for interactive use.
- **Detailed explanations**: Provides insights into generated code to understand its logic and structure.

## Command Line Animation

![Code Puppy](code_puppy.gif)

## Installation

`pip install code-puppy`

## Usage
```bash
export MODEL_NAME=gpt-5 # or gemini-2.5-flash-preview-05-20 as an example for Google Gemini models
export OPENAI_API_KEY=<your_openai_api_key> # or GEMINI_API_KEY for Google Gemini models
export CEREBRAS_API_KEY=<your_cerebras_api_key> # for Cerebras models
export YOLO_MODE=true # to bypass the safety confirmation prompt when running shell commands

# or ...

export AZURE_OPENAI_API_KEY=...
export AZURE_OPENAI_ENDPOINT=...

code-puppy --interactive
```
Running in a super weird corporate environment? 

Try this:
```bash
export MODEL_NAME=my-custom-model
export YOLO_MODE=true
export MODELS_JSON_PATH=/path/to/custom/models.json
```

```json
{
    "my-custom-model": {
        "type": "custom_openai",
        "name": "o4-mini-high",
        "max_requests_per_minute": 100,
        "max_retries": 3,
        "retry_base_delay": 10,
        "custom_endpoint": {
            "url": "https://my.custom.endpoint:8080",
            "headers": {
                "X-Api-Key": "<Your_API_Key>",
                "Some-Other-Header": "<Some_Value>"
            },
            "ca_certs_path": "/path/to/cert.pem"
        }
    }
}
```
Note that the `OPENAI_API_KEY` or `CEREBRAS_API_KEY` env variable must be set when using `custom_openai` endpoints.

Open an issue if your environment is somehow weirder than mine.

Run specific tasks or engage in interactive mode:

```bash
# Execute a task directly
code-puppy "write me a C++ hello world program in /tmp/main.cpp then compile it and run it"
```

## Requirements

- Python 3.9+
- OpenAI API key (for GPT models)
- Gemini API key (for Google's Gemini models)
- Cerebras API key (for Cerebras models)
- Anthropic key (for Claude models)
- Ollama endpoint available

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Agent Rules
We support AGENT.md files for defining coding standards and styles that your code should comply with. These rules can cover various aspects such as formatting, naming conventions, and even design guidelines.

For examples and more information about agent rules, visit [https://agent.md](https://agent.md)

## Using MCP Servers for External Tools

Code Puppy supports **MCP (Model Context Protocol) servers** to give you access to external code tools and advanced features like code search, documentation lookups, and more—including Context7 (https://context7.com/) integration for deep docs and search!

### What is an MCP Server?
An MCP server is a standalone process (can be local or remote) that offers specialized functionality (plugins, doc search, code analysis, etc.). Code Puppy can connect to one or more MCP servers at startup, unlocking these extra commands inside your coding agent.

### Configuration
Create a config file at `~/.code_puppy/mcp_servers.json`. Here’s an example that connects to a local Context7 MCP server:

```json
{
  "mcp_servers": {
     "context7": { 
        "url": "https://mcp.context7.com/sse"
     }
  }
}
```

You can list multiple objects (one per server).

### How to Use
- Drop the config file in `~/.code_puppy/mcp_servers.json`.
- Start your MCP (like context7, or anything compatible).
- Run Code Puppy as usual. It’ll discover and use all configured MCP servers.

#### Example usage
```bash
code-puppy --interactive
# Then ask: Use context7 to look up FastAPI docs!
```

That’s it!
If you need to run more exotic setups or connect to remote MCPs, just update your `mcp_servers.json` accordingly.

**NOTE:** Want to add your own server or tool? Just follow the config pattern above—no code changes needed!

---

## Create your own Agent!!!

Code Puppy features a flexible agent system that allows you to work with specialized AI assistants tailored for different coding tasks. The system supports both built-in Python agents and custom JSON agents that you can create yourself.

## Quick Start

### Check Current Agent
```bash
/agent
```
Shows current active agent and all available agents

### Switch Agent
```bash
/agent <agent-name>
```
Switches to the specified agent

### Create New Agent
```bash
/agent agent-creator
```
Switches to the Agent Creator for building custom agents

## Available Agents

### Code-Puppy 🐶 (Default)
- **Name**: `code-puppy`
- **Specialty**: General-purpose coding assistant
- **Personality**: Playful, sarcastic, pedantic about code quality
- **Tools**: Full access to all tools
- **Best for**: All coding tasks, file management, execution
- **Principles**: Clean, concise code following YAGNI, SRP, DRY principles
- **File limit**: Max 600 lines per file (enforced!)

### Agent Creator 🏗️
- **Name**: `agent-creator`
- **Specialty**: Creating custom JSON agent configurations
- **Tools**: File operations, reasoning
- **Best for**: Building new specialized agents
- **Features**: Schema validation, guided creation process

## Agent Types

### Python Agents
Built-in agents implemented in Python with full system integration:
- Discovered automatically from `code_puppy/agents/` directory
- Inherit from `BaseAgent` class
- Full access to system internals
- Examples: `code-puppy`, `agent-creator`

### JSON Agents
User-created agents defined in JSON files:
- Stored in user's agents directory
- Easy to create, share, and modify
- Schema-validated configuration
- Custom system prompts and tool access

## Creating Custom JSON Agents

### Using Agent Creator (Recommended)

1. **Switch to Agent Creator**:
   ```bash
   /agent agent-creator
   ```

2. **Request agent creation**:
   ```
   I want to create a Python tutor agent
   ```

3. **Follow guided process** to define:
   - Name and description
   - Available tools
   - System prompt and behavior
   - Custom settings

4. **Test your new agent**:
   ```bash
   /agent your-new-agent-name
   ```

### Manual JSON Creation

Create JSON files in your agents directory following this schema:

```json
{
  "name": "agent-name",              // REQUIRED: Unique identifier (kebab-case)
  "display_name": "Agent Name 🤖",   // OPTIONAL: Pretty name with emoji
  "description": "What this agent does", // REQUIRED: Clear description
  "system_prompt": "Instructions...",    // REQUIRED: Agent instructions
  "tools": ["tool1", "tool2"],        // REQUIRED: Array of tool names
  "user_prompt": "How can I help?",     // OPTIONAL: Custom greeting
  "tools_config": {                    // OPTIONAL: Tool configuration
    "timeout": 60
  }
}
```

#### Required Fields
- **`name`**: Unique identifier (kebab-case, no spaces)
- **`description`**: What the agent does
- **`system_prompt`**: Agent instructions (string or array)
- **`tools`**: Array of available tool names

#### Optional Fields
- **`display_name`**: Pretty display name (defaults to title-cased name + 🤖)
- **`user_prompt`**: Custom user greeting
- **`tools_config`**: Tool configuration object

## Available Tools

Agents can access these tools based on their configuration:

- **`list_files`**: Directory and file listing
- **`read_file`**: File content reading
- **`grep`**: Text search across files
- **`edit_file`**: File editing and creation
- **`delete_file`**: File deletion
- **`agent_run_shell_command`**: Shell command execution
- **`agent_share_your_reasoning`**: Share reasoning with user

### Tool Access Examples
- **Read-only agent**: `["list_files", "read_file", "grep"]`
- **File editor agent**: `["list_files", "read_file", "edit_file"]`
- **Full access agent**: All tools (like Code-Puppy)

## System Prompt Formats

### String Format
```json
{
  "system_prompt": "You are a helpful coding assistant that specializes in Python development."
}
```

### Array Format (Recommended)
```json
{
  "system_prompt": [
    "You are a helpful coding assistant.",
    "You specialize in Python development.",
    "Always provide clear explanations.",
    "Include practical examples in your responses."
  ]
}
```

## Example JSON Agents

### Python Tutor
```json
{
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
}
```

### Code Reviewer
```json
{
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
}
```

### DevOps Helper
```json
{
  "name": "devops-helper",
  "display_name": "DevOps Helper ⚙️",
  "description": "Helps with Docker, CI/CD, and deployment tasks",
  "system_prompt": [
    "You are a DevOps engineer specialized in containerization and CI/CD.",
    "You help with Docker, Kubernetes, GitHub Actions, and deployment.",
    "You provide practical, production-ready solutions.",
    "You always consider security and best practices."
  ],
  "tools": [
    "list_files",
    "read_file",
    "edit_file",
    "agent_run_shell_command",
    "agent_share_your_reasoning"
  ],
  "user_prompt": "What DevOps task can I help you with today?"
}
```

## File Locations

### JSON Agents Directory
- **All platforms**: `~/.code_puppy/agents/`

### Python Agents Directory
- **Built-in**: `code_puppy/agents/` (in package)

## Best Practices

### Naming
- Use kebab-case (hyphens, not spaces)
- Be descriptive: "python-tutor" not "tutor"
- Avoid special characters

### System Prompts
- Be specific about the agent's role
- Include personality traits
- Specify output format preferences
- Use array format for multi-line prompts

### Tool Selection
- Only include tools the agent actually needs
- Most agents need `agent_share_your_reasoning`
- File manipulation agents need `read_file`, `edit_file`
- Research agents need `grep`, `list_files`

### Display Names
- Include relevant emoji for personality
- Make it friendly and recognizable
- Keep it concise

## System Architecture

### Agent Discovery
The system automatically discovers agents by:
1. **Python Agents**: Scanning `code_puppy/agents/` for classes inheriting from `BaseAgent`
2. **JSON Agents**: Scanning user's agents directory for `*-agent.json` files
3. Instantiating and registering discovered agents

### JSONAgent Implementation
JSON agents are powered by the `JSONAgent` class (`code_puppy/agents/json_agent.py`):
- Inherits from `BaseAgent` for full system integration
- Loads configuration from JSON files with robust validation
- Supports all BaseAgent features (tools, prompts, settings)
- Cross-platform user directory support
- Built-in error handling and schema validation

### BaseAgent Interface
Both Python and JSON agents implement this interface:
- `name`: Unique identifier
- `display_name`: Human-readable name with emoji
- `description`: Brief description of purpose
- `get_system_prompt()`: Returns agent-specific system prompt
- `get_available_tools()`: Returns list of tool names

### Agent Manager Integration
The `agent_manager.py` provides:
- Unified registry for both Python and JSON agents
- Seamless switching between agent types
- Configuration persistence across sessions
- Automatic caching for performance

### System Integration
- **Command Interface**: `/agent` command works with all agent types
- **Tool Filtering**: Dynamic tool access control per agent
- **Main Agent System**: Loads and manages both agent types
- **Cross-Platform**: Consistent behavior across all platforms

## Adding Python Agents

To create a new Python agent:

1. Create file in `code_puppy/agents/` (e.g., `my_agent.py`)
2. Implement class inheriting from `BaseAgent`
3. Define required properties and methods
4. Agent will be automatically discovered

Example implementation:

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
        ]
```

## Troubleshooting

### Agent Not Found
- Ensure JSON file is in correct directory
- Check JSON syntax is valid
- Restart Code Puppy or clear agent cache
- Verify filename ends with `-agent.json`

### Validation Errors
- Use Agent Creator for guided validation
- Check all required fields are present
- Verify tool names are correct
- Ensure name uses kebab-case

### Permission Issues
- Make sure agents directory is writable
- Check file permissions on JSON files
- Verify directory path exists

## Advanced Features

### Tool Configuration
```json
{
  "tools_config": {
    "timeout": 120,
    "max_retries": 3
  }
}
```

### Multi-line System Prompts
```json
{
  "system_prompt": [
    "Line 1 of instructions",
    "Line 2 of instructions",
    "Line 3 of instructions"
  ]
}
```

## Future Extensibility

The agent system supports future expansion:

- **Specialized Agents**: Code reviewers, debuggers, architects
- **Domain-Specific Agents**: Web dev, data science, DevOps, mobile
- **Personality Variations**: Different communication styles
- **Context-Aware Agents**: Adapt based on project type
- **Team Agents**: Shared configurations for coding standards
- **Plugin System**: Community-contributed agents

## Benefits of JSON Agents

1. **Easy Customization**: Create agents without Python knowledge
2. **Team Sharing**: JSON agents can be shared across teams
3. **Rapid Prototyping**: Quick agent creation for specific workflows
4. **Version Control**: JSON agents are git-friendly
5. **Built-in Validation**: Schema validation with helpful error messages
6. **Cross-Platform**: Works consistently across all platforms
7. **Backward Compatible**: Doesn't affect existing Python agents

## Implementation Details

### Files in System
- **Core Implementation**: `code_puppy/agents/json_agent.py`
- **Agent Discovery**: Integrated in `code_puppy/agents/agent_manager.py`
- **Command Interface**: Works through existing `/agent` command
- **Testing**: Comprehensive test suite in `tests/test_json_agents.py`

### JSON Agent Loading Process
1. System scans `~/.code_puppy/agents/` for `*-agent.json` files
2. `JSONAgent` class loads and validates each JSON configuration
3. Agents are registered in unified agent registry
4. Users can switch to JSON agents via `/agent <name>` command
5. Tool access and system prompts work identically to Python agents

### Error Handling
- Invalid JSON syntax: Clear error messages with line numbers
- Missing required fields: Specific field validation errors
- Invalid tool names: Warning with list of available tools
- File permission issues: Helpful troubleshooting guidance

## Future Possibilities

- **Agent Templates**: Pre-built JSON agents for common tasks
- **Visual Editor**: GUI for creating JSON agents
- **Hot Reloading**: Update agents without restart
- **Agent Marketplace**: Share and discover community agents
- **Enhanced Validation**: More sophisticated schema validation
- **Team Agents**: Shared configurations for coding standards

## Contributing

### Sharing JSON Agents
1. Create and test your agent thoroughly
2. Ensure it follows best practices
3. Submit a pull request with agent JSON
4. Include documentation and examples
5. Test across different platforms

### Python Agent Contributions
1. Follow existing code style
2. Include comprehensive tests
3. Document the agent's purpose and usage
4. Submit pull request for review
5. Ensure backward compatibility

### Agent Templates
Consider contributing agent templates for:
- Code reviewers and auditors
- Language-specific tutors
- DevOps and deployment helpers
- Documentation writers
- Testing specialists

---

**Happy Agent Building!** 🚀 Code Puppy now supports both Python and JSON agents, making it easy for anyone to create custom AI coding assistants! 🐶✨


## Conclusion
By using Code Puppy, you can maintain code quality and adhere to design guidelines with ease.
