# ChatGPT OAuth Plugin Setup

## Prerequisites

1. **OpenAI Account**: You need a ChatGPT/OpenAI account
2. **Python Packages**: The plugin requires `requests` (already a Code Puppy dependency)

## Installation

The plugin is already included in Code Puppy at `code_puppy/plugins/chatgpt_oauth/`.

To enable it, simply import it in your Code Puppy session:

```python
from code_puppy.plugins.chatgpt_oauth import register_callbacks
```

Or add it to Code Puppy's plugin auto-loading system.

## First-Time Setup

### Step 1: Authenticate

Run the authentication command:

```bash
/chatgpt-auth
```

**⚠️ IMPORTANT - Complete authentication QUICKLY!** OpenAI OAuth sessions expire in 2-4 minutes and only work through `http://localhost:1455/auth/callback`.

This will:
1. 🌐 Open your browser to OpenAI's OAuth page
2. 🔑 Log in with your OpenAI account
3. ✅ Authorize Code Puppy to access your account
4. 🔄 Automatically redirect back to localhost
5. 🎯 Exchange the code for tokens
6. 🔑 Obtain an API key (if your account is set up)
7. 📚 Fetch available models

**Timing Tips:**
- ⏱️ Session countdown shows remaining time
- 🏃‍♂️ Complete auth within 1-2 minutes
- 📱 Keep browser tab open until success page
- 🔄 If "session expired" - retry immediately

### Step 2: Verify

Check that everything worked:

```bash
/chatgpt-status
```

You should see:
- ✅ "ChatGPT OAuth: Authenticated"
- ✓ "API key available" (if obtained)
- List of available models

### Step 3: Set Environment Variable (Optional but Recommended)

For persistent access across terminal sessions, add to your shell profile:

**Bash/Zsh** (`~/.bashrc` or `~/.zshrc`):
```bash
export CHATGPT_OAUTH_API_KEY="$(jq -r .api_key ~/.code_puppy/chatgpt_oauth.json 2>/dev/null)"
```

**Fish** (`~/.config/fish/config.fish`):
```fish
set -gx CHATGPT_OAUTH_API_KEY (jq -r .api_key ~/.code_puppy/chatgpt_oauth.json 2>/dev/null)
```

This ensures the API key is available every time you start Code Puppy.

## Usage

### Switch to ChatGPT Model

```bash
/model chatgpt-gpt-4o
```

### List Available Models

```bash
/models
```

Look for models with the `chatgpt-` prefix.

### Check Status Anytime

```bash
/chatgpt-status
```

## Troubleshooting

### "No API key" Warning

If authentication succeeds but no API key is obtained:

1. Your account may not have organization/project setup
2. Visit https://platform.openai.com
3. Create or join an organization
4. Create a project
5. Run `/chatgpt-auth` again

Alternatively, you can still use the OAuth tokens directly with OpenAI's API, but you'll need to handle token refresh manually.

### "Port in use" Error

The callback server must bind to port 1455 (matching the official Codex CLI).

To free the port:
```bash
lsof -ti:1455 | xargs kill
```

The OAuth flow will not work on any other port.

### "Route Error (400 Invalid Session)" or "Session expired"

**MOST COMMON ISSUE!** OpenAI OAuth sessions are very time-sensitive.

**Immediate Solution:**
```bash
/chatgpt-auth
# Complete authentication within 1-2 minutes!
```

**Why this happens:**
- OpenAI sessions expire in 2-4 minutes
- Taking too long during browser authentication
- Network delays or copying URLs manually

**Best Practices:**
1. **Click auth URL immediately** when it appears
2. **Complete login quickly** - don't browse other sites
3. **Keep browser tab open** until success page shows
4. **If expired, retry immediately** - don't wait
5. **Use fast internet connection** during auth

**Still failing?**
- Check internet speed and stability
- Try manual URL paste (but be super quick!)
- Ensure firewall allows localhost connections
- Check port availability: `lsof -i:8765-8795`

### Browser Doesn't Open Automatically

If `webbrowser.open()` fails:
1. Copy the URL printed in the terminal **IMMEDIATELY**
2. Paste it into your browser quickly
3. Complete the OAuth flow fast (under 2 minutes)
4. The callback should still work

### Tokens Expired

OAuth tokens are long-lived but can expire. Simply re-authenticate:

```bash
/chatgpt-auth
```

### Wrong Models Showing Up

If you see unexpected models:
1. Check `~/.code_puppy/chatgpt_models.json`
2. Remove entries with `"oauth_source": "chatgpt-oauth-plugin"`
3. Or run `/chatgpt-logout` and `/chatgpt-auth` again

## File Locations

- **Tokens**: `~/.code_puppy/chatgpt_oauth.json`
- **ChatGPT Models**: `~/.code_puppy/chatgpt_models.json`
- **Plugin**: `code_puppy/plugins/chatgpt_oauth/`

## Uninstallation

To completely remove ChatGPT OAuth:

1. Logout:
   ```bash
   /chatgpt-logout
   ```

2. Remove token file:
   ```bash
   rm ~/.code_puppy/chatgpt_oauth.json
   ```

3. Remove environment variable from shell profile

4. (Optional) Delete plugin directory:
   ```bash
   rm -rf code_puppy/plugins/chatgpt_oauth
   ```

## Advanced Configuration

### Custom OAuth Settings

Edit `config.py` to customize:

```python
CHATGPT_OAUTH_CONFIG = {
    "client_id": "Iv1.5a92863aee9e4f61",  # Official Codex CLI client
    "required_port": 1455,                # Fixed port required by OpenAI Codex CLI
    "callback_timeout": 120,              # 2 minutes to complete auth
    "prefix": "chatgpt-",                 # Model name prefix
    "default_context_length": 128000,     # Default for discovered models
}
```

### Using Different Client ID

If you have your own OAuth app:

1. Create OAuth app at https://platform.openai.com
2. Update `client_id` in `config.py`
3. Ensure redirect URI includes `http://localhost:1455/auth/callback`

### Model Filtering

By default, only `gpt-*`, `o1-*`, and `o3-*` models are imported. To change this, edit `fetch_chatgpt_models()` in `utils.py`:

```python
if model_id and (
    model_id.startswith("gpt-")
    or model_id.startswith("o1-")
    or model_id.startswith("o3-")
    or model_id.startswith("dall-e-")  # Add DALL-E
):
    models.append(model_id)
```

## Security Best Practices

1. **Never commit** `~/.code_puppy/chatgpt_oauth.json` to version control
2. **File permissions** are automatically set to `0600` (owner only)
3. **Token rotation**: Re-authenticate periodically for security
4. **Revoke access**: Visit https://platform.openai.com/account/authorized-apps to revoke
5. **Environment variables**: Be cautious about exposing `CHATGPT_OAUTH_API_KEY`

## FAQ

**Q: Is this official?**  
A: No, but it uses the same OAuth flow as OpenAI's official Codex CLI.

**Q: Will this cost money?**  
A: Using the OAuth flow is free. API calls are billed to your OpenAI account as usual.

**Q: Can I use this without organization setup?**  
A: You can authenticate, but you may not get an API key without org/project setup.

**Q: Does this work with ChatGPT Plus?**  
A: Yes, but API access requires separate setup on the Platform side.

**Q: Can I share my tokens?**  
A: No, tokens are tied to your account and should never be shared.

**Q: How long do tokens last?**  
A: Refresh tokens are long-lived (typically months), but can be revoked anytime.

---

🎉 That's it! You're ready to use ChatGPT OAuth with Code Puppy!
