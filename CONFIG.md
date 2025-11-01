# 🐶 Code Puppy Configuration Guide

This comprehensive guide covers all configuration options available in Code Puppy.

## Table of Contents

1. [Configuration Files](#configuration-files)
2. [Environment Variables](#environment-variables)
3. [puppy.cfg Settings](#puppycfg-settings)
4. [Model Configuration](#model-configuration)
5. [MCP Server Configuration](#mcp-server-configuration)
6. [Agent Configuration](#agent-configuration)
7. [Session Management](#session-management)
8. [TUI Theme Configuration](#tui-theme-configuration)
9. [Plugin Configuration](#plugin-configuration)
10. [Custom Commands](#custom-commands)
11. [Advanced Configuration](#advanced-configuration)

---

## Configuration Files

All Code Puppy configuration files are stored in `~/.code_puppy/`:

| File | Purpose |
|------|---------|
| `puppy.cfg` | Main configuration file (INI format) |
| `models.json` | Built-in model configurations |
| `extra_models.json` | User-defined custom models and round-robin configurations |
| `mcp_servers.json` | MCP (Model Context Protocol) server configurations |
| `command_history.txt` | Command history with timestamps |
| `dbos_store.sqlite` | DBOS durable execution database (if enabled) |
| `agents/*.json` | Custom JSON agent definitions |
| `contexts/*.pkl` | Saved session contexts |
| `autosaves/*.pkl` | Auto-saved sessions |

---

## TUI Settings Modal 🎨

**New in TUI Mode!** Code Puppy now features a comprehensive, user-friendly Settings Modal with 6 organized tabs.

### Accessing the Settings Modal

- **Keybinding**: Press `Ctrl+3` in TUI mode
- **Footer**: Click on "Settings" in the app footer
- The modal opens as an overlay on your current session

### Settings Tabs

#### 1. **General**
Configure basic settings:
- Puppy's Name
- Owner's Name
- **YOLO Mode** (auto-confirm commands) ✨ Now configurable!
- Allow Agent Recursion

#### 2. **Models & AI**
AI model configuration:
- Default Model (dynamically loaded from models.json)
- Vision Model (VQA)
- GPT-5 Reasoning Effort (Low/Medium/High)

#### 3. **History & Context**
Context management settings:
- Compaction Strategy (Summarization/Truncation)
- Compaction Threshold (percentage)
- Protected Recent Tokens
- Auto-Save Session
- Max Autosaved Sessions

#### 4. **Appearance**
Visual customization:
- Diff Display Style (Plain Text/Highlighted)
- Diff Addition Color
- Diff Deletion Color
- Diff Context Lines

#### 5. **Agents & Integrations**
Advanced integration settings:
- Agent Model Pinning (table view of all agents)
- Disable All MCP Servers
- Enable DBOS (durable execution)

#### 6. **API Keys & Status** (Read-Only)
Diagnostic information showing:
- Environment variable status (✔️ Set / ❌ Not Set)
- OPENAI_API_KEY
- GEMINI_API_KEY
- ANTHROPIC_API_KEY
- CEREBRAS_API_KEY
- SYN_API_KEY
- AZURE_OPENAI_API_KEY
- AZURE_OPENAI_ENDPOINT

### Features

- **Live Validation**: Input values are validated before saving
- **Tooltips**: Each setting has a helpful description
- **Easy Navigation**: Use Tab key to move between tabs
- **Esc to Cancel**: Press Escape to close without saving
- **Immediate Effect**: Settings take effect immediately after saving

---

## Environment Variables

### API Keys

Configure API keys for different model providers:

```bash
# OpenAI (GPT models)
export OPENAI_API_KEY=sk-...

# Google Gemini
export GEMINI_API_KEY=...

# Anthropic Claude
export ANTHROPIC_API_KEY=...

# Cerebras
export CEREBRAS_API_KEY=csk-...

# Synthetic Provider (open-source models)
export SYN_API_KEY=...

# Azure OpenAI
export AZURE_OPENAI_API_KEY=...
export AZURE_OPENAI_ENDPOINT=...
```

### Model Configuration

```bash
# Default model to use (must exist in models.json)
export MODEL_NAME=gpt-5

# Path to custom models.json file (optional)
export MODELS_JSON_PATH=/path/to/custom/models.json
```

### DBOS (Durable Execution)

```bash
# Connect to DBOS Management Console (optional)
export DBOS_CONDUCTOR_KEY=your-conductor-key

# DBOS logging level (ERROR, WARNING, INFO, DEBUG)
# Default: ERROR
export DBOS_LOG_LEVEL=ERROR

# Database URL for DBOS (SQLite or PostgreSQL)
# Default: sqlite:///~/.code_puppy/dbos_store.sqlite
export DBOS_SYSTEM_DATABASE_URL=postgresql://postgres:dbos@localhost:5432/postgres
```

---

## puppy.cfg Settings

The `~/.code_puppy/puppy.cfg` file stores persistent configuration. You can modify it:
- **In TUI mode**: Press `Ctrl+3` to open the comprehensive Settings modal (recommended)
- **In interactive mode**: Use the `/set` command
- **Manually**: Edit the file directly with a text editor

### Basic Settings

```ini
[puppy]
# Your puppy's name (shown in status)
puppy_name = Puppy

# Your name (puppy's owner)
owner_name = Master
```

### Model Settings

```ini
# Active model (from models.json or extra_models.json)
model = gpt-5

# VQA (Vision Question Answering) model
vqa_model_name = gpt-4.1

# OpenAI reasoning effort for GPT-5 models (low, medium, high)
# Default: medium
openai_reasoning_effort = medium
```

### Behavior Settings

```ini
# YOLO mode - auto-confirm commands without prompting
# Default: true
# NOTE: In TUI mode, you can now toggle this via Settings (Ctrl+3)!
yolo_mode = true

# Enable/disable MCP servers
# Default: false
disable_mcp = false

# Allow agent recursion (agents calling other agents)
# Default: true
allow_recursion = true

# HTTP/2 support for httpx clients
# Default: false
http2 = false

# Enable DBOS durable execution
# Default: false
enable_dbos = false
```

### Message History & Compaction

```ini
# Number of recent tokens protected from summarization
# Default: 50000, Max: 75% of model context length
protected_token_count = 50000

# Context usage threshold that triggers compaction (0.0-1.0)
# Default: 0.85 (85% of context length)
compaction_threshold = 0.85

# Compaction strategy: 'summarization' or 'truncation'
# Default: truncation
compaction_strategy = truncation

# Maximum number of agent requests/steps
# Default: 100
message_limit = 100
```

### Session Management

```ini
# Auto-save session after each response
# Default: true
auto_save_session = true

# Maximum number of autosave sessions to keep (0 = unlimited)
# Default: 20
max_saved_sessions = 20
```

### Diff Display Configuration

```ini
# Diff highlighting style: 'text' or 'highlighted'
# Default: text
diff_highlight_style = text

# Color for additions (Rich color name or hex)
# Default: sea_green1
diff_addition_color = sea_green1

# Color for deletions (Rich color name or hex)
# Default: orange1
diff_deletion_color = orange1

# Number of context lines shown in diffs
# Default: 6, Range: 0-50
diff_context_lines = 6
```

### Agent-Specific Model Pinning

Pin specific models to specific agents:

```ini
# Pin a model to the python-reviewer agent
agent_model_python-reviewer = gpt-5

# Pin a model to code-puppy
agent_model_code-puppy = claude-4-5-sonnet
```

### Command-line Configuration

Use `/set` command to modify settings interactively:

```bash
# Set YOLO mode
/set yolo_mode true

# Set auto-save
/set auto_save_session true

# Set compaction strategy
/set compaction_strategy summarization

# Set protected token count
/set protected_token_count 60000

# Set diff context lines
/set diff_context_lines 10

# Enable DBOS
/set enable_dbos true
```

---

## Model Configuration

### Built-in Models (models.json)

Code Puppy comes with pre-configured models. View them at `code_puppy/models.json`.

### Custom Models (extra_models.json)

Create `~/.code_puppy/extra_models.json` to add custom models:

#### OpenAI-Compatible Model

```json
{
  "my-custom-model": {
    "type": "custom_openai",
    "name": "gpt-4o",
    "custom_endpoint": {
      "url": "https://my.custom.endpoint:8080",
      "api_key": "$MY_CUSTOM_API_KEY"
    },
    "context_length": 128000,
    "max_requests_per_minute": 100,
    "max_retries": 3,
    "retry_base_delay": 10
  }
}
```

#### Anthropic Claude

```json
{
  "claude-custom": {
    "type": "anthropic",
    "name": "claude-sonnet-4-20250514",
    "context_length": 200000
  }
}
```

#### Cerebras

```json
{
  "cerebras-qwen": {
    "type": "cerebras",
    "name": "qwen-3-coder-480b",
    "custom_endpoint": {
      "url": "https://api.cerebras.ai/v1",
      "api_key": "$CEREBRAS_API_KEY"
    },
    "context_length": 131072
  }
}
```

#### Round-Robin Model Distribution

Distribute load across multiple models/API keys:

```json
{
  "qwen1": {
    "type": "cerebras",
    "name": "qwen-3-coder-480b",
    "custom_endpoint": {
      "url": "https://api.cerebras.ai/v1",
      "api_key": "$CEREBRAS_API_KEY1"
    },
    "context_length": 131072
  },
  "qwen2": {
    "type": "cerebras",
    "name": "qwen-3-coder-480b",
    "custom_endpoint": {
      "url": "https://api.cerebras.ai/v1",
      "api_key": "$CEREBRAS_API_KEY2"
    },
    "context_length": 131072
  },
  "cerebras_round_robin": {
    "type": "round_robin",
    "models": ["qwen1", "qwen2"],
    "rotate_every": 5
  }
}
```

**Usage**: `/model cerebras_round_robin`

#### Model Schema

```json
{
  "model-name": {
    "type": "openai|anthropic|cerebras|zai_coding|zai_api|custom_openai|round_robin",
    "name": "actual-model-name",
    "context_length": 128000,
    "supports_vision": true,
    "supports_vqa": true,
    "custom_endpoint": {
      "url": "https://api.example.com/v1",
      "api_key": "$ENV_VAR_NAME",
      "headers": {
        "X-Custom-Header": "value"
      }
    },
    "max_requests_per_minute": 100,
    "max_retries": 3,
    "retry_base_delay": 10
  }
}
```

### Model Commands

```bash
# List available models
/model

# Switch model
/model gpt-5

# Pin model to specific agent
/pin_model python-reviewer gpt-5

# Set reasoning effort (GPT-5 only)
/reasoning high
```

---

## MCP Server Configuration

MCP (Model Context Protocol) servers provide external tools and capabilities.

### Configuration File

Located at `~/.code_puppy/mcp_servers.json`:

```json
{
  "mcp_servers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
      "env": {},
      "enabled": true
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "$GITHUB_TOKEN"
      },
      "enabled": true
    },
    "brave-search": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-brave-search"],
      "env": {
        "BRAVE_API_KEY": "$BRAVE_API_KEY"
      },
      "enabled": false
    }
  }
}
```

### MCP Commands

```bash
# List all MCP servers
/mcp list

# Start a server
/mcp start filesystem

# Start all enabled servers
/mcp start-all

# Stop a server
/mcp stop filesystem

# Stop all servers
/mcp stop-all

# View server status
/mcp status

# View server logs
/mcp logs filesystem

# Search for MCP servers
/mcp search github

# Install a server from wizard
/mcp install

# Test a server connection
/mcp test filesystem

# Remove a server configuration
/mcp remove filesystem
```

### MCP Server Schema

```json
{
  "server-name": {
    "command": "executable-path",
    "args": ["arg1", "arg2"],
    "env": {
      "ENV_VAR": "$ENV_VAR_FROM_SHELL"
    },
    "enabled": true
  }
}
```

---

## Agent Configuration

### Built-in Agents

Code Puppy includes several built-in agents:

- **code-puppy** 🐶 - General-purpose coding assistant
- **agent-creator** 🏗️ - Creates custom JSON agents
- **python-reviewer** 🐍 - Python code review specialist
- **javascript-reviewer** ⚡ - JavaScript/TypeScript code reviewer
- **golang-reviewer** 🐹 - Go code reviewer
- **cpp-reviewer** ⚙️ - C++ code reviewer
- **security-auditor** 🔒 - Security vulnerability scanner
- **qa-expert** 🧪 - QA and testing specialist

### Custom JSON Agents

Create custom agents in `~/.code_puppy/agents/`:

#### Example: Python Tutor Agent

**File**: `~/.code_puppy/agents/python-tutor-agent.json`

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
  "user_prompt": "What Python concept would you like to learn today?",
  "model": "gpt-5"
}
```

#### JSON Agent Schema

```json
{
  "name": "agent-name",              // REQUIRED: kebab-case identifier
  "display_name": "Agent Name 🤖",   // OPTIONAL: Pretty name with emoji
  "description": "What this agent does", // REQUIRED: Clear description
  "system_prompt": "Instructions..." | ["Line 1", "Line 2"], // REQUIRED
  "tools": ["tool1", "tool2"],       // REQUIRED: Array of tool names
  "user_prompt": "How can I help?",  // OPTIONAL: Custom greeting
  "model": "gpt-5",                  // OPTIONAL: Pin specific model
  "tools_config": {                  // OPTIONAL: Tool configuration
    "timeout": 60
  }
}
```

#### Available Tools

- `list_files` - Directory and file listing
- `read_file` - File content reading
- `grep` - Text search across files
- `edit_file` - File editing and creation
- `delete_file` - File deletion
- `agent_run_shell_command` - Shell command execution
- `agent_share_your_reasoning` - Share reasoning with user

### Agent Commands

```bash
# List available agents
/agent

# Switch to an agent
/agent python-reviewer

# Create a new agent (uses agent-creator)
/agent agent-creator

# Pin a model to an agent
/pin_model python-tutor gpt-5
```

---

## Session Management

### Autosave Configuration

Autosave automatically saves your conversation after each response.

```bash
# Enable/disable autosave
/set auto_save_session true

# Set maximum autosave sessions to keep
/set max_saved_sessions 20

# View current session ID
/session id

# Rotate to new session
/session new

# Load an autosave
/autosave_load
```

### Manual Context Management

```bash
# Save current context
/dump_context my-session-name

# Load a saved context
/load_context my-session-name

# List available contexts
ls ~/.code_puppy/contexts/
```

### Session Files

- **Autosaves**: `~/.code_puppy/autosaves/auto_session_YYYYMMDD_HHMMSS.pkl`
- **Manual Contexts**: `~/.code_puppy/contexts/<name>.pkl`
- **Metadata**: `<session-name>_meta.json` (includes message count, tokens, timestamp)

---

## TUI Theme Configuration

Code Puppy's Terminal User Interface theme is configured in the source code.

### Theme Files

Located in `code_puppy/tui/`:

- `app.py` - Main app layout and colors
- `components/chat_view.py` - Message styling
- `components/input_area.py` - Input area styling
- `components/status_bar.py` - Status bar styling
- `components/sidebar.py` - Sidebar styling
- `THEME.md` - Complete theme documentation

### Core Colors

```python
# Background colors
BACKGROUND = "#0a0e1a"  # Deep navy
SURFACE = "#0f172a"     # Dark slate
PRIMARY = "#1e3a8a"     # Rich blue
ACCENT = "#3b82f6"      # Bright blue
```

### Message Type Colors

- **User**: Deep blue background (`#1e3a5f`), light cyan text
- **Agent**: Dark slate background, light indigo text
- **System**: Dark purple-blue, muted gray-blue text
- **Error**: Deep red background, light pink text
- **Success**: Deep green background, light mint text
- **Warning**: Deep orange-brown, light yellow text
- **Tool Output**: Deep purple, light lavender text

---

## Plugin Configuration

### OAuth Plugins

Code Puppy supports OAuth plugins for ChatGPT and Claude Code.

#### ChatGPT OAuth

**File**: `code_puppy/plugins/chatgpt_oauth/config.py`

Configure in your environment or plugin config:

```bash
export CHATGPT_CLIENT_ID=your-client-id
export CHATGPT_CLIENT_SECRET=your-client-secret
```

#### Claude Code OAuth

**File**: `code_puppy/plugins/claude_code_oauth/config.py`

Configure OAuth credentials similarly.

### File Permission Handler

Automatically handles file permission requests from the agent.

**File**: `code_puppy/plugins/file_permission_handler/`

### Customizable Commands

Create custom slash commands using markdown files.

**File**: `code_puppy/plugins/customizable_commands/`

---

## Custom Commands

Create custom slash commands by placing markdown files in:

- `.claude/commands/`
- `.github/prompts/`
- `.agents/commands/`

### Example Custom Command

**File**: `.claude/commands/review.md`

```markdown
# Security Code Review

Please review this code for:
- Security vulnerabilities
- Authentication issues
- Input validation
- SQL injection risks
- XSS vulnerabilities
```

**Usage**: `/review src/auth.py`

The filename becomes the command name, and the content is sent as a prompt to the agent.

---

## Advanced Configuration

### History Compaction

Manage message history to stay within context limits:

```bash
# Manually compact history
/compact

# Configure compaction strategy
/set compaction_strategy summarization  # or truncation

# Set protected token count (recent messages preserved)
/set protected_token_count 60000

# Set compaction threshold (0.8 = 80% context usage)
/set compaction_threshold 0.85
```

### Truncate History

Keep only N recent messages:

```bash
# Keep only the 20 most recent messages
/truncate 20
```

### Diff Configuration

Customize diff output colors:

```bash
# View current diff configuration
/diff

# Set diff style (text or highlighted)
/diff style highlighted

# Configure addition color
/diff additions sea_green1

# Configure deletion color
/diff deletions orange1

# View color options
/diff additions  # Shows available colors
```

### Show Configuration

View current configuration:

```bash
# Show all settings
/show

# Show available tools
/tools

# Show command help
/help
```

### Directory Navigation

```bash
# Show current directory
/cd

# Change directory
/cd /path/to/directory
```

### Generate PR Descriptions

```bash
# Generate PR description for current branch
/generate-pr-description

# Generate PR description for specific directory
/generate-pr-description @src/features/auth
```

---

## Configuration Best Practices

### 1. API Key Management

- Store API keys in environment variables, not in config files
- Use `.env` file for local development (add to `.gitignore`)
- Rotate API keys regularly

### 2. Model Selection

- Use faster models for simple tasks (e.g., `gpt-4.1-mini`)
- Use powerful models for complex reasoning (e.g., `gpt-5`, `claude-4-5-sonnet`)
- Configure round-robin for high-volume usage

### 3. Session Management

- Enable autosave to prevent data loss
- Set reasonable `max_saved_sessions` limit
- Use manual contexts for important conversations

### 4. Performance Optimization

- Enable HTTP/2 if your provider supports it: `/set http2 true`
- Adjust `protected_token_count` based on your workflow
- Use truncation strategy for faster compaction

### 5. Agent Workflow

- Create specialized JSON agents for repetitive tasks
- Pin appropriate models to each agent
- Use agent-creator to build new agents

### 6. MCP Integration

- Enable only necessary MCP servers
- Monitor MCP logs for errors: `/mcp logs <server>`
- Test MCP servers after configuration: `/mcp test <server>`

---

## Troubleshooting

### Configuration Issues

```bash
# Verify configuration
/show

# Check model availability
/model

# Verify agent configuration
/agent

# Check MCP status
/mcp status
```

### Reset Configuration

To reset Code Puppy configuration:

```bash
# Backup current config
cp ~/.code_puppy/puppy.cfg ~/.code_puppy/puppy.cfg.backup

# Remove config directory (WARNING: loses all settings)
rm -rf ~/.code_puppy

# Restart Code Puppy to recreate defaults
code-puppy -i
```

### Common Issues

1. **Model not found**: Ensure model exists in `models.json` or `extra_models.json`
2. **API key errors**: Verify environment variables are set correctly
3. **MCP server fails**: Check server logs with `/mcp logs <server>`
4. **Autosave not working**: Check `/set auto_save_session true`
5. **Context too long**: Lower `protected_token_count` or use `/compact`

---

## Quick Reference

### Essential Commands

```bash
/help              # Show all commands
/show              # Show configuration
/model <name>      # Switch model
/agent <name>      # Switch agent
/set <key> <value> # Set configuration
/mcp list          # List MCP servers
/compact           # Compact history
/cd <dir>          # Change directory
/exit              # Exit Code Puppy
```

### Configuration Locations

- **Config file**: `~/.code_puppy/puppy.cfg`
- **Models**: `~/.code_puppy/extra_models.json`
- **MCP servers**: `~/.code_puppy/mcp_servers.json`
- **Agents**: `~/.code_puppy/agents/*.json`
- **Contexts**: `~/.code_puppy/contexts/*.pkl`
- **Autosaves**: `~/.code_puppy/autosaves/*.pkl`

---

**Happy Coding with Code Puppy!** 🐶✨
