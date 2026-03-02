# Initial Configuration

## Overview

When you first launch Code Puppy, it walks you through a quick setup: naming your puppy and identifying yourself. After that, the main thing you need to configure is **how to connect to an AI model**. This page covers everything you need to get fully configured.

## First Launch Setup

The very first time you run Code Puppy, you'll be prompted with two questions:

```
🐾 Let's get your Puppy ready!
What should we name the puppy? Buddy
What's your name (so Code Puppy knows its owner)? Alice
```

These are stored in your configuration file and can be changed later.

## The Onboarding Tutorial

After the initial prompts, Code Puppy launches a **5-slide interactive tutorial** that guides you through:

1. **Welcome** — A quick overview of what's ahead
2. **Model selection** — Choose how you want to access AI models
3. **MCP servers** — Optional integrations (you can skip this)
4. **Agents** — Learn when to use Code Puppy vs. the Planning Agent
5. **Ready!** — Essential commands to get started

**Navigation:**

| Key | Action |
|-----|--------|
| `→` or `l` | Next slide |
| `←` or `h` | Previous slide |
| `↑↓` or `j/k` | Move between options |
| `Enter` | Select option / advance |
| `ESC` | Skip the tutorial |

> [!TIP]
> You can re-run the tutorial anytime by typing `/tutorial` in the chat.

## Setting Up Your Model Provider

Code Puppy needs access to an AI model to work. You have several options:

### Option 1: ChatGPT (OAuth — No API Key Needed)

If you have a ChatGPT Plus, Pro, or Max subscription, you can log in directly:

1. Select **ChatGPT Plus/Pro/Max** during the onboarding tutorial, or
2. After setup, the OAuth login flow will start automatically

This gives you access to models like GPT-5.2 using your existing subscription.

### Option 2: Claude Code (OAuth — No API Key Needed)

If you have a Claude Code Pro or Max subscription:

1. Select **Claude Code Pro/Max** during onboarding, or
2. The OAuth login flow will guide you through authentication

### Option 3: API Keys

If you have API keys from providers like OpenAI, Anthropic, or Google, set them with the `/set` command:

```
/set OPENAI_API_KEY=sk-...
/set ANTHROPIC_API_KEY=sk-ant-...
/set GEMINI_API_KEY=...
```

Then browse and add models from the catalog:

```
/add_model
```

### Option 4: OpenRouter

OpenRouter gives you a single API key for 100+ models from various providers:

```
/set OPENROUTER_API_KEY=sk-or-...
```

> [!TIP]
> You can also store API keys in a `.env` file in your project directory. Keys in `.env` take priority over keys stored in the configuration file.

### Supported API Keys

| Key | Provider |
|-----|----------|
| `OPENAI_API_KEY` | OpenAI (GPT models) |
| `ANTHROPIC_API_KEY` | Anthropic (Claude models) |
| `GEMINI_API_KEY` | Google (Gemini models) |
| `OPENROUTER_API_KEY` | OpenRouter (multi-provider) |
| `CEREBRAS_API_KEY` | Cerebras |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL |

## Essential Settings

Use `/set` to configure Code Puppy's behavior. Here are the most important settings:

### Viewing Your Current Config

```
/show
```

This displays all your current settings including puppy name, model, agent, YOLO mode, and more.

### Key Settings

| Setting | Default | Description | Example |
|---------|---------|-------------|---------|
| `puppy_name` | *(set at first launch)* | Your puppy's name | `/set puppy_name Buddy` |
| `owner_name` | *(set at first launch)* | Your name | `/set owner_name Alice` |
| `yolo_mode` | `true` | Skip confirmation prompts for shell commands | `/set yolo_mode false` |
| `default_agent` | `code-puppy` | Agent to use when starting a new session | `/set default_agent planning-agent` |
| `auto_save_session` | `true` | Automatically save your chat history | `/set auto_save_session false` |
| `max_saved_sessions` | `20` | Maximum number of saved sessions to keep | `/set max_saved_sessions 50` |
| `temperature` | *(model default)* | Model creativity (0.0–2.0, lower = more precise) | `/set temperature 0.7` |

> [!WARNING]
> **YOLO mode** is enabled by default! This means Code Puppy will run shell commands without asking for confirmation. If you prefer to review commands before they run, set it to `false`:
> ```
> /set yolo_mode false
> ```

### Model Tuning Settings

| Setting | Default | Description | Example |
|---------|---------|-------------|---------|
| `openai_reasoning_effort` | `medium` | Reasoning depth for GPT models (`minimal`, `low`, `medium`, `high`, `xhigh`) | `/reasoning high` |
| `openai_verbosity` | `medium` | Response length (`low`, `medium`, `high`) | `/set openai_verbosity low` |

> [!TIP]
> For the reasoning effort, you can use the shorthand `/reasoning high` instead of `/set openai_reasoning_effort high`.

### Advanced Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `compaction_strategy` | `truncation` | How to manage long conversations (`summarization` or `truncation`) |
| `compaction_threshold` | `0.85` | Context usage percentage that triggers compaction (0.5–0.95) |
| `protected_token_count` | `50000` | Recent tokens preserved during compaction |
| `allow_recursion` | `true` | Allow recursive directory listings |
| `enable_streaming` | `true` | Stream model responses in real-time |
| `http2` | `false` | Use HTTP/2 for API requests |
| `cancel_agent_key` | `ctrl+c` | Keyboard shortcut to cancel the current task (`ctrl+c`, `ctrl+k`, or `ctrl+q`) |
| `enable_universal_constructor` | `true` | Allow agents to create custom tools at runtime |
| `enable_pack_agents` | `false` | Enable advanced pack agent system |
| `enable_dbos` | `false` | Enable DBOS durable execution (requires restart) |

## Configuration File Location

All settings are stored in a configuration file at:

```
~/.code_puppy/puppy.cfg
```

Code Puppy also uses these directories:

| Directory | Purpose |
|-----------|---------|
| `~/.code_puppy/` | Configuration, data, cache, and state |
| `~/.code_puppy/agents/` | Custom agent definitions |
| `~/.code_puppy/contexts/` | Saved contexts |
| `~/.code_puppy/autosaves/` | Auto-saved session backups |

> [!NOTE]
> If you have XDG Base Directory environment variables set (like `XDG_CONFIG_HOME`), Code Puppy will respect them and use standard XDG paths instead.

## Verify Your Configuration

Run `/show` to verify everything is set up correctly:

```
/show
```

You should see output like:

```
🐶 Puppy Status

puppy_name:            Buddy
owner_name:            Alice
current_agent:         Code Puppy
default_agent:         code-puppy
model:                 gpt-5
YOLO_MODE:             ON
auto_save_session:     enabled
...
```

## Common Issues

| Problem | Solution |
|---------|----------|
| "No model configured" | Set up an API key or complete OAuth login — see [Setting Up Your Model Provider](#setting-up-your-model-provider) |
| Model not responding | Verify your API key is correct with `/show` and check your provider's status page |
| Want to change puppy name | `/set puppy_name NewName` |
| Want to re-run setup tutorial | Type `/tutorial` |
| Settings not taking effect | Some settings (like `enable_dbos` and `cancel_agent_key`) require restarting Code Puppy |

## Next Steps

- [Quick Start Tutorial](QuickStart) — Start your first coding task
- [How to Switch Models](../Guides/SwitchModels) — Change models on the fly
- [How to Switch and Use Agents](../Guides/UseAgents) — Use different agents for different tasks
- [Configuration Reference](../Reference/ConfigReference) — Full list of all settings
