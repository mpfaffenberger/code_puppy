# Environment Variables for Code Puppy

This document lists all environment variables that can be used to configure Code Puppy.

## Model Configuration

| Variable | Description | Default | Used In |
|----------|-------------|---------|---------|

| `GEMINI_API_KEY` | API key for Google's Gemini models. | None | model_factory.py |
| `OPENAI_API_KEY` | API key for OpenAI models. | None | model_factory.py |

## Command Execution

| Variable | Description | Default | Used In |
|----------|-------------|---------|---------|


## Custom Endpoints

When using custom endpoints (type: "custom_openai" in models.json), environment variables can be referenced in header values by prefixing with $ in models.json.

Example configuration in models.json:
```json
"gpt-4o-custom": {
  "type": "custom_openai",
  "name": "gpt-4o",
  "max_requests_per_minute": 100,
  "max_retries": 3,
  "retry_base_delay": 10,
  "custom_endpoint": {
    "url": "https://my.custom.endpoint:8080",
    "headers": {
      "X-Api-Key": "$OPENAI_API_KEY"
    }
  }
}
```

In this example, `$OPENAI_API_KEY` will be replaced with the value from the environment variable.

## Usage Examples

### Setting the Model

Model selection is now handled through the config file and interactive commands:

```bash
# In interactive mode, use ~m to switch models
code-puppy --interactive
# Then type: ~mgpt-4.1
# Or use the dev console: ~set model=gpt-4.1
```

### Model Configuration

Models are now automatically fetched from the remote endpoint (https://puppy.stg.walmart.com/api/puppy-models/latest) and cached locally in ~/.code_puppy/models.json. No environment variable configuration is needed.

The system will:
1. Try to fetch the latest config from the remote endpoint
2. Fall back to the local cached version if remote is unavailable  
3. Automatically update the local cache when remote config changes



### Setting API Keys

```bash
# Set API keys for model providers
export OPENAI_API_KEY=sk-...
export GEMINI_API_KEY=...
code-puppy --interactive
```
