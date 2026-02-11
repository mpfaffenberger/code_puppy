# Configuration Options Reference

## Overview

This page lists every setting you can configure in Code Puppy. All settings are managed with the `/set` command and stored in your configuration file at `~/.code_puppy/puppy.cfg`.

**Quick syntax:**

```
/set setting_name value
```

**View current settings:**

```
/show
```

**Reset a setting to its default:**

```
/reset setting_name
```

---

## Identity & Personalization

| Setting | Default | Description |
|---------|---------|-------------|
| `puppy_name` | *(set at first launch)* | Your puppy's display name |
| `owner_name` | *(set at first launch)* | Your name (how Code Puppy addresses you) |

**Examples:**

```
/set puppy_name Buddy
/set owner_name Alice
```

---

## Model & Provider

| Setting | Default | Description |
|---------|---------|-------------|
| `model` | *(first model in your catalog)* | The AI model to use for conversations |
| `temperature` | *(model default)* | Creativity level (0.0–2.0). Lower = more precise, higher = more creative |
| `openai_reasoning_effort` | `medium` | Reasoning depth for supported models: `minimal`, `low`, `medium`, `high`, `xhigh` |
| `openai_verbosity` | `medium` | Response length for supported models: `low`, `medium`, `high` |
| `default_agent` | `code-puppy` | Agent to start with when launching a new session |

**Examples:**

```
/set model gpt-5
/set temperature 0.7
/set openai_reasoning_effort high
/set openai_verbosity low
/set default_agent planning-agent
```

> [!TIP]
> You can also use the shorthand `/reasoning high` instead of `/set openai_reasoning_effort high`.

> [!TIP]
> Use `/model` to switch models interactively, or `/add_model` to browse and add models from the catalog.

### Per-Model Settings

You can configure settings for individual models using the `/model_settings` command. These override the global `temperature` setting for that specific model.

Supported per-model settings vary by model and may include:

| Setting | Description |
|---------|-------------|
| `temperature` | Creativity level (0.0–2.0) |
| `seed` | Reproducibility seed (integer) |
| `top_p` | Nucleus sampling parameter |
| `extended_thinking` | Enable extended thinking (Claude models) |
| `budget_tokens` | Token budget for extended thinking (Claude models) |

> [!NOTE]
> Not all models support all settings. Code Puppy automatically filters settings to only those the current model supports.

---

## API Keys

Set API keys to connect to model providers. You can also store keys in a `.env` file in your project directory (`.env` takes priority).

| Setting | Provider |
|---------|----------|
| `OPENAI_API_KEY` | OpenAI (GPT models) |
| `ANTHROPIC_API_KEY` | Anthropic (Claude models) |
| `GEMINI_API_KEY` | Google (Gemini models) |
| `OPENROUTER_API_KEY` | OpenRouter (multi-provider access) |
| `CEREBRAS_API_KEY` | Cerebras |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL |

**Examples:**

```
/set OPENAI_API_KEY sk-...
/set ANTHROPIC_API_KEY sk-ant-...
/set OPENROUTER_API_KEY sk-or-...
```

> [!TIP]
> Create a `.env` file in your project root with `KEY=value` pairs. Keys in `.env` take priority over keys stored in the config file.

---

## Safety & Permissions

| Setting | Default | Description |
|---------|---------|-------------|
| `yolo_mode` | `true` | Skip confirmation prompts before running shell commands |
| `safety_permission_level` | `medium` | Risk threshold for shell commands: `none`, `low`, `medium`, `high`, `critical` |

**Examples:**

```
/set yolo_mode false
/set safety_permission_level high
```

> [!WARNING]
> **YOLO mode is ON by default.** This means Code Puppy runs shell commands without asking first. Set `yolo_mode` to `false` if you want to review every command before it executes.

### Safety Permission Levels

| Level | Behavior |
|-------|----------|
| `none` | No safety checks — all commands run immediately |
| `low` | Only block very dangerous commands |
| `medium` | Balance between convenience and safety (default) |
| `high` | Ask for confirmation on most system-modifying commands |
| `critical` | Ask for confirmation on nearly everything |

---

