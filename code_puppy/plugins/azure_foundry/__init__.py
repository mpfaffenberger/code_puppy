"""Azure AI Foundry Plugin for Code Puppy.

This plugin enables Code Puppy to use Anthropic Claude models hosted on
Microsoft Azure AI Foundry with Azure AD (Entra ID) authentication.

The plugin uses the `az login` credentials from the Azure CLI to authenticate,
eliminating the need for API keys.

Supported models:
- Claude Opus 4.6 (1M context)
- Claude Sonnet 4.6 (1M context)
- Claude Haiku 4.5 (200K context)
"""

__version__ = "0.1.0"
