# Environment Variables

## Overview

Code Puppy uses environment variables for API keys, network configuration, directory customization, and behavior control. This reference lists all recognized environment variables.

> [!TIP]
> You can set API keys either as environment variables, in a `.env` file in your project directory, or through the `puppy.cfg` configuration file. Code Puppy checks all three locations automatically.

---

## API Keys

These environment variables provide authentication credentials for AI model providers. You need at least one to use Code Puppy.

| Variable | Description | Required |
|----------|-------------|----------|
| `OPENAI_API_KEY` | API key for OpenAI models (GPT-4, GPT-4o, etc.) | At least one API key is required |
| `ANTHROPIC_API_KEY` | API key for Anthropic models (Claude) | At least one API key is required |
| `GEMINI_API_KEY` | API key for Google Gemini models | At least one API key is required |
| `CEREBRAS_API_KEY` | API key for Cerebras models | At least one API key is required |
| `OPENROUTER_API_KEY` | API key for OpenRouter (access multiple providers) | At least one API key is required |
| `AZURE_OPENAI_API_KEY` | API key for Azure-hosted OpenAI models | At least one API key is required |
| `AZURE_OPENAI_ENDPOINT` | Endpoint URL for your Azure OpenAI deployment | Required with `AZURE_OPENAI_API_KEY` |
| `SYN_API_KEY` | API key for SambaNova (SYN) models | At least one API key is required |
| `ZAI_API_KEY` | API key for ZAI models | At least one API key is required |

### API Key Priority

When the same API key is defined in multiple places, Code Puppy uses this priority order:

1. **`.env` file** (highest priority) — a `.env` file in your current working directory
2. **`puppy.cfg`** — your Code Puppy configuration file
3. **Environment variable** — already set in your shell

### Examples

**Set via environment variable:**
```bash
export OPENAI_API_KEY="sk-your-key-here"
code-puppy
```

**Set via `.env` file:**
```bash
# Create a .env file in your project directory
echo 'OPENAI_API_KEY=sk-your-key-here' >> .env
code-puppy
```

**Set via Code Puppy config:**
```bash
code-puppy
# Then use: /config set OPENAI_API_KEY sk-your-key-here
```

---

## Code Puppy Behavior

These variables control Code Puppy's own behavior.

| Variable | Description | Default | Values |
|----------|-------------|---------|--------|
| `CODE_PUPPY_NO_TUI` | Disable interactive terminal UI elements (menus, pickers) | `0` (off) | `1` to disable |
| `CODE_PUPPY_NO_COLOR` | Disable colored output in tool results | `0` (off) | `1` to disable |
| `CODE_PUPPY_SKIP_TUTORIAL` | Skip the onboarding tutorial on first launch | Not set | `1`, `true`, or `yes` to skip |
| `CODE_PUPPY_DISABLE_RETRY_TRANSPORT` | Disable automatic HTTP request retries | Not set | `1`, `true`, or `yes` to disable |
| `NO_VERSION_UPDATE` | Disable automatic version checking on startup | Not set | `1`, `true`, `yes`, or `on` to disable |

### Examples

**Skip the tutorial for automated setups:**
```bash
export CODE_PUPPY_SKIP_TUTORIAL=1
code-puppy
```

**Disable colored output (useful for logging or piping):**
```bash
CODE_PUPPY_NO_COLOR=1 code-puppy
```

**Disable version checking:**
```bash
export NO_VERSION_UPDATE=1
code-puppy
```

---

## Network & Proxy

These standard environment variables configure network behavior.

| Variable | Description | Default |
|----------|-------------|---------|
| `HTTP_PROXY` / `http_proxy` | HTTP proxy URL for outgoing requests | Not set |
| `HTTPS_PROXY` / `https_proxy` | HTTPS proxy URL for outgoing requests | Not set |
| `SSL_CERT_FILE` | Path to a custom SSL/TLS certificate bundle | System default |

### Examples

**Route traffic through a corporate proxy:**
```bash
export HTTPS_PROXY="http://proxy.example.com:8080"
code-puppy
```

**Use a custom certificate bundle:**
```bash
export SSL_CERT_FILE="/path/to/custom-ca-bundle.crt"
code-puppy
```