## Session & History

| Setting | Default | Description |
|---------|---------|-------------|
| `auto_save_session` | `true` | Automatically save your chat history |
| `max_saved_sessions` | `20` | Maximum number of saved sessions to keep (0 = unlimited) |
| `message_limit` | `1000` | Maximum number of agent steps per session |

**Examples:**

```
/set auto_save_session true
/set max_saved_sessions 50
/set message_limit 500
```

> [!NOTE]
> Auto-saved sessions are stored in `~/.code_puppy/autosaves/`. Use `/session list` to view them and `/session load` to restore one.

---

## Context Management

These settings control how Code Puppy handles long conversations that approach the model's context limit.

| Setting | Default | Description |
|---------|---------|-------------|
| `compaction_strategy` | `truncation` | How to reduce context: `summarization` or `truncation` |
| `compaction_threshold` | `0.85` | Context usage percentage that triggers compaction (0.5–0.95) |
| `protected_token_count` | `50000` | Number of recent tokens preserved during compaction (min: 1000, max: 75% of context) |

**Examples:**

```
/set compaction_strategy summarization
/set compaction_threshold 0.9
/set protected_token_count 30000
```

### Compaction Strategies

| Strategy | How It Works |
|----------|-------------|
| `truncation` | Removes the oldest messages to free up space. Fast and simple. |
| `summarization` | Uses the AI to summarize older messages before removing them. Preserves more context but takes a moment. |

> [!TIP]
> If you find Code Puppy "forgetting" earlier parts of your conversation, try increasing `protected_token_count` or switching to `summarization`.

---

## Display & Output

| Setting | Default | Description |
|---------|---------|-------------|
| `diff_context_lines` | `6` | Number of surrounding lines shown in file diffs (0–50) |
| `highlight_addition_color` | `#0b1f0b` | Background color for diff additions (hex or Rich color name) |
| `highlight_deletion_color` | `#390e1a` | Background color for diff deletions (hex or Rich color name) |
| `suppress_thinking_messages` | `false` | Hide agent reasoning/thinking output |
| `suppress_informational_messages` | `false` | Hide info, success, and warning messages |
| `grep_output_verbose` | `false` | Show full grep output with line numbers and content (default shows file names with match counts) |

**Examples:**

```
/set diff_context_lines 10
/set suppress_thinking_messages true
/set grep_output_verbose true
```

### Banner Colors

You can customize the background colors of different output sections. Use Rich color names or hex codes.

| Setting | Default | Used For |
|---------|---------|----------|
| `banner_color_thinking` | `deep_sky_blue4` | "Thinking" banners |
| `banner_color_agent_response` | `medium_purple4` | Main AI responses |
| `banner_color_shell_command` | `dark_orange3` | Shell command output |
| `banner_color_read_file` | `steel_blue` | File reading output |
| `banner_color_edit_file` | `dark_goldenrod` | File edit output |
| `banner_color_grep` | `grey37` | Search results |
| `banner_color_directory_listing` | `dodger_blue2` | Directory listings |
| `banner_color_agent_reasoning` | `dark_violet` | Agent reasoning output |
| `banner_color_invoke_agent` | `deep_pink4` | Agent invocation |
| `banner_color_subagent_response` | `sea_green3` | Sub-agent responses |
| `banner_color_list_agents` | `dark_slate_gray3` | Agent listings |
| `banner_color_universal_constructor` | `dark_cyan` | Tool construction |
| `banner_color_terminal_tool` | `dark_goldenrod` | Browser/terminal tools |

**Examples:**

```
/set banner_color_thinking blue
/set banner_color_agent_response #5f00af
```

> [!TIP]
> Use the `/colors` command to interactively preview and customize banner colors.

---

## Agent Pinning

You can pin specific models to specific agents so each agent always uses its preferred model.

**Set via the `/pin` command:**

```
/pin planning-agent claude-4-5-sonnet
/pin code-puppy gpt-5
```

**Clear a pin:**

```
/unpin planning-agent
```

Pinned models are stored as `agent_model_{agent_name}` in the config file, but you should use the `/pin` and `/unpin` commands to manage them.

