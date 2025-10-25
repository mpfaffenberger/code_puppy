# Claude Code OAuth Plugin Setup Guide

This guide walks you through using the Claude Code OAuth plugin inside Code Puppy.

## Quick Start

1. Ensure the plugin files live under `code_puppy/plugins/claude_code_oauth/`
2. Restart Code Puppy so it loads the plugin
3. Run `/claude-code-auth` and follow the prompts

## Why No Client Registration?

Anthropic exposes a shared **public client** (`claude-cli`) for command-line tools. That means:
- No client secret is needed
- Everyone authenticates through Claude Console
- Security is enforced with PKCE and per-user tokens

## Authentication Flow

1. Call `/claude-code-auth`
2. Your browser opens the Claude OAuth consent flow at `https://claude.ai/oauth/authorize`
3. Sign in (or pick an account) and approve the "Claude CLI" access request
4. The browser closes automatically after the redirect is captured
5. Tokens are stored locally at `~/.code_puppy/claude_code_oauth.json`
6. Available Claude Code models are fetched and added to `extra_models.json`

## Commands Recap

- `/claude-code-auth` – Authenticate and sync models
- `/claude-code-status` – Show auth status, expiry, configured models
- `/claude-code-logout` – Remove tokens and any models added by the plugin

## Configuration Defaults

`config.py` ships with values aligned to llxprt-code:

```python
CLAUDE_CODE_OAUTH_CONFIG = {
    "auth_url": "https://claude.ai/oauth/authorize",
    "token_url": "https://claude.ai/api/oauth/token",
    "api_base_url": "https://api.anthropic.com",
    "client_id": "9d1c250a-e61b-44d9-88ed-5944d1962f5e",
    "scope": "org:create_api_key user:profile user:inference",
    "redirect_host": "http://localhost",
    "redirect_path": "callback",
    "callback_port_range": (8765, 8795),
    "callback_timeout": 180,
    "prefix": "claude-code-",
    "default_context_length": 200000,
    "api_key_env_var": "CLAUDE_CODE_ACCESS_TOKEN",
}
```

Change these only if Anthropic updates their endpoints or scopes.

## After Authentication

- Models appear in `~/.code_puppy/extra_models.json` with the `claude-code-` prefix
- The environment variable `CLAUDE_CODE_ACCESS_TOKEN` is used by those models
- `/claude-code-status` shows token expiry when the API provides it

## Troubleshooting Tips

- **Browser did not open** – Copy the displayed URL into your browser manually
- **Invalid code** – The code expires quickly; generate a new one in Claude Console
- **State mismatch** – Rare, but rerun `/claude-code-auth` if the browser reports a mismatch
- **No models added** – Your account might lack Claude Code access; tokens are still stored for later use

## Files Created

```
~/.code_puppy/
├── claude_code_oauth.json   # OAuth tokens (0600 permissions)
└── extra_models.json        # Extended model registry
```

## Manual Testing

Run the helper script for sanity checks:

```bash
python code_puppy/plugins/claude_code_oauth/test_plugin.py
```

It verifies imports, configuration values, and filesystem expectations without hitting the Anthropic API.

## Security Notes

- Tokens are stored locally and never transmitted elsewhere
- PKCE protects the flow even without a client secret
- HTTPS endpoints are enforced for all requests

Enjoy hacking with Claude Code straight from Code Puppy! 🐶💻
