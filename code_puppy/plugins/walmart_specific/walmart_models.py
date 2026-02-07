"""Walmart-specific model configurations.

This module provides model configurations for Walmart's internal AI infrastructure,
using the puppy-backend proxy for accessing various model providers.
"""

from typing import Any, Dict


def get_walmart_models() -> Dict[str, Any]:
    """Return Walmart-specific model configurations.

    These models use Walmart's puppy-backend proxy and require
    the $puppy_token for authentication.

    Returns:
        Dict of model configurations keyed by model ID.
    """
    return {
        "claude-sonnet-4": {
            "custom_endpoint": {
                "api_key": "$puppy_token",
                "headers": {"X-Api-Key": "$puppy_token"},
                "url": "https://puppy-backend.stg.walmart.com/anthropic",
            },
            "name": "claude-sonnet-4",
            "type": "custom_anthropic",
            "context_length": 200000,
            "supported_settings": ["temperature", "interleaved_thinking"],
        },
        "gemini-2.5-pro": {
            "custom_endpoint": {
                "api_key": "$puppy_token",
                "headers": {"X-Goog-Api-Key": "$puppy_token"},
                "url": "https://puppy-backend.stg.walmart.com/gemini",
            },
            "name": "gemini-2.5-pro",
            "type": "custom_gemini",
            "context_length": 1048576,
            "supported_settings": [
                "temperature",
                "top_p",
                "thinking_enabled",
                "thinking_level",
            ],
        },
        "gemini-3-pro-preview": {
            "custom_endpoint": {
                "api_key": "$puppy_token",
                "headers": {"X-Goog-Api-Key": "$puppy_token"},
                "url": "https://puppy-backend.stg.walmart.com/gemini",
            },
            "name": "gemini-3-pro-preview",
            "type": "custom_gemini",
            "context_length": 200000,
            "supported_settings": [
                "temperature",
                "top_p",
                "thinking_enabled",
                "thinking_level",
            ],
        },
        "gemini-3-pro-preview-long": {
            "custom_endpoint": {
                "api_key": "$puppy_token",
                "headers": {"X-Goog-Api-Key": "$puppy_token"},
                "url": "https://puppy-backend.stg.walmart.com/gemini",
            },
            "name": "gemini-3-pro-preview",
            "type": "custom_gemini",
            "context_length": 1000000,
            "supported_settings": [
                "temperature",
                "top_p",
                "thinking_enabled",
                "thinking_level",
            ],
        },
        "gpt-4.1-custom": {
            "custom_endpoint": {
                "headers": {"X-Api-Key": "$puppy_token"},
                "url": "https://puppy-backend.stg.walmart.com",
            },
            "name": "gpt-4.1",
            "type": "custom_openai",
            "context_length": 1000000,
        },
        "o3-custom": {
            "custom_endpoint": {
                "headers": {"X-Api-Key": "$puppy_token"},
                "url": "https://puppy-backend.stg.walmart.com",
            },
            "name": "o3",
            "type": "custom_openai",
            "context_length": 200000,
        },
    }
