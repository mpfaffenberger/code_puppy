# Enabling the ChatGPT OAuth Plugin

## Quick Enable

To enable the ChatGPT OAuth plugin in Code Puppy, add these lines to your Code Puppy startup:

```python
# Add to your Code Puppy initialization or run in a session
import code_puppy.plugins.chatgpt_oauth.register_callbacks
```

## Auto-loading (Recommended)

For automatic loading, add the plugin to Code Puppy's plugin system:

### Option 1: Auto-load in main.py

Add to `code_puppy/main.py` in the plugin loading section:

```python
# Find the plugin loading section and add:
import code_puppy.plugins.chatgpt_oauth.register_callbacks
```

### Option 2: Plugin discovery

Ensure the plugin directory is in the Python path and Code Puppy can discover it:

```python
# Add to plugin discovery system
import code_puppy.plugins
plugins.discover_plugins()
```

## Verify Plugin is Loaded

Once Code Puppy is running, you should see the custom commands:

```bash
/help
```

Look for:
- `/chatgpt-auth` - Authenticate with ChatGPT via OAuth
- `/chatgpt-status` - Check ChatGPT OAuth status
- `/chatgpt-logout` - Remove ChatGPT OAuth tokens

## First Use

```bash
/chatgpt-auth
```

This will open your browser and guide you through the OAuth flow.

## Troubleshooting

### Plugin Not Found

If you get import errors:

1. **Check Python path**:
   ```bash
   echo $PYTHONPATH
   # Should include the code_puppy directory
   ```

2. **Check file structure**:
   ```bash
   ls -la code_puppy/plugins/chatgpt_oauth/
   ```

3. **Manual import test**:
   ```bash
   cd code_puppy
   python -c "from plugins.chatgpt_oauth.register_callbacks import _custom_help"
   ```

### Commands Not Available

If the plugin loads but commands aren't available:

1. **Check callback registration**:
   ```bash
   python -c "from plugins.chatgpt_oauth.register_callbacks import _custom_help; print(len(_custom_help()))"
   ```
   Should print: `3`

2. **Restart Code Puppy** after enabling the plugin

### Port Conflicts

If the OAuth callback fails with port errors:

1. **Check available ports**:
   ```bash
   lsof -i :8765-8795
   ```

2. **Kill conflicting processes**:
   ```bash
   lsof -ti:8765-8795 | xargs kill
   ```

## Development

### Testing the Plugin

Run the test suite:

```bash
cd code_puppy/plugins/chatgpt_oauth
python -m pytest test_plugin.py -v
```

or

```bash
python test_plugin.py
```

### Debug Mode

Enable debug logging:

```python
import logging
logging.getLogger("code_puppy.plugins.chatgpt_oauth").setLevel(logging.DEBUG)
```

### Custom Configuration

Edit `config.py` to customize:
- Client ID
- Port ranges
- Model prefixes
- API endpoints

## Security Notes

- The plugin stores OAuth tokens securely in `~/.code_puppy/chatgpt_oauth.json`
- File permissions are set to `0600` (owner read/write only)
- The API key is exposed via environment variable `CHATGPT_OAUTH_API_KEY`
- Never commit the token file to version control

---

🐶 Happy authenticating with ChatGPT OAuth!
