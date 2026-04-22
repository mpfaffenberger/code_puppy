"""AWS Bedrock Plugin for Code Puppy.

This plugin enables Code Puppy to use Anthropic Claude models hosted on
AWS Bedrock with standard AWS credential chain authentication (env vars,
profiles, IAM roles, SSO).

Supported models:
- Claude Opus 4.7 (1M context)
- Claude Opus 4.6 (1M context)
- Claude Sonnet 4.6 (1M context)
- Claude Haiku 4.5 (200K context)
"""

__version__ = "0.1.0"
