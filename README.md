<div align="center">

![Code Puppy Logo](code_puppy.png)

**🐶✨The sassy AI code agent that makes IDEs look outdated** ✨🐶

[![Version](https://img.shields.io/pypi/v/code-puppy?style=for-the-badge&logo=python&label=Version&color=purple)](https://pypi.org/project/code-puppy/)
[![Downloads](https://img.shields.io/badge/Downloads-100k%2B-brightgreen?style=for-the-badge&logo=download)](https://pypi.org/project/code-puppy/)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)
[![Build Status](https://img.shields.io/badge/Build-Passing-brightgreen?style=for-the-badge&logo=github)](https://github.com/mpfaffenberger/code_puppy/actions)
[![Coverage](https://img.shields.io/badge/Coverage-95%25-brightgreen?style=for-the-badge)](https://github.com/mpfaffenberger/code_puppy)
[![Code Style](https://img.shields.io/badge/Code%20Style-Black-black?style=for-the-badge)](https://github.com/psf/black)
[![Tests](https://img.shields.io/badge/Tests-Passing-success?style=for-the-badge&logo=pytest)](https://github.com/mpfaffenberger/code_puppy/tests)

[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--5-orange?style=flat-square&logo=openai)](https://openai.com)
[![Gemini](https://img.shields.io/badge/Google-Gemini-blue?style=flat-square&logo=google)](https://ai.google.dev/)
[![Anthropic](https://img.shields.io/badge/Anthropic-Claude-orange?style=flat-square&logo=anthropic)](https://anthropic.com)
[![Cerebras](https://img.shields.io/badge/Cerebras-GLM%204.6-red?style=flat-square)](https://cerebras.ai)
[![Z.AI](https://img.shields.io/badge/Z.AI-GLM%204.6-purple?style=flat-square)](https://z.ai/)
[![Synthetic](https://img.shields.io/badge/Synthetic-MINIMAX_M2-green?style=flat-square)](https://synthetic.new)

[![100% Open Source](https://img.shields.io/badge/100%25-Open%20Source-blue?style=for-the-badge)](https://github.com/mpfaffenberger/code_puppy)
[![Pydantic AI](https://img.shields.io/badge/Pydantic-AI-success?style=for-the-badge)](https://github.com/pydantic/pydantic-ai)

[![100% privacy](https://img.shields.io/badge/FULL-Privacy%20commitment-blue?style=for-the-badge)](https://github.com/mpfaffenberger/code_puppy/blob/main/README.md#code-puppy-privacy-commitment)

[![GitHub stars](https://img.shields.io/github/stars/mpfaffenberger/code_puppy?style=for-the-badge&logo=github)](https://github.com/mpfaffenberger/code_puppy/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/mpfaffenberger/code_puppy?style=for-the-badge&logo=github)](https://github.com/mpfaffenberger/code_puppy/network)

**[⭐ Star this repo if you hate expensive IDEs! ⭐](#quick-start)**

*"Who needs an IDE when you have 1024 angry puppies?"* - Someone, probably.

</div>

---



## Overview

*This project was coded angrily in reaction to Windsurf and Cursor removing access to models and raising prices.*

*You could also run 50 code puppies at once if you were insane enough.*

*Would you rather plow a field with one ox or 1024 puppies?*
    - If you pick the ox, better slam that back button in your browser.


Code Puppy is an AI-powered code generation agent, designed to understand programming tasks, generate high-quality code, and explain its reasoning similar to tools like Windsurf and Cursor.


## Quick start

```bash
uvx code-puppy -i
````

## Installation

### UV (Recommended)

```bash
# Install UV if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Set UV to always use managed Python (one-time setup)
echo 'export UV_MANAGED_PYTHON=1' >> ~/.zshrc  # or ~/.bashrc
source ~/.zshrc  # or ~/.bashrc

# Install and run code-puppy
uvx code-puppy -i
```

UV will automatically download the latest compatible Python version (3.11+) if your system doesn't have one.

### pip (Alternative)

```bash
pip install code-puppy
```

*Note: pip installation requires your system Python to be 3.11 or newer.*

### Permanent Python Management

To make UV always use managed Python versions (recommended):

```bash
# Set environment variable permanently
echo 'export UV_MANAGED_PYTHON=1' >> ~/.zshrc  # or ~/.bashrc
source ~/.zshrc  # or ~/.bashrc

# Now all UV commands will prefer managed Python installations
uvx code-puppy  # No need for --managed-python flag anymore
```

### Verifying Python Version

```bash
# Check which Python UV will use
uv python find

# Or check the current project's Python
uv run python --version
```

## Usage

### Custom Commands
Create markdown files in `.claude/commands/`, `.github/prompts/`, or `.agents/commands/` to define custom slash commands. The filename becomes the command name and the content runs as a prompt.

```bash
# Create a custom command
echo "# Code Review

Please review this code for security issues." > .claude/commands/review.md

# Use it in Code Puppy
/review with focus on authentication
```

### Adding Models from models.dev 🆕

While there are several models configured right out of the box from providers like Synthetic, Cerebras, OpenAI, Google, and Anthropic, Code Puppy integrates with [models.dev](https://models.dev) to let you browse and add models from **65+ providers** with a single command:

```bash
/add_model
```

This opens an interactive TUI where you can:
- **Browse providers** - See all available AI providers (OpenAI, Anthropic, Groq, Mistral, xAI, Cohere, Perplexity, DeepInfra, and many more)
- **Preview model details** - View capabilities, pricing, context length, and features
- **One-click add** - Automatically configures the model with correct endpoints and API keys

#### Live API with Offline Fallback

The `/add_model` command fetches the latest model data from models.dev in real-time. If the API is unavailable, it falls back to a bundled database:

```
📡 Fetched latest models from models.dev     # Live API
📦 Using bundled models database              # Offline fallback
```

#### Supported Providers

Code Puppy integrates with https://models.dev giving you access to 65 providers and >1000 different model offerings.

There are **39+ additional providers** that already have OpenAI-compatible APIs configured in models.dev!

These providers are automatically configured with correct OpenAI-compatible endpoints, but have **not** been tested thoroughly:

| Provider | Endpoint | API Key Env Var |
|----------|----------|----------------|
| **xAI** (Grok) | `https://api.x.ai/v1` | `XAI_API_KEY` |
| **Groq** | `https://api.groq.com/openai/v1` | `GROQ_API_KEY` |
| **Mistral** | `https://api.mistral.ai/v1` | `MISTRAL_API_KEY` |
| **Together AI** | `https://api.together.xyz/v1` | `TOGETHER_API_KEY` |
| **Perplexity** | `https://api.perplexity.ai` | `PERPLEXITY_API_KEY` |
| **DeepInfra** | `https://api.deepinfra.com/v1/openai` | `DEEPINFRA_API_KEY` |
| **Cohere** | `https://api.cohere.com/compatibility/v1` | `COHERE_API_KEY` |
| **AIHubMix** | `https://aihubmix.com/v1` | `AIHUBMIX_API_KEY` |

#### Smart Warnings

- **⚠️ Unsupported Providers** - Providers like Amazon Bedrock and Google Vertex that require special authentication are clearly marked
- **⚠️ No Tool Calling** - Models without tool calling support show a big warning since they can't use Code Puppy's file/shell tools

### Durable Execution

Code Puppy now supports **[DBOS](https://github.com/dbos-inc/dbos-transact-py)** durable execution.

When enabled, every agent is automatically wrapped as a `DBOSAgent`, checkpointing key interactions (including agent inputs, LLM responses, MCP calls, and tool calls) in a database for durability and recovery.

You can toggle DBOS via either of these options:

- CLI config (persists): `/set enable_dbos true` (or `false` to disable)


Config takes precedence if set; otherwise the environment variable is used.

### Configuration

The following environment variables control DBOS behavior:
- `DBOS_CONDUCTOR_KEY`: If set, Code Puppy connects to the [DBOS Management Console](https://console.dbos.dev/). Make sure you first register an app named `dbos-code-puppy` on the console to generate a Conductor key. Default: `None`.
- `DBOS_LOG_LEVEL`: Logging verbosity: `CRITICAL`, `ERROR`, `WARNING`, `INFO`, or `DEBUG`. Default: `ERROR`.
- `DBOS_SYSTEM_DATABASE_URL`: Database URL used by DBOS. Can point to a local SQLite file or a Postgres instance. Example: `postgresql://postgres:dbos@localhost:5432/postgres`. Default: `dbos_store.sqlite` file in the config directory.
- `DBOS_APP_VERSION`: If set, Code Puppy uses it as the [DBOS application version](https://docs.dbos.dev/architecture#application-and-workflow-versions) and automatically tries to recover pending workflows for this version. Default: Code Puppy version + Unix timestamp in millisecond (disable automatic recovery).


## Requirements

- Python 3.11+
- OpenAI API key (for GPT models)
- Gemini API key (for Google's Gemini models)
- Cerebras API key (for Cerebras models)
- Anthropic key (for Claude models)
- Ollama endpoint available

## Agent Rules
We support AGENT.md files for defining coding standards and styles that your code should comply with. These rules can cover various aspects such as formatting, naming conventions, and even design guidelines.

For examples and more information about agent rules, visit [https://agent.md](https://agent.md)

## Using MCP Servers for External Tools

Use the `/mcp` command to manage MCP (list, start, stop, status, etc.)

Watch this video for examples! https://www.youtube.com/watch?v=1t1zEetOqlo


## Round Robin Model Distribution

Code Puppy supports **Round Robin model distribution** to help you overcome rate limits and distribute load across multiple AI models. This feature automatically cycles through configured models with each request, maximizing your API usage while staying within rate limits.

### Configuration
Add a round-robin model configuration to your `~/.code_puppy/extra_models.json` file:

```bash
export CEREBRAS_API_KEY1=csk-...
export CEREBRAS_API_KEY2=csk-...
export CEREBRAS_API_KEY3=csk-...

```

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
  "qwen3": {
    "type": "cerebras",
    "name": "qwen-3-coder-480b",
    "custom_endpoint": {
      "url": "https://api.cerebras.ai/v1",
      "api_key": "$CEREBRAS_API_KEY3"
    },
    "context_length": 131072
  },
  "cerebras_round_robin": {
    "type": "round_robin",
    "models": ["qwen1", "qwen2", "qwen3"],
    "rotate_every": 5
  }
}
```

Then just use /model and tab to select your round-robin model!

The `rotate_every` parameter controls how many requests are made to each model before rotating to the next one. In this example, the round-robin model will use each Qwen model for 5 consecutive requests before moving to the next model in the sequence.

---

## Theme System 🎨

Code Puppy features a powerful theming system that lets you customize the appearance of all message colors in the terminal interface. Themes control the colors of user messages, agent responses, system messages, warnings, errors, info messages, and more.

### Theme System Overview

**What are themes?**

Themes are color palettes that define how different types of messages are displayed in your Code Puppy terminal. Each theme consists of a collection of color settings that control:

- **User messages** - The color of your input text
- **Agent responses** - The color of the agent's output
- **System messages** - Notifications and system information
- **Warnings** - Cautionary messages
- **Errors** - Error messages
- **Info messages** - Informational messages
- **Success messages** - Success confirmations
- **Tool outputs** - Shell command and tool execution results
- **Reasoning** - Agent's thought process explanations
- **Code blocks** - Code snippet backgrounds

**What themes DON'T control:**

- **Syntax highlighting** - Code syntax colors (handled by Pygments)
- **Diffs** - Git diff colors (red/green additions/removals)
- **UI elements** - Menu borders, buttons, and other UI components

**How themes work:**

Themes are stored as JSON files in your `~/.code_puppy/themes/` directory. Each theme file contains color definitions using ANSI color codes (0-255 for 256-color support). The theme system uses terminal color capabilities to render beautiful, consistent output across different terminal emulators.

### Using the Theme Menu

The theme menu provides an interactive interface for browsing, selecting, and creating themes.

**Opening the Theme Menu:**

```bash
/theme
```

This opens an interactive terminal UI (TUI) with the following options:

```
┌─────────────────────────────────────────┐
│         🎨 Code Puppy Themes           │
├─────────────────────────────────────────┤
│  • Browse Preset Themes                │
│  • Create Custom Theme                 │
│  • Manage Custom Themes                │
│  • Export/Import Themes                │
│  • View Current Theme                  │
└─────────────────────────────────────────┘
```

**Navigating the Menu:**

- **Arrow keys** (↑/↓) - Navigate between options
- **Enter** - Select an option or theme
- **Esc** - Go back or exit
- **Tab** - Move between color selection fields

**Selecting and Applying a Theme:**

1. Open the theme menu with `/theme`
2. Select "Browse Preset Themes"
3. Use arrow keys to highlight a theme
4. Press Enter to preview the theme
5. Press Enter again to apply it to your current session

**Keyboard Shortcuts:**

- `q` - Quit/exit the menu
- `r` - Reset to default theme
- `s` - Save current theme selection
- `?` - Show help

### Available Preset Themes

Code Puppy includes 10 beautiful preset themes, each with a unique aesthetic:

| Theme | Description | Aesthetic |
|-------|-------------|-----------|
| **Default** 🐶 | Classic Code Puppy look | Balanced colors, high contrast, puppy-friendly |
| **Ocean** 🌊 | Calming blue tones | Deep blues and teals, easy on the eyes |
| **Forest** 🌲 | Nature-inspired greens | Rich greens and earth tones, organic feel |
| **Sunset** 🌅 | Warm sunset gradients | Oranges, pinks, and purples, vibrant |
| **Midnight** 🌙 | Dark mode optimized | Deep purples and dark blues, low-light friendly |
| **Cyberpunk** 🤖 | Neon futuristic style | Bright neons on dark backgrounds, sci-fi |
| **Retro** 📟 | Vintage terminal look | Amber/green on black, nostalgic |
| **Pastel** 🎀 | Soft pastel colors | Gentle pinks, blues, lavenders, calming |
| **Hacker** 💻 | Matrix-inspired green | Bright green on black, classic hacker |
| **Minimal** ⬜ | Clean monochrome | Grayscale only, distraction-free |

**Previewing Themes:**

When you select a theme from the menu, you'll see a live preview showing how different message types will appear:

```
[USER] This is how your messages look
[AGENT] This is how agent responses appear
[SYSTEM] System notifications use this color
[WARNING] ⚠️  Warnings use caution colors
[ERROR] ❌ Errors stand out clearly
[INFO] ℹ️  Info messages are subtle
[SUCCESS] ✓ Success messages are positive
```

### Creating Custom Themes

You can create your own themes with custom color combinations using the built-in theme builder.

**Using the Custom Theme Builder:**

1. Open the theme menu with `/theme`
2. Select "Create Custom Theme"
3. Enter a name for your theme (e.g., "my-awesome-theme")
4. For each color category, use the color picker:
   - **Arrow keys** to navigate the color palette
   - **Enter** to select a color
   - **Tab** to move to the next color category
5. Add optional metadata:
   - **Author**: Your name or handle
   - **Version**: Theme version (e.g., "1.0.0")
   - **Tags**: Comma-separated tags (e.g., "dark,blue,calm")
   - **Description**: Brief description of your theme
6. Press `s` to save your theme

**Color Selection Interface:**

The color picker displays a 16x16 grid of available colors (256-color palette):

```
┌─────────────────────────────────────┐
│  Select User Message Color          │
├─────────────────────────────────────┤
│  ████  ████  ████  ████  ████ ...  │
│  ████  ████  ████  ████  ████ ...  │
│  ████  ████  ████  ████  ████ ...  │
│  ████  ████  ████  ████  ████ ...  │
│                                     │
│  Selected: #FF6B6B (Red)           │
│  Press Enter to confirm             │
└─────────────────────────────────────┘
```

**Example Custom Theme JSON:**

```json
{
  "name": "my-awesome-theme",
  "author": "Your Name",
  "version": "1.0.0",
  "tags": ["dark", "blue", "calm"],
  "description": "A calming dark theme with blue accents",
  "colors": {
    "user_message": 39,      // Dodger Blue
    "agent_response": 45,    // Turquoise
    "system_message": 240,   // Dark Gray
    "warning": 208,          // Orange
    "error": 196,            // Red
    "info": 244,             // Light Gray
    "success": 46,           // Green
    "tool_output": 243,      // Gray
    "reasoning": 241,        // Light Gray
    "code_block": 236        // Dark Background
  }
}
```

**Color Numbers:**

Color numbers are ANSI 256-color codes:
- **0-15**: Standard 16 colors (black, red, green, yellow, blue, magenta, cyan, white, and bright variants)
- **16-231**: 216 colors (6x6x6 RGB cube)
- **232-255**: 24 grayscale colors

### Theme Configuration

Themes are stored in your Code Puppy configuration file and persist across sessions.

**Theme Storage in puppy.cfg:**

```ini
[theme]
name = ocean
author = Code Puppy Team
version = 1.0.0
```

**Setting Theme via Config:**

You can set your theme directly in the configuration file:

```bash
# Edit your config file
nano ~/.code_puppy/puppy.cfg

# Add or modify the theme section
[theme]
name = cyberpunk
```

Or use the `/set` command:

```bash
/set theme ocean
```

**Theme Persistence:**

- Your selected theme is automatically saved to `puppy.cfg`
- The theme is loaded automatically when you start Code Puppy
- Changes to the theme take effect immediately
- Custom themes are saved to `~/.code_puppy/themes/` as JSON files

**Theme File Locations:**

- **Preset themes**: `code_puppy/themes/` (built-in, read-only)
- **Custom themes**: `~/.code_puppy/themes/` (user-created, editable)
- **Current theme**: `~/.code_puppy/puppy.cfg` (configuration)

### Advanced Features

**Exporting Themes:**

Share your custom themes with others by exporting them:

1. Open the theme menu with `/theme`
2. Select "Export/Import Themes"
3. Choose "Export Theme"
4. Select the theme to export
5. Choose export location (default: `~/.code_puppy/themes/exports/`)
6. The theme is saved as a `.json` file

```bash
# Exported theme file example
~/.code_puppy/themes/exports/my-awesome-theme.json
```

**Importing Themes:**

Import themes shared by others:

1. Open the theme menu with `/theme`
2. Select "Export/Import Themes"
3. Choose "Import Theme"
4. Navigate to the theme JSON file
5. Press Enter to import
6. The theme is added to your custom themes

```bash
# Import a theme file
/theme
# → Export/Import Themes
# → Import Theme
# → Select: /path/to/shared-theme.json
```

**Deleting Custom Themes:**

Remove themes you no longer need:

1. Open the theme menu with `/theme`
2. Select "Manage Custom Themes"
3. Highlight the theme to delete
4. Press `d` to delete
5. Confirm with `y`

```bash
# Or delete manually
rm ~/.code_puppy/themes/your-theme.json
```

**Theme Metadata:**

Each theme can include metadata to help organize and describe it:

```json
{
  "name": "theme-name",
  "author": "Author Name",
  "version": "1.0.0",
  "tags": ["dark", "blue", "calm"],
  "description": "A brief description of the theme",
  "created_at": "2025-01-15T10:30:00Z",
  "updated_at": "2025-01-20T14:22:00Z"
}
```

**Metadata Fields:**

- **name** (required): Unique theme identifier (kebab-case)
- **author** (optional): Theme creator's name
- **version** (optional): Semantic version (e.g., "1.0.0")
- **tags** (optional): Array of descriptive tags for filtering
- **description** (optional): Brief description of the theme's aesthetic
- **created_at** (auto): ISO 8601 timestamp of creation
- **updated_at** (auto): ISO 8601 timestamp of last update

**Viewing Current Theme:**

Check which theme is currently active:

```bash
/theme
# → View Current Theme
```

This displays:
- Theme name and version
- Author information
- Color palette preview
- All color definitions

**Resetting to Default:**

Reset to the default theme:

```bash
/theme
# Press `r` to reset
```

Or via config:

```bash
/set theme default
```

**Theme Best Practices:**

1. **Contrast**: Ensure good contrast between text and background
2. **Accessibility**: Consider colorblind users (avoid relying on color alone)
3. **Consistency**: Use a coherent color scheme throughout
4. **Testing**: Test your theme in different terminal emulators
5. **Documentation**: Include clear descriptions and tags for sharing

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

### Truncate Message History
```bash
/truncate <N>
```
Truncates the message history to keep only the N most recent messages while protecting the first (system) message. For example:
```bash
/truncate 20
```
Would keep the system message plus the 19 most recent messages, removing older ones from the history.

This is useful for managing context length when you have a long conversation history but only need the most recent interactions.

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

# Code Puppy Privacy Commitment

**Zero-compromise privacy policy. Always.**

Unlike other Agentic Coding software, there is no corporate or investor backing for this project, which means **zero pressure to compromise our principles for profit**. This isn't just a nice-to-have feature – it's fundamental to the project's DNA.

### What Code Puppy _absolutely does not_ collect:
- ❌ **Zero telemetry** – no usage analytics, crash reports, or behavioral tracking
- ❌ **Zero prompt logging** – your code, conversations, or project details are never stored
- ❌ **Zero behavioral profiling** – we don't track what you build, how you code, or when you use the tool
- ❌ **Zero third-party data sharing** – your information is never sold, traded, or given away

### What data flows where:
- **LLM Provider Communication**: Your prompts are sent directly to whichever LLM provider you've configured (OpenAI, Anthropic, local models, etc.) – this is unavoidable for AI functionality
- **Complete Local Option**: Run your own VLLM/SGLang/Llama.cpp server locally → **zero data leaves your network**. Configure this with `~/.code_puppy/extra_models.json`
- **Direct Developer Contact**: All feature requests, bug reports, and discussions happen directly with me – no middleman analytics platforms or customer data harvesting tools

### Our privacy-first architecture:
Code Puppy is designed with privacy-by-design principles. Every feature has been evaluated through a privacy lens, and every integration respects user data sovereignty. When you use Code Puppy, you're not the product – you're just a developer getting things done.

**This commitment is enforceable because it's structurally impossible to violate it.** No external pressures, no investor demands, no quarterly earnings targets to hit. Just solid code that respects your privacy.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
