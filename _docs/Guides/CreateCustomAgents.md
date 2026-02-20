# How to Create Custom Agents

## What You'll Learn
By the end of this guide, you'll be able to create your own custom agents with tailored personalities, tools, and instructions — then use them just like built-in agents.

## Prerequisites
- Code Puppy installed and running (see [Installation](../Getting-Started/Installation))
- At least one model configured (see [Configuration](../Getting-Started/Configuration))
- Familiarity with switching agents (see [How to Switch and Use Agents](UseAgents))

## Quick Version

The fastest way to create a custom agent is to use the built-in **Agent Creator**:

```
/agent agent-creator
```

Then describe what you want your agent to do. The Agent Creator walks you through the entire process interactively.

## Two Ways to Create Custom Agents

You can create custom agents either:
1. **Interactively** — Use the Agent Creator agent to guide you through the process
2. **Manually** — Write a JSON file by hand and place it in the agents directory

---

## Method 1: Using the Agent Creator (Recommended)

The Agent Creator is a specialized agent that helps you build custom agents step by step.

### 1. Switch to the Agent Creator

```
/agent agent-creator
```

You'll see a greeting like:

```
Hi! I'm the Agent Creator 🏗️ Let's build an awesome agent together!
```

### 2. Describe Your Agent

Tell the Agent Creator what kind of agent you want. For example:

```
I want an agent that helps me write documentation for Python projects.
```

The Agent Creator will:
- Ask clarifying questions about your agent's purpose
- Suggest appropriate tools based on your description
- Show you all available tools so you can add or remove any
- Ask whether you want to pin a specific model to the agent
- Generate a complete agent configuration
- Show you the JSON for review
- Save the file automatically once you confirm

### 3. Review and Confirm

The Agent Creator shows you the complete JSON configuration before saving. You can:
- **Approve it** — The agent file is created immediately
- **Request changes** — Ask to modify any field before saving

### 4. Start Using Your Agent

Once created, switch to your new agent immediately:

```
/agent your-agent-name
```

> [!TIP]
> Your custom agent will also appear in the interactive agent picker (`/agent`) alongside built-in agents.

---

## Method 2: Creating a JSON Agent File Manually

If you prefer full control, you can write the JSON configuration yourself.

### 1. Locate the Agents Directory

Custom agents are stored as `.json` files in your Code Puppy data directory:

