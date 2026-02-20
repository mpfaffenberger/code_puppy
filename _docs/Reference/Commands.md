# Slash Commands Reference

## Overview

Code Puppy uses slash commands (prefixed with `/`) to control settings, switch models, manage sessions, and more. Type `/help` at any prompt to see a quick summary of all available commands.

> [!TIP]
> Many commands have shorter aliases. For example, `/m` is the same as `/model`, and `/a` is the same as `/agent`.

---

## Core Commands

### `/help`

**Description:** Display a list of all available commands.

**Usage:**
```
/help
/h
```

**Aliases:** `/h`

---

### `/exit`

**Description:** Exit the Code Puppy interactive session.

**Usage:**
```
/exit
/quit
```

**Aliases:** `/quit`

> [!TIP]
> You can also press `Ctrl+D` to exit.

---

### `/cd`

**Description:** Change your working directory or list the contents of the current directory.

**Usage:**
```
/cd              # List current directory contents
/cd <directory>  # Change to the specified directory
```

**Examples:**
```
/cd src            # Change to the src folder
/cd ..             # Go up one level
/cd ~/projects     # Change to an absolute path
/cd "my folder"    # Paths with spaces (use quotes)
```

---

### `/tools`

**Description:** Show the tools and capabilities available to the current agent.

**Usage:**
```
/tools
```

---

### `/motd`

**Description:** Show the latest Message of the Day (MOTD).

**Usage:**
```
/motd
```

---

### `/paste`

**Description:** Paste an image from your system clipboard and attach it to your next message.

**Usage:**
```
/paste
/clipboard
/cb
```

**Aliases:** `/clipboard`, `/cb`

**How it works:**
1. Copy an image to your clipboard (e.g., take a screenshot)
2. Run `/paste`
3. Type your prompt and press Enter — the image is sent along with it

> [!TIP]
> You can paste multiple images before sending. Each `/paste` adds another image to your pending attachments.

---

### `/tutorial`

**Description:** Run the interactive onboarding tutorial. You can run this at any time to walk through setup again.

**Usage:**
```
/tutorial
```

---

## Model Commands

### `/model`

**Description:** Switch the active AI model. Run without arguments to open an interactive model picker.

**Usage:**
```
/model              # Open interactive model picker
/model <model>      # Switch to a specific model
/m <model>          # Shorthand
```

**Aliases:** `/m`

**Examples:**
```
/model                          # Opens the arrow-key model selector
/m claude-sonnet-4-20250514     # Switch directly by name
```

---

### `/add_model`

**Description:** Browse the models.dev catalog and add new model configurations to Code Puppy.

**Usage:**
```
/add_model
```

This opens an interactive TUI where you can search, browse, and add models from a large catalog of available AI providers and models.

---

### `/model_settings`

**Description:** Configure per-model settings like temperature, seed, and other parameters.

**Usage:**
```
/model_settings                  # Open interactive settings TUI
/model_settings --show           # Display current settings for all models
/model_settings --show <model>   # Display settings for a specific model
/ms                              # Shorthand
```

**Aliases:** `/ms`

---

### `/pin_model`

**Description:** Pin a specific model to an agent, so that agent always uses that model regardless of the global model selection.

**Usage:**
```
/pin_model <agent> <model>
```

**Examples:**
```
/pin_model code_puppy claude-sonnet-4-20250514
/pin_model planning gpt-5.3-codex
```

> [!NOTE]
> Run `/pin_model` without arguments to see all available agents and models.

---

### `/unpin`

**Description:** Remove a pinned model from an agent, resetting it to use the global default model.

**Usage:**
```
/unpin <agent>
```

**Examples:**
```
/unpin code_puppy
/unpin planning
```

---

## Agent Commands

### `/agent`

**Description:** Switch to a different agent or view available agents. Run without arguments to open the interactive agent picker.

**Usage:**
```
/agent              # Open interactive agent picker
/agent <name>       # Switch directly to a named agent
/a <name>           # Shorthand
```

**Aliases:** `/a`

**Examples:**
```
/agent              # Opens arrow-key agent selector with descriptions
/a planning         # Switch to the planning agent
/a code_puppy       # Switch back to the default agent
```

> [!NOTE]
> Switching agents automatically rotates your autosave session to preserve history.

---

### `/skills`

**Description:** Browse, enable, or disable agent skills. Skills extend what agents can do by injecting additional instructions.

**Usage:**
```
/skills              # Open interactive skills TUI
/skills list         # List all skills and their status
/skills enable       # Enable skills integration globally
/skills disable      # Disable skills integration globally
```

**Examples:**
```
/skills list         # See which skills are enabled/disabled
/skills enable       # Turn on skills for all agents
```

---

## Session Commands

### `/session`

**Description:** View or manage your autosave session ID.

**Usage:**
```
/session          # Show current session ID
/session id       # Show current session ID
/session new      # Create a new session (rotates the ID)
/s                # Shorthand
```

**Aliases:** `/s`

---

### `/compact`

**Description:** Summarize and compact your current chat history to free up context window space.

**Usage:**
```
/compact
```

