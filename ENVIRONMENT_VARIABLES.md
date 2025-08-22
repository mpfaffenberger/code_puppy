# Environment Variables for Code Puppy

This document lists all environment variables that can be used to configure Code Puppy.

## Model Configuration

| Variable | Description | Default | Used In |
|----------|-------------|---------|---------|
| `MODEL_NAME` | The model to use for code generation. Must match a key in the models.json configuration. | `gpt-4o` | agent.py |
| `MODELS_JSON_PATH` | Optional path to a custom models.json configuration file. | Package directory models.json | agent.py |
| `GEMINI_API_KEY` | API key for Google's Gemini models. | None | model_factory.py |
| `OPENAI_API_KEY` | API key for OpenAI models. | None | model_factory.py |
| `CEREBRAS_API_KEY` | API key for Cerebras models. | None | model_factory.py |

## Command Execution

| Variable | Description | Default | Used In |
|----------|-------------|---------|---------|
| `YOLO_MODE` | When set to "true" (case-insensitive), bypasses the safety confirmation prompt when running shell commands. This allows commands to execute without user intervention. | `false` | tools/command_runner.py |

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

```bash
# Use a specific model defined in models.json
export MODEL_NAME=gemini-2.5-flash-preview-05-20
code-puppy --interactive
```

## Version Store Location

Control where the SQLite version store database is created/read.

| Variable | Description | Default | Used In |
|----------|-------------|---------|---------|
| `CODE_PUPPY_DB_PATH` | Absolute or relative FILE path to the SQLite DB. Overrides all other location settings. | None | `code_puppy/version_store.py` |
| `CODE_PUPPY_DB_DIR` | Directory where `version_store.db` will be created/used. Overrides the project-local default. | None | `code_puppy/version_store.py` |

If neither is set, the DB defaults to a project-local path based on the current working directory at startup:

```
$CWD/.code_puppy/version_store.db
```

If the project-local path cannot be used, Code Puppy falls back to the home directory path:

```
~/.code_puppy/version_store.db
```

### Using a Custom Models Configuration

```bash
# Use a custom models.json file
export MODELS_JSON_PATH=/path/to/custom/models.json
code-puppy --interactive
```

### Bypassing Command Confirmation

```bash
# Run in YOLO mode to bypass command confirmations (use with caution)
export YOLO_MODE=true
code-puppy --interactive
```

### Setting API Keys

```bash
# Set API keys for model providers
export OPENAI_API_KEY=sk-...
export GEMINI_API_KEY=...
export CEREBRAS_API_KEY=...
code-puppy --interactive
```