> [!NOTE]
> When a proxy is detected, Code Puppy automatically enables proxy-aware HTTP handling. SSL verification remains active even behind a proxy.

---

## XDG Base Directories

Code Puppy follows the [XDG Base Directory Specification](https://specifications.freedesktop.org/basedir-spec/latest/) for file storage. By default, all files are stored in `~/.code_puppy`. Setting these variables moves files to XDG-compliant locations.

| Variable | What It Controls | Default Location |
|----------|-----------------|------------------|
| `XDG_CONFIG_HOME` | Configuration files (`puppy.cfg`, `mcp_servers.json`) | `~/.code_puppy` |
| `XDG_DATA_HOME` | Data files (models, agents, contexts) | `~/.code_puppy` |
| `XDG_CACHE_HOME` | Cache files (autosaves, browser profiles) | `~/.code_puppy` |
| `XDG_STATE_HOME` | State files (command history, error logs) | `~/.code_puppy` |

### How It Works

- **If the XDG variable is NOT set:** All files go to `~/.code_puppy` (the default)
- **If the XDG variable IS set:** Files go to `$XDG_<type>_HOME/code_puppy/`

### Example

```bash
# Use XDG-compliant paths
export XDG_CONFIG_HOME="$HOME/.config"
export XDG_DATA_HOME="$HOME/.local/share"
export XDG_CACHE_HOME="$HOME/.cache"
export XDG_STATE_HOME="$HOME/.local/state"

# Files will be stored at:
# Config:  ~/.config/code_puppy/puppy.cfg
# Data:    ~/.local/share/code_puppy/models.json
# Cache:   ~/.cache/code_puppy/autosaves/
# State:   ~/.local/state/code_puppy/command_history.txt
```

> [!TIP]
> Most users don't need to set XDG variables. The default `~/.code_puppy` directory works well for the majority of setups.

---

## Browser Automation

| Variable | Description | Default | Values |
|----------|-------------|---------|--------|
| `BROWSER_HEADLESS` | Run browser automation in headless mode (no visible browser window) | `true` | `false` to show the browser |

### Example

**See the browser during automated tasks:**
```bash
export BROWSER_HEADLESS=false
code-puppy
```

---

## DBOS (Advanced)

These variables control the optional DBOS integration for durable execution. Most users do not need to set these.

| Variable | Description | Default |
|----------|-------------|---------|
| `DBOS_SYSTEM_DATABASE_URL` | Database URL for DBOS storage | SQLite file in data directory |
| `DBOS_APP_VERSION` | Application version reported to DBOS | Auto-generated from Code Puppy version |
| `DBOS_CONDUCTOR_KEY` | API key for connecting to DBOS Conductor | Not set |
| `DBOS_LOG_LEVEL` | Log level for DBOS output | `ERROR` |

> [!NOTE]
> DBOS must be enabled in your `puppy.cfg` configuration file (`enable_dbos = true`) before these variables have any effect. See the [Configuration Reference](ConfigReference) for details.

---

## Quick Reference

| Category | Variable | Purpose |
|----------|----------|---------|
| **API Keys** | `OPENAI_API_KEY` | OpenAI authentication |
| | `ANTHROPIC_API_KEY` | Anthropic authentication |
| | `GEMINI_API_KEY` | Google Gemini authentication |
| | `OPENROUTER_API_KEY` | OpenRouter authentication |
| **Behavior** | `CODE_PUPPY_SKIP_TUTORIAL` | Skip onboarding |
| | `CODE_PUPPY_NO_COLOR` | Disable colors |
| | `NO_VERSION_UPDATE` | Skip version check |
| **Network** | `HTTPS_PROXY` | Proxy configuration |
| | `SSL_CERT_FILE` | Custom certificates |
| **Directories** | `XDG_CONFIG_HOME` | Config file location |
| | `XDG_DATA_HOME` | Data file location |

## See Also

- [Getting Started: Installation](../Getting-Started/Installation) — Setting up API keys
- [Getting Started: Configuration](../Getting-Started/Configuration) — Configuring Code Puppy
- [Reference: Configuration Options](ConfigReference) — All `puppy.cfg` settings
- [Guide: How to Add Models](../Guides/AddModels) — Adding new AI model providers