Uses the configured compaction strategy (summarization or truncation). See `/set compaction_strategy` to change the strategy.

**Example output:**
```
✨ Done! History: 42 → 8 messages via summarization
🏦 Tokens: 32,450 → 4,200 (87.1% reduction)
```

---

### `/truncate`

**Description:** Truncate your message history to keep only the N most recent messages (plus the system message).

**Usage:**
```
/truncate <N>
```

**Examples:**
```
/truncate 10    # Keep the 10 most recent messages
/truncate 5     # Keep the 5 most recent messages
```

---

### `/dump_context`

**Description:** Save your current message history to a named file for later use.

**Usage:**
```
/dump_context <name>
```

**Examples:**
```
/dump_context my-refactor      # Save as "my-refactor"
/dump_context debug-session    # Save as "debug-session"
```

---

### `/load_context`

**Description:** Load a previously saved message history.

**Usage:**
```
/load_context <name>
```

**Examples:**
```
/load_context my-refactor      # Resume the "my-refactor" session
```

> [!NOTE]
> Loading a context rotates your autosave session ID automatically to prevent overwriting existing saves.

---

### `/autosave_load`

**Description:** Browse and load an autosaved session interactively.

**Usage:**
```
/autosave_load
/resume
```

**Aliases:** `/resume`

---

## Configuration Commands

### `/show`

**Description:** Display all current configuration values including puppy name, active model, YOLO mode, compaction settings, and more.

**Usage:**
```
/show
```

**Example output:**
```
🐶 Puppy Status

puppy_name:            Ralph
owner_name:            User
current_agent:         Code Puppy 🐶
model:                 claude-sonnet-4-20250514
YOLO_MODE:             off
auto_save_session:     enabled
compaction_strategy:   summarization
temperature:           (model default)
```

---

### `/set`

**Description:** Set a configuration value. Changes are saved to your `puppy.cfg` file and take effect immediately.

**Usage:**
```
/set <key> <value>
/set <key>=<value>
```

**Available Configuration Keys:**

| Key | Values | Description |
|-----|--------|-------------|
| `puppy_name` | any string | Your puppy's display name |
| `owner_name` | any string | Your name (used in prompts) |
| `yolo_mode` | `true` / `false` | Skip shell command confirmations |
| `auto_save_session` | `true` / `false` | Auto-save chat after every response |
| `protected_tokens` | integer | Number of recent tokens to preserve during compaction |
| `compaction_threshold` | decimal (0-1) | Context usage percentage that triggers compaction |
| `compaction_strategy` | `summarization` / `truncation` | How to compact history |
| `temperature` | decimal | Model temperature (creativity) |
| `cancel_agent_key` | `ctrl+c` / `ctrl+k` / `ctrl+q` | Key to cancel running tasks |
| `enable_dbos` | `true` / `false` | Enable DBOS integration (requires restart) |

**Examples:**
```
/set yolo_mode true
/set puppy_name Buddy
/set compaction_strategy truncation
/set temperature 0.7
/set cancel_agent_key ctrl+k
```

> [!WARNING]
> Changing `enable_dbos` or `cancel_agent_key` requires restarting Code Puppy to take effect.

---

### `/reasoning`

**Description:** Set the reasoning effort level for models that support it (e.g., GPT-5).

**Usage:**
```
/reasoning <level>
```

**Levels:**

| Level | Description |
|-------|-------------|
| `minimal` | Least thinking, fastest responses |
| `low` | Light reasoning |
| `medium` | Balanced (default) |
| `high` | More thorough reasoning |
| `xhigh` | Maximum reasoning effort |

**Example:**
```
/reasoning high
```

---

### `/verbosity`

**Description:** Set the verbosity level for models that support it.

**Usage:**
```
/verbosity <level>
```

**Levels:**

| Level | Description |
|-------|-------------|
| `low` | Concise responses |
| `medium` | Balanced (default) |
| `high` | Verbose, detailed responses |

**Example:**
```
/verbosity low
```

---

### `/diff`

**Description:** Configure the colors used for diff highlighting (additions and deletions).

**Usage:**
```
/diff
```

Opens an interactive color picker for customizing how code diffs are displayed.

---

### `/colors`

**Description:** Configure banner colors for tool outputs (THINKING, SHELL COMMAND, etc.).

**Usage:**
```
/colors
```

Opens an interactive color picker for customizing the appearance of output banners.

---

## MCP Server Commands

### `/mcp`

**Description:** Manage MCP (Model Context Protocol) servers. Run without a subcommand to list configured servers.

**Usage:**
```
/mcp                        # List all configured servers
/mcp <subcommand> [args]
```

**Subcommands:**

