# Claude Code OAuth Plugin

This plugin adds OAuth authentication for Claude Code to Code Puppy, automatically importing available models into your configuration.

## Features

- **OAuth Authentication**: Secure OAuth flow for Claude Code using PKCE
- **Automatic Model Discovery**: Fetches available models from the Claude API once authenticated
- **Model Registration**: Automatically adds models to `extra_models.json` with the `claude-code-` prefix
- **Token Management**: Secure storage of OAuth tokens in the Code Puppy config directory
- **Browser Integration**: Launches the Claude OAuth consent flow automatically
- **Callback Capture**: Listens on localhost to receive and process the OAuth redirect

## Commands

### `/claude-code-auth`
Authenticate with Claude Code via OAuth and import available models.

This will:
1. Launch the Claude OAuth consent flow in your browser
2. Walk you through approving access for the shared `claude-cli` client
3. Capture the redirect from Claude in a temporary local callback server
4. Exchange the returned code for access tokens and store them securely
5. Fetch available models from Claude Code and add them to your configuration

### `/claude-code-status`
Check Claude Code OAuth authentication status and configured models.

Shows:
- Current authentication status
- Token expiry information (if available)
- Number and names of configured Claude Code models

### `/claude-code-logout`
Remove Claude Code OAuth tokens and imported models.

This will:
1. Remove stored OAuth tokens
2. Remove all Claude Code models from `extra_models.json`

## Setup

### Prerequisites

1. **Claude account** with access to the Claude Console developer settings
2. **Browser access** to generate authorization codes

### Configuration

The plugin ships with sensible defaults in `config.py`:

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

These values mirror the public client used by llxprt-code. Adjust only if Anthropic changes their configuration.

### Environment Variables

After authentication, the models will reference:
- `CLAUDE_CODE_ACCESS_TOKEN`: Automatically written by the plugin

## Usage Example

```bash
# Authenticate with Claude Code
/claude-code-auth

# Check status
/claude-code-status

# Use a Claude Code model
/set model claude-code-claude-3-5-sonnet-20241022

# When done, logout
/claude-code-logout
```

## Model Configuration

After authentication, models will be added to `~/.code_puppy/extra_models.json`:

```json
{
  "claude-code-claude-3-5-sonnet-20241022": {
    "type": "anthropic",
    "name": "claude-3-5-sonnet-20241022",
    "custom_endpoint": {
      "url": "https://api.anthropic.com",
      "api_key": "$CLAUDE_CODE_ACCESS_TOKEN"
    },
    "context_length": 200000,
    "oauth_source": "claude-code-plugin"
  }
}
```

## Security

- **Token Storage**: Tokens are saved to `~/.code_puppy/claude_code_oauth.json` with `0o600` permissions
- **PKCE Support**: Uses Proof Key for Code Exchange for enhanced security
- **State Validation**: Checks the returned state (if provided) to guard against CSRF
- **HTTPS Only**: All OAuth communications use HTTPS endpoints

## Troubleshooting

### Browser doesn't open
- Manually visit the URL shown in the output
- Check that a default browser is configured

### Authentication fails
- Ensure the browser completed the redirect back to Code Puppy (no pop-up blockers)
- Retry if the window shows an error; codes expire quickly
- Confirm network access to `claude.ai`

### Models not showing up
- Claude may not return the model list for your account; verify access manually
- Check `/claude-code-status` to confirm authentication succeeded

## Development

### File Structure

```
claude_code_oauth/
├── __init__.py
├── register_callbacks.py  # Main plugin logic and command handlers
├── config.py              # Configuration settings
├── utils.py               # OAuth helpers and file operations
├── README.md              # This file
├── SETUP.md               # Quick setup guide
└── test_plugin.py         # Manual test helper
```

### Key Components

- **OAuth Flow**: Authorization code flow with PKCE and automatic callback capture
- **Token Management**: Secure storage and retrieval helpers
- **Model Discovery**: API integration for model fetching
- **Plugin Registration**: Custom command handlers wired into Code Puppy

## Notes

- The plugin assumes Anthropic continues to expose the shared `claude-cli` OAuth client
- Tokens are refreshed on subsequent API calls if the service returns refresh tokens
- Models are prefixed with `claude-code-` to avoid collisions with other Anthropic models

## Contributing

When modifying this plugin:
1. Maintain security best practices
2. Test OAuth flow changes manually before shipping
3. Update documentation for any configuration or UX changes
4. Keep files under 600 lines; split into helpers when needed