| OS | Path |
|----|------|
| **macOS** | `~/Library/Application Support/code-puppy/agents/` |
| **Linux** | `~/.local/share/code-puppy/agents/` |
| **Windows** | `%LOCALAPPDATA%\code-puppy\agents\` |

> [!NOTE]
> The directory is created automatically the first time you use Code Puppy. If it doesn't exist yet, just create it.

### 2. Write the JSON File

Create a new `.json` file (e.g., `python-docs-writer.json`) with the following structure:

```json
{
  "name": "python-docs-writer",
  "display_name": "Python Docs Writer 📝",
  "description": "Helps write clear documentation for Python projects",
  "system_prompt": [
    "You are an expert technical writer specializing in Python documentation.",
    "You write clear, concise docstrings, README files, and API references.",
    "You follow Google-style Python docstring conventions.",
    "Always provide examples in your documentation."
  ],
  "tools": [
    "list_files",
    "read_file",
    "edit_file",
    "grep",
    "agent_share_your_reasoning"
  ],
  "user_prompt": "What would you like me to document today?"
}
```

### 3. Start Using It

Code Puppy automatically discovers new agent files — no restart needed:

```
/agent python-docs-writer
```

---

## JSON Agent Schema

Here's the complete schema for custom agent files:

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Unique identifier for the agent. Use kebab-case (e.g., `my-agent`). No spaces. |
| `description` | string | A short description of what the agent does. |
| `system_prompt` | string or array | Instructions that define the agent's behavior and personality. |
| `tools` | array | List of tool names the agent can use. |

### Optional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `display_name` | string | Title-cased name + 🤖 | A pretty name shown in the agent picker. |
| `user_prompt` | string | — | A custom greeting displayed when switching to this agent. |
| `tools_config` | object | — | Additional configuration for the agent's tools. |
| `model` | string | Global default | Pin a specific model for this agent (overrides the global model). |

### System Prompt Formats

You can write the system prompt as a single string:

```json
"system_prompt": "You are a helpful coding assistant that specializes in Python."
```

Or as an array of strings (recommended for longer prompts — each item is joined with a newline):

```json
"system_prompt": [
  "You are a helpful coding assistant.",
  "You specialize in Python development.",
  "Always provide clear explanations with examples."
]
```

---

## Available Tools

When creating an agent, choose the tools it needs from this list:

### File Operations
| Tool | Description |
|------|-------------|
| `list_files` | Browse and explore directory structures |
| `read_file` | Read file contents |
| `edit_file` | Create and modify files |
| `delete_file` | Remove files |
| `grep` | Search for text patterns across files |

### Command Execution
| Tool | Description |
|------|-------------|
| `agent_run_shell_command` | Execute terminal commands and scripts |

### Communication & Reasoning
| Tool | Description |
|------|-------------|
| `agent_share_your_reasoning` | Explain the agent's thought process (recommended for most agents) |
| `list_agents` | List all available sub-agents |
| `invoke_agent` | Delegate tasks to other agents |

> [!TIP]
> **Tool suggestions by agent type:**
> - **Code helper**: `read_file`, `edit_file`, `list_files`, `agent_run_shell_command`, `agent_share_your_reasoning`
> - **Code reviewer**: `list_files`, `read_file`, `grep`, `agent_share_your_reasoning`
> - **Documentation writer**: `read_file`, `edit_file`, `list_files`, `grep`, `agent_share_your_reasoning`
> - **System admin helper**: `agent_run_shell_command`, `list_files`, `read_file`, `agent_share_your_reasoning`
> - **Agent orchestrator**: `list_agents`, `invoke_agent`, `agent_share_your_reasoning`

---

## Pinning a Model to an Agent

You can pin a specific model so the agent always uses it, regardless of the global model setting.

### In the JSON file

Add a `model` field:

```json
{
  "name": "fast-helper",
  "description": "Quick answers using a fast model",
  "system_prompt": "You are a fast, concise coding helper.",
  "tools": ["read_file", "edit_file"],
  "model": "gpt-4.1-mini"
}
```

### From the Agent Picker

You can also pin or change a model from the interactive agent picker:

1. Open the agent picker: `/agent`
2. Navigate to the agent
3. Press **P** to open the model picker
4. Select a model to pin (or choose **unpin** to use the global default)

### Using the `/pin_model` command

```
/pin_model your-agent-name model-name
```

> [!NOTE]
> **When to pin a model:**
> - Code-heavy agents → use a strong coding model
> - Simple tasks → use a faster, cheaper model
> - Privacy-sensitive work → use a local model
> - Specialized analysis → use a model with the right strengths

---

## Cloning an Existing Agent

Want to start from an existing agent's configuration? Clone it and customize:

1. Open the agent picker: `/agent`
2. Navigate to the agent you want to clone
3. Press **C** to clone
4. The clone appears as `agent-name-clone-1`
5. Edit the clone's JSON file in the agents directory to customize it

> [!TIP]
> Cloning is great for creating variations of built-in agents. You get all their tools and system prompt as a starting point.

---

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

### Agent Manager

```json
{
  "name": "my-manager",
  "display_name": "Agent Manager 🎭",
  "description": "Orchestrates other agents to accomplish complex tasks",
  "system_prompt": [
    "You are an agent manager that orchestrates other specialized agents.",
    "You help users accomplish tasks by delegating to the appropriate sub-agent.",
    "You coordinate between multiple agents to get complex work done."
  ],
  "tools": ["list_agents", "invoke_agent", "agent_share_your_reasoning"],
  "user_prompt": "What can I help you accomplish today?"
}
```

---

## Editing and Deleting Custom Agents

### Editing

Edit the JSON file directly in the agents directory. Changes take effect the next time you switch to the agent — no restart required.

### Deleting Cloned Agents

From the agent picker:
1. Open the agent picker: `/agent`
2. Navigate to the cloned agent
3. Press **D** to delete

> [!WARNING]
> Only cloned agents (names ending in `-clone-N`) can be deleted from the picker. To delete a manually created agent, remove its JSON file from the agents directory.

---

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| Agent doesn't appear in the picker | Invalid JSON file | Check for syntax errors in the JSON file. All required fields (`name`, `description`, `system_prompt`, `tools`) must be present. |
| Agent has no tools | Invalid tool names | Make sure tool names match exactly (e.g., `read_file`, not `readFile`). |
| Agent uses the wrong model | No model pinned | Add a `model` field to the JSON or pin one via the agent picker. |
| "Agent already exists" error | Duplicate name | Each agent must have a unique `name` value. |
| Agent name has spaces | Invalid name format | Use kebab-case with hyphens, not spaces (e.g., `my-agent`, not `my agent`). |

## Related Guides
- [How to Switch and Use Agents](UseAgents)
- [How to Switch Models](SwitchModels)
- [How to Add Models from the Catalog](AddModels)
