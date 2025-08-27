# Agent Creator 🏗️

The **Agent Creator** is a specialized agent that helps you create custom JSON agent configurations for Code Puppy. It guides you through the entire process of building new agents with proper schema validation.

## Quick Start

1. **Switch to the Agent Creator**:
   ```bash
   /agent agent-creator
   ```

2. **Ask for help creating an agent**:
   ```
   I want to create a Python tutor agent
   ```

3. **Follow the guided process** to define your agent's:
   - Name and description
   - Available tools
   - System prompt and behavior
   - Custom settings

4. **Test your new agent**:
   ```bash
   /agent your-new-agent-name
   ```

## JSON Agent Schema

Agent Creator helps you build JSON files following this schema:

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

### Required Fields
- **`name`**: Unique identifier (use kebab-case, no spaces)
- **`description`**: What the agent does
- **`system_prompt`**: Agent instructions (string or array)
- **`tools`**: Array of available tool names

### Optional Fields
- **`display_name`**: Pretty display name (defaults to title-cased name + 🤖)
- **`user_prompt`**: Custom user greeting
- **`tools_config`**: Tool configuration object

## Available Tools

Your agents can use these tools:

- **`list_files`**: Directory and file listing
- **`read_file`**: File content reading
- **`grep`**: Text search across files
- **`edit_file`**: File editing and creation
- **`delete_file`**: File deletion
- **`agent_run_shell_command`**: Shell command execution
- **`agent_share_your_reasoning`**: Share reasoning with user

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

## Example Agents

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

## Agent Creation Workflow

The Agent Creator guides you through this process:

1. **Define Purpose**: What should your agent do?
2. **Choose Name**: Kebab-case identifier (e.g., "python-tutor")
3. **Write Description**: Clear, concise explanation
4. **Select Tools**: Choose appropriate tools for the agent's tasks
5. **Craft System Prompt**: Define the agent's behavior and personality
6. **Add Optional Settings**: Custom greeting, tool config, etc.
7. **Validate & Create**: Agent Creator validates and saves the JSON file
8. **Test**: Switch to your new agent and try it out!

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

## File Locations

JSON agents are stored in:
- **macOS**: `~/Library/Application Support/code-puppy/agents/`
- **Linux**: `~/.local/share/code-puppy/agents/`
- **Windows**: `%APPDATA%\code-puppy\agents\`

## Troubleshooting

### Agent Not Found
- Ensure the JSON file is in the correct directory
- Check that the JSON is valid
- Restart Code Puppy or clear agent cache

### Validation Errors
- Use Agent Creator for guided validation
- Check required fields are present
- Verify tool names are correct
- Ensure name doesn't contain spaces

### Permission Issues
- Make sure the agents directory is writable
- Check file permissions on created JSON files

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

## Contributing Agent Templates

Consider sharing useful agent configurations:
1. Create your agent JSON file
2. Test it thoroughly
3. Submit a pull request

---

**Happy Agent Building!** 🚀 The Agent Creator makes it easy to customize Code Puppy for your specific workflows and needs.