---

## Network & Performance

| Setting | Default | Description |
|---------|---------|-------------|
| `enable_streaming` | `true` | Stream model responses in real-time (disable for batch responses) |
| `http2` | `false` | Use HTTP/2 for API requests |

**Examples:**

```
/set enable_streaming true
/set http2 true
```

---

## Advanced Features

| Setting | Default | Description | Restart Required? |
|---------|---------|-------------|-------------------|
| `enable_universal_constructor` | `true` | Allow agents to create custom tools at runtime | No |
| `enable_pack_agents` | `false` | Enable the pack agent system (specialized sub-agents) | No |
| `enable_dbos` | `false` | Enable DBOS durable execution for crash recovery | **Yes** |
| `disable_mcp` | `false` | Skip loading MCP servers entirely | **Yes** |
| `subagent_verbose` | `false` | Show full verbose output from sub-agents (useful for debugging) | No |
| `allow_recursion` | `true` | Allow recursive directory listings | No |
| `cancel_agent_key` | `ctrl+c` | Keyboard shortcut to cancel the current task | **Yes** |

**Examples:**

```
/set enable_universal_constructor false
/set enable_pack_agents true
/set cancel_agent_key ctrl+k
```

### Cancel Key Options

| Value | Key Combination |
|-------|----------------|
| `ctrl+c` | Ctrl + C (default) |
| `ctrl+k` | Ctrl + K |
| `ctrl+q` | Ctrl + Q |

> [!WARNING]
> Changing `cancel_agent_key`, `enable_dbos`, or `disable_mcp` requires restarting Code Puppy to take effect.

---

## Frontend Emitter (Web UI)

These settings control the event emitter used by the web-based terminal interface.

| Setting | Default | Description |
|---------|---------|-------------|
| `frontend_emitter_enabled` | `true` | Enable the frontend event emitter |
| `frontend_emitter_max_recent_events` | `100` | Maximum recent events to buffer |
| `frontend_emitter_queue_size` | `100` | Maximum subscriber queue size |

> [!NOTE]
> These settings are primarily relevant when using Code Puppy's web terminal interface. Most CLI users can leave these at their defaults.

---

## Configuration File

All settings are stored in:

```
~/.code_puppy/puppy.cfg
```

This is a standard INI-format file under the `[puppy]` section. You can edit it directly with a text editor, but using `/set` is recommended.

**Example `puppy.cfg`:**

```ini
[puppy]
puppy_name = Buddy
owner_name = Alice
model = gpt-5
yolo_mode = true
auto_save_session = true
max_saved_sessions = 20
temperature = 0.7
default_agent = code-puppy
```

### XDG Base Directory Support

If you set XDG environment variables, Code Puppy will use standard XDG paths:

| Variable | Default Location | Purpose |
|----------|------------------|---------|
| `XDG_CONFIG_HOME` | `~/.code_puppy/` | Configuration files (`puppy.cfg`, `mcp_servers.json`) |
| `XDG_DATA_HOME` | `~/.code_puppy/` | Data files (models, agents, contexts) |
| `XDG_CACHE_HOME` | `~/.code_puppy/` | Cache files (autosaves) |
| `XDG_STATE_HOME` | `~/.code_puppy/` | State files (command history) |

> [!NOTE]
> XDG paths are only used when the corresponding environment variable is explicitly set. Otherwise, everything stays in `~/.code_puppy/`.

---

## Related Directories

| Directory | Purpose |
|-----------|---------|
| `~/.code_puppy/` | Main configuration and data directory |
| `~/.code_puppy/agents/` | Custom agent definitions |
| `~/.code_puppy/contexts/` | Saved contexts |
| `~/.code_puppy/autosaves/` | Auto-saved session backups |

---

## See Also

- [Initial Configuration](../Getting-Started/Configuration) — First-time setup walkthrough
- [How to Switch Models](../Guides/SwitchModels) — Change models on the fly
- [How to Create Custom Agents](../Guides/CreateCustomAgents) — Build your own agents
- [Slash Commands Reference](Commands) — All available commands
- [Environment Variables](EnvVars) — Environment variable reference
