# ChatGPT OAuth Plugin for Code Puppy

🎉 **Authenticate with ChatGPT/OpenAI using OAuth and get access to all your models!**

This plugin implements the same OAuth flow used by OpenAI's Codex CLI, allowing you to:
- Authenticate with your OpenAI account via browser
- Automatically obtain an API key (if your account has org/project setup)
- Import all available ChatGPT models into Code Puppy
- Use the models with the `chatgpt-` prefix

## Features

- 🔐 **Secure OAuth 2.0 + PKCE flow** - Same as official OpenAI CLI
- 🔁 **Fixed callback port (1455)** - Matches Codex CLI requirements
- 🤖 **Automatic API key exchange** - No manual key copying needed
- 🎯 **Auto model discovery** - Fetches all available GPT models
- 💾 **Persistent tokens** - Stored securely in `~/.code_puppy/chatgpt_oauth.json`
- 🎨 **Fun success pages** - Because OAuth should be delightful!

## Quick Start

### 1. Authenticate

```bash
/chatgpt-auth
```

This will:
1. Open your browser to OpenAI's login page
2. After you authorize, redirect back to localhost
3. Exchange the code for tokens
4. Attempt to obtain an API key
5. Fetch available models and add them to your config

### 2. Check Status

```bash
/chatgpt-status
```

Shows:
- Authentication status
- Whether API key is available
- List of configured models

### 3. Use Models

Once authenticated, use any discovered model:

```bash
/model chatgpt-gpt-4o
/model chatgpt-o1-preview
/model chatgpt-gpt-3.5-turbo
```

All models are prefixed with `chatgpt-` to distinguish them from other providers.

### 4. Logout

```bash
/chatgpt-logout
```

Removes:
- OAuth tokens from disk
- API key from environment
- All imported models from config

## How It Works

### OAuth Flow

1. **Initiate**: Creates PKCE challenge and opens browser to OpenAI auth URL
2. **Authorize**: User logs in and authorizes Code Puppy
3. **Callback**: OpenAI redirects to `http://localhost:8765-8795/auth/callback`
4. **Exchange**: Code is exchanged for `access_token`, `refresh_token`, and `id_token`
5. **API Key**: Uses token exchange grant to obtain OpenAI API key
6. **Models**: Fetches available models from `/v1/models` endpoint

### Token Storage

Tokens are stored in `~/.code_puppy/chatgpt_oauth.json`:

```json
{
  "access_token": "...",
  "refresh_token": "...",
  "id_token": "...",
  "api_key": "sk-proj-...",
  "last_refresh": "2025-05-15T10:30:00Z"
}
```

File permissions are set to `0600` (owner read/write only).

### Environment Variable

The API key is set in your environment as `CHATGPT_OAUTH_API_KEY`. Models recorded in `~/.code_puppy/chatgpt_models.json` reference this:

```json
{
  "chatgpt-gpt-4o": {
    "type": "openai",
    "name": "gpt-4o",
    "custom_endpoint": {
      "url": "https://api.openai.com",
      "api_key": "$CHATGPT_OAUTH_API_KEY"
    },
    "context_length": 128000,
    "oauth_source": "chatgpt-oauth-plugin"
  }
}
```

## Troubleshooting

### No API Key Obtained

If authentication succeeds but no API key is generated, you may need to:

1. Visit [OpenAI Platform](https://platform.openai.com)
2. Create or join an organization
3. Set up a project
4. Run `/chatgpt-auth` again

The API key exchange requires your account to have `organization_id` and `project_id` in the JWT claims.

### Port Already in Use

The plugin requires port `1455` (matches the official Codex CLI). If the port is in use:

1. Kill the process using that port: `lsof -ti:1455 | xargs kill`
2. Retry `/chatgpt-auth` after freeing the port

### Browser Doesn't Open

If the browser fails to open automatically, copy the URL from the terminal and paste it manually.

### Session Expired (Route Error 400)

If you see "Route Error (400 Invalid Session): Your authorization session was not initialized or has expired":

```bash
/chatgpt-auth
```

**Quick fix - Run authentication immediately!** OpenAI OAuth sessions are very time-sensitive.

**Why this happens:**
- OpenAI OAuth sessions expire in 2-4 minutes
- Taking too long to complete the browser flow
- Network delays or manual copy-paste delays

**Solutions:**
1. **Complete authentication within 1-2 minutes** after `/chatgpt-auth`
2. **Keep the browser tab open** until you see the success page
3. **Click the OAuth URL immediately** when it appears
4. **If expired, run `/chatgpt-auth` again** right away

The plugin now shows:
- ⏱️ Session countdown during authentication
- ⚠️ Warnings about session expiration
- 💔 Clear error messages when sessions expire

### Token Expired

Stored OAuth tokens are long-lived but may expire. Simply run `/chatgpt-auth` again to refresh.

## Configuration

You can customize the plugin by editing `config.py`:

```python
CHATGPT_OAUTH_CONFIG = {
    "issuer": "https://auth.openai.com",
    "client_id": "Iv1.5a92863aee9e4f61",  # Official Codex CLI client ID
    "required_port": 1455,
    "callback_timeout": 120,
    "prefix": "chatgpt-",  # Model name prefix
    # ... more options
}
```

## Comparison with Manual API Keys

| Feature | OAuth Plugin | Manual API Key |
|---------|-------------|----------------|
| Setup time | 30 seconds | 2-5 minutes |
| Browser needed | Yes (once) | Yes |
| Key rotation | Automatic | Manual |
| Model discovery | Automatic | Manual |
| Revocation | Easy | Platform only |

## Security

- **PKCE**: Prevents authorization code interception
- **State parameter**: Prevents CSRF attacks
- **Localhost only**: Callback server only binds to `127.0.0.1`
- **File permissions**: Token file is `chmod 600`
- **No secrets**: Client ID is public (same as official CLI)

## Architecture

Based on the same patterns as the `claude_code_oauth` plugin:

```
chatgpt_oauth/
├── __init__.py              # Plugin metadata
├── config.py               # OAuth configuration
├── utils.py                # PKCE, token exchange, model fetch
├── register_callbacks.py   # Main plugin logic
└── README.md               # This file
```

## Credits

OAuth flow reverse-engineered from [ChatMock](https://github.com/mpfaffenberger/ChatMock), which implements the official OpenAI Codex CLI OAuth.

Plugin architecture follows the `claude_code_oauth` plugin pattern.

## License

Same as Code Puppy main project.

---

🐶 **Woof woof!** Happy coding with ChatGPT OAuth! 🐶