| Subcommand | Usage | Description |
|------------|-------|-------------|
| `list` | `/mcp list` | List all configured MCP servers |
| `start <name>` | `/mcp start filesystem` | Start a specific server |
| `start-all` | `/mcp start-all` | Start all configured servers |
| `stop <name>` | `/mcp stop filesystem` | Stop a specific server |
| `stop-all` | `/mcp stop-all` | Stop all running servers |
| `restart <name>` | `/mcp restart filesystem` | Restart a specific server |
| `status <name>` | `/mcp status filesystem` | Show detailed status of a server |
| `test <name>` | `/mcp test filesystem` | Test connectivity to a server |
| `install` | `/mcp install` | Install a new MCP server |
| `search <query>` | `/mcp search files` | Search the MCP server catalog |
| `edit <name>` | `/mcp edit filesystem` | Edit a server's configuration |
| `remove <name>` | `/mcp remove filesystem` | Remove a server configuration |
| `logs <name>` | `/mcp logs filesystem` | View server logs |
| `help` | `/mcp help` | Show MCP command help |

**Examples:**
```
/mcp list                  # See all servers and their status
/mcp start filesystem      # Start the filesystem server
/mcp status filesystem     # Check if it's running
/mcp search database       # Find database-related MCP servers
/mcp install               # Launch the install wizard
```

---

## Advanced Commands

### `/api`

**Description:** Manage the local Code Puppy API server for GUI integration.

**Usage:**
```
/api              # Show server status
/api start        # Start the API server
/api stop         # Stop the API server
/api status       # Check if the server is running
```

When running, the API server is available at `http://127.0.0.1:8765` with interactive docs at `http://127.0.0.1:8765/docs`.

---

### `/generate-pr-description`

**Description:** Automatically generate a comprehensive PR description based on your current branch's changes.

**Usage:**
```
/generate-pr-description
/generate-pr-description @path/to/dir
```

This command analyzes your git changes and generates a structured PR description with title, summary, changes, technical details, and more. If the GitHub CLI (`gh`) is installed, it can even update the PR directly.

---

### `/wiggum`

**Description:** Activate loop mode — automatically re-run the same prompt each time the agent finishes.

**Usage:**
```
/wiggum <prompt>
```

**Example:**
```
/wiggum run the test suite and fix any failures
```

The agent will keep executing the prompt in a loop until you press `Ctrl+C` or run `/wiggum_stop`.

---

### `/wiggum_stop`

**Description:** Stop wiggum loop mode.

**Usage:**
```
/wiggum_stop
/stopwiggum
/ws
```

**Aliases:** `/stopwiggum`, `/ws`

---

### `/scheduler`

**Description:** Manage scheduled tasks — create, run, and monitor automated prompts that run on a schedule.

**Usage:**
```
/scheduler                  # Open interactive scheduler TUI
/scheduler start            # Start the scheduler daemon
/scheduler stop             # Stop the scheduler daemon
/scheduler status           # Show daemon status and task summary
/scheduler list             # List all scheduled tasks
/scheduler run <id>         # Run a specific task immediately
```

**Aliases:** `/sched`, `/cron`

---

### `/uc`

**Description:** Open the Universal Constructor — browse and manage custom tools that extend Code Puppy's capabilities.

**Usage:**
```
/uc
```

Opens an interactive TUI for browsing, installing, and managing custom tools.

---

## Quick Reference Table

| Command | Alias(es) | Description |
|---------|-----------|-------------|
| `/help` | `/h` | Show all commands |
| `/exit` | `/quit` | Exit Code Puppy |
| `/cd <dir>` | — | Change directory |
| `/model <name>` | `/m` | Switch AI model |
| `/add_model` | — | Browse model catalog |
| `/model_settings` | `/ms` | Per-model settings |
| `/agent <name>` | `/a` | Switch agent |
| `/show` | — | Show current config |
| `/set <key> <val>` | — | Change a setting |
| `/session [id\|new]` | `/s` | Manage session ID |
| `/compact` | — | Compact chat history |
| `/truncate <N>` | — | Keep N recent messages |
| `/dump_context <n>` | — | Save history to file |
| `/load_context <n>` | — | Load saved history |
| `/autosave_load` | `/resume` | Load autosaved session |
| `/paste` | `/clipboard`, `/cb` | Paste clipboard image |
| `/tools` | — | Show available tools |
| `/mcp` | — | Manage MCP servers |
| `/skills` | — | Manage agent skills |
| `/pin_model` | — | Pin model to agent |
| `/unpin` | — | Unpin model from agent |
| `/reasoning <lvl>` | — | Set reasoning effort |
| `/verbosity <lvl>` | — | Set verbosity level |
| `/diff` | — | Configure diff colors |
| `/colors` | — | Configure banner colors |
| `/api` | — | Manage API server |
| `/generate-pr-description` | — | Generate PR description |
| `/wiggum <prompt>` | — | Loop mode |
| `/wiggum_stop` | `/stopwiggum`, `/ws` | Stop loop mode |
| `/scheduler` | `/sched`, `/cron` | Scheduled tasks |
| `/uc` | — | Universal Constructor |
| `/tutorial` | — | Run onboarding tutorial |
| `/motd` | — | Show message of the day |

---

## See Also

- [Guide: How to Switch Models](../Guides/SwitchModels)
- [Guide: How to Switch and Use Agents](../Guides/UseAgents)
- [Guide: How to Manage Sessions](../Guides/ManageSessions)
- [Guide: How to Use MCP Servers](../Guides/MCPServers)
- [Reference: Configuration Options](ConfigReference)
- [Reference: Environment Variables](EnvVars)
