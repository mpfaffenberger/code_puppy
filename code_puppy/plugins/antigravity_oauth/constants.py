"""Constants for Antigravity OAuth flows and Cloud Code Assist API integration."""

from typing import Any, Dict, List

# OAuth client credentials (from Antigravity/Google IDE)
ANTIGRAVITY_CLIENT_ID = (
    "1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com"
)
ANTIGRAVITY_CLIENT_SECRET = "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"

# OAuth scopes required for Antigravity integrations
ANTIGRAVITY_SCOPES: List[str] = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/cclog",
    "https://www.googleapis.com/auth/experimentsandconfigs",
]

# OAuth redirect URI for local CLI callback server
ANTIGRAVITY_REDIRECT_URI = "http://localhost:51121/oauth-callback"

# API endpoints (in fallback order: daily → autopush → prod)
ANTIGRAVITY_ENDPOINT_DAILY = "https://daily-cloudcode-pa.sandbox.googleapis.com"
ANTIGRAVITY_ENDPOINT_AUTOPUSH = "https://autopush-cloudcode-pa.sandbox.googleapis.com"
ANTIGRAVITY_ENDPOINT_PROD = "https://cloudcode-pa.googleapis.com"

ANTIGRAVITY_ENDPOINT_FALLBACKS = [
    ANTIGRAVITY_ENDPOINT_DAILY,
    ANTIGRAVITY_ENDPOINT_AUTOPUSH,
    ANTIGRAVITY_ENDPOINT_PROD,
]

# Preferred endpoint order for project discovery
ANTIGRAVITY_LOAD_ENDPOINTS = [
    ANTIGRAVITY_ENDPOINT_PROD,
    ANTIGRAVITY_ENDPOINT_DAILY,
    ANTIGRAVITY_ENDPOINT_AUTOPUSH,
]

# Primary endpoint (daily sandbox)
ANTIGRAVITY_ENDPOINT = ANTIGRAVITY_ENDPOINT_DAILY

# Default project ID fallback
ANTIGRAVITY_DEFAULT_PROJECT_ID = "rising-fact-p41fc"

# Request headers for Antigravity API
ANTIGRAVITY_HEADERS: Dict[str, str] = {
    "User-Agent": "antigravity/1.11.5 windows/amd64",
    "X-Goog-Api-Client": "google-cloud-sdk vscode_cloudshelleditor/0.1",
    "Client-Metadata": '{"ideType":"IDE_UNSPECIFIED","platform":"PLATFORM_UNSPECIFIED","pluginType":"GEMINI"}',
    "x-goog-api-key": "",  # Must be present but empty for Antigravity
}

# Request headers for Gemini CLI fallback
GEMINI_CLI_HEADERS: Dict[str, str] = {
    "User-Agent": "google-api-nodejs-client/9.15.1",
    "X-Goog-Api-Client": "gl-node/22.17.0",
    "Client-Metadata": "ideType=IDE_UNSPECIFIED,platform=PLATFORM_UNSPECIFIED,pluginType=GEMINI",
}

# Provider identifier
ANTIGRAVITY_PROVIDER_ID = "google"

# Available models with their configurations
ANTIGRAVITY_MODELS: Dict[str, Dict[str, Any]] = {
    # Gemini models
    "gemini-3-pro-low": {
        "name": "Gemini 3 Pro Low (Antigravity)",
        "family": "gemini",
        "context_length": 1048576,
        "max_output": 65535,
    },
    "gemini-3-pro-high": {
        "name": "Gemini 3 Pro High (Antigravity)",
        "family": "gemini",
        "context_length": 1048576,
        "max_output": 65535,
    },
    "gemini-3-flash": {
        "name": "Gemini 3 Flash (Antigravity)",
        "family": "gemini",
        "context_length": 1048576,
        "max_output": 65536,
    },
    # Claude models (non-thinking)
    "claude-sonnet-4-5": {
        "name": "Claude Sonnet 4.5 (Antigravity)",
        "family": "claude",
        "context_length": 200000,
        "max_output": 64000,
    },
    # Claude thinking models
    "claude-sonnet-4-5-thinking-low": {
        "name": "Claude Sonnet 4.5 Thinking Low (Antigravity)",
        "family": "claude",
        "context_length": 200000,
        "max_output": 64000,
        "thinking_budget": 8192,
    },
    "claude-sonnet-4-5-thinking-medium": {
        "name": "Claude Sonnet 4.5 Thinking Medium (Antigravity)",
        "family": "claude",
        "context_length": 200000,
        "max_output": 64000,
        "thinking_budget": 16384,
    },
    "claude-sonnet-4-5-thinking-high": {
        "name": "Claude Sonnet 4.5 Thinking High (Antigravity)",
        "family": "claude",
        "context_length": 200000,
        "max_output": 64000,
        "thinking_budget": 32768,
    },
    "claude-opus-4-5-thinking-low": {
        "name": "Claude Opus 4.5 Thinking Low (Antigravity)",
        "family": "claude",
        "context_length": 200000,
        "max_output": 64000,
        "thinking_budget": 8192,
    },
    "claude-opus-4-5-thinking-medium": {
        "name": "Claude Opus 4.5 Thinking Medium (Antigravity)",
        "family": "claude",
        "context_length": 200000,
        "max_output": 64000,
        "thinking_budget": 16384,
    },
    "claude-opus-4-5-thinking-high": {
        "name": "Claude Opus 4.5 Thinking High (Antigravity)",
        "family": "claude",
        "context_length": 200000,
        "max_output": 64000,
        "thinking_budget": 32768,
    },
}
