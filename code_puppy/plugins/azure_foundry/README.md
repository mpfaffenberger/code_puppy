# Azure AI Foundry Plugin for Code Puppy

This plugin enables Code Puppy to use Anthropic Claude models hosted on
Microsoft Azure AI Foundry with Azure AD (Entra ID) authentication.

## Overview

Azure AI Foundry provides enterprise-grade hosting of Anthropic Claude models
within the Microsoft Azure cloud. This plugin uses your existing Azure CLI
credentials (`az login`) to authenticate, eliminating the need for API keys.

## Supported Models

| Model | Context Length | Deployment Name (Default) |
|-------|----------------|---------------------------|
| Claude Opus 4.6 | 1M tokens | `claude-opus-4-6` |
| Claude Sonnet 4.6 | 1M tokens | `claude-sonnet-4-6` |
| Claude Haiku 4.5 | 200K tokens | `claude-haiku-4-5` |

Deployment names are user-configurable during setup.

## Prerequisites

1. **Azure subscription** with access to Azure AI Foundry
2. **Azure CLI** installed and authenticated (`az login`)
3. **Claude model deployments** provisioned in your Azure AI Foundry resource
4. **Python packages**: `azure-identity>=1.15.0` (installed with Code Puppy)

## Quick Start

### 1. Authenticate with Azure

```bash
az login
```

### 2. Set Your Resource Name

```bash
export ANTHROPIC_FOUNDRY_RESOURCE=your-resource-name
```

### 3. Run Interactive Setup

```bash
pup
/foundry-setup
```

The wizard will guide you through configuring your model deployments.

### 4. Start Using Foundry Models

```bash
/model foundry-claude-opus
```

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `ANTHROPIC_FOUNDRY_RESOURCE` | Your Azure AI Foundry resource name | Yes |
| `ANTHROPIC_FOUNDRY_BASE_URL` | Override the base URL (optional) | No |

### Model Configuration

Models are stored in `~/.code_puppy/extra_models.json`:

```json
{
  "foundry-claude-opus": {
    "type": "azure_foundry",
    "name": "it-entra-claude-opus-4-6[1m]",
    "foundry_resource": "$ANTHROPIC_FOUNDRY_RESOURCE",
    "context_length": 1000000,
    "supported_settings": ["temperature", "extended_thinking", "budget_tokens"]
  },
  "foundry-claude-sonnet": {
    "type": "azure_foundry",
    "name": "it-entra-claude-sonnet-4-6[1m]",
    "foundry_resource": "$ANTHROPIC_FOUNDRY_RESOURCE",
    "context_length": 1000000,
    "supported_settings": ["temperature", "extended_thinking", "budget_tokens"]
  },
  "foundry-claude-haiku": {
    "type": "azure_foundry",
    "name": "it-entra-claude-haiku-4-5",
    "foundry_resource": "$ANTHROPIC_FOUNDRY_RESOURCE",
    "context_length": 200000,
    "supported_settings": ["temperature", "extended_thinking", "budget_tokens"]
  }
}
```

**Configuration Fields:**

- `type`: Must be `"azure_foundry"` to route to this plugin
- `name`: Your Azure deployment name (e.g., `it-entra-claude-opus-4-6`)
- `foundry_resource`: Resource name (supports `$ENV_VAR` syntax)
- `context_length`: Model context window in tokens
- `supported_settings`: List of supported model settings

## Context Window Configuration

Deployment names can include a context window suffix following the Claude Code format:
- `[1m]` - 1 million tokens
- `[2m]` - 2 million tokens
- `[200k]` - 200 thousand tokens
- `[500k]` - 500 thousand tokens

When you specify a deployment name with a context suffix (e.g., `it-entra-claude-opus-4-6[1m]`):
1. The suffix is **automatically stripped** before sending to Azure
2. The `context_length` is set based on the parsed suffix

**Example:**

During `/foundry-setup`, if you enter:
```
Opus deployment name: it-entra-claude-opus-4-6[1m]
```

The saved configuration will have:
- `name`: `it-entra-claude-opus-4-6` (suffix stripped)
- `context_length`: `1000000` (parsed from `[1m]`)

This is useful when your Azure deployment names don't include the context indicator,
but you want to configure the context length.

## Slash Commands

| Command | Description |
|---------|-------------|
| `/foundry-status` | Check Azure AD authentication status and configured models |
| `/foundry-setup` | Interactive wizard to configure Foundry models |
| `/foundry-remove` | Remove all Foundry model configurations |

### Example: /foundry-status

```
Azure AI Foundry Status
========================================
Authentication: Valid (expires in 45 minutes)
   Logged in as: user@company.com

Foundry Resource: my-foundry-resource

Configured Models (3):
   - foundry-claude-opus: it-entra-claude-opus-4-6[1m]
   - foundry-claude-sonnet: it-entra-claude-sonnet-4-6[1m]
   - foundry-claude-haiku: it-entra-claude-haiku-4-5
```

## How It Works

1. **Token Acquisition**: Uses `AzureCliCredential` from `azure-identity` to
   obtain tokens from your `az login` session

2. **Token Refresh**: The `get_bearer_token_provider` function handles automatic
   token refresh before expiry

3. **API Calls**: Creates an `AsyncAnthropicFoundry` client that uses the native
   Anthropic Messages API (not OpenAI format)

4. **Integration**: Wraps the client in pydantic-ai's `AnthropicModel` for
   seamless integration with Code Puppy's agent system

## Troubleshooting

### "CredentialUnavailableError" or "Not authenticated"

Run `az login` to authenticate with Azure:

```bash
az login
```

### "Resource not found" or "404 errors"

1. Verify `ANTHROPIC_FOUNDRY_RESOURCE` is set correctly
2. Check that your model deployments exist in Azure AI Foundry
3. Ensure the deployment names match your configuration

### Token Expiry

Tokens are automatically refreshed by the Azure Identity library. If you
encounter issues, try:

```bash
az account get-access-token --resource https://cognitiveservices.azure.com
```

### Model Not Found

After running `/foundry-setup`, verify configuration with `/foundry-status`.
Check that deployment names match exactly (case-sensitive).

## Architecture

```
code_puppy/plugins/azure_foundry/
├── __init__.py              # Package marker and version
├── config.py                # Constants and configuration helpers
├── token.py                 # Azure AD token provider
├── utils.py                 # Configuration file utilities
└── register_callbacks.py    # Plugin callbacks and model handler
```

## Security Notes

- **No API keys stored**: Authentication uses Azure AD tokens only
- **Token caching**: Managed by Azure CLI, not stored by this plugin
- **Credential scope**: Limited to `https://cognitiveservices.azure.com/.default`

## Contributing

This plugin follows Code Puppy's plugin architecture. Key callbacks:

- `register_model_type`: Registers `azure_foundry` type handler
- `custom_command`: Handles `/foundry-*` slash commands
- `custom_command_help`: Provides help text for commands

## License

Same as Code Puppy (see repository LICENSE file).
