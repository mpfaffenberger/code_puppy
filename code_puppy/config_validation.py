"""
Configuration validation helpers for Code Puppy models.

This module provides validation functions for specific model configurations
to ensure they are properly set up before use.

This is fork-specific and provides stricter validation than upstream.
"""

import os
from typing import Dict, Any


def validate_cerebras_glm47_config(config: Dict[str, Any]) -> None:
    """
    Validate the Cerebras-GLM-4.7 model configuration.
    
    Raises ValueError on invalid configuration.
    
    Args:
        config: The complete models configuration dictionary
        
    Raises:
        ValueError: If configuration is invalid
    """
    model_cfg = config.get("Cerebras-GLM-4.7")
    
    if not model_cfg:
        # If the model is not present at all, do nothing here.
        return
    
    if model_cfg.get("type") != "cerebras":
        raise ValueError(
            "Cerebras-GLM-4.7 config must have type='cerebras' to use CerebrasProvider."
        )
    
    endpoint = model_cfg.get("custom_endpoint", {})
    api_key_env = endpoint.get("api_key", "")
    
    # Check environment variable reference (e.g., $CEREBRAS_API_KEY)
    if api_key_env.startswith("$"):
        env_var = api_key_env[1:]
        if not os.getenv(env_var):
            raise ValueError(
                f"Cerebras-GLM-4.7 requires '{env_var}' environment variable to be set."
            )
    
    # Validate context length
    ctx_len = model_cfg.get("context_length", 0)
    if ctx_len <= 0 or ctx_len > 2_000_000:
        raise ValueError(
            f"Invalid context_length for Cerebras-GLM-4.7: {ctx_len}"
        )
    
    # Validate max_tokens if present
    max_tokens = model_cfg.get("max_tokens", 0)
    if max_tokens and max_tokens > ctx_len:
        raise ValueError(
            f"Cerebras-GLM-4.7 max_tokens ({max_tokens}) cannot exceed "
            f"context_length ({ctx_len})."
        )
    
    # Validate required fields
    if not model_cfg.get("name"):
        raise ValueError("Cerebras-GLM-4.7 config must have a 'name' field.")
    
    # Validate custom_endpoint
    if not endpoint:
        raise ValueError("Cerebras-GLM-4.7 config must have 'custom_endpoint' field.")
    
    if not endpoint.get("url"):
        raise ValueError("Cerebras-GLM-4.7 custom_endpoint must have 'url' field.")


def validate_custom_openai_config(config: Dict[str, Any], model_name: str) -> None:
    """
    Validate a custom_openai model configuration.
    
    Args:
        config: The complete models configuration dictionary
        model_name: The name of the model to validate
        
    Raises:
        ValueError: If configuration is invalid
    """
    model_cfg = config.get(model_name)
    
    if not model_cfg:
        return
    
    if model_cfg.get("type") != "custom_openai":
        raise ValueError(
            f"{model_name} config must have type='custom_openai'."
        )
    
    endpoint = model_cfg.get("custom_endpoint", {})
    if not endpoint:
        raise ValueError(f"{model_name} config must have 'custom_endpoint' field.")
    
    # Check API key environment variable
    api_key_env = endpoint.get("api_key", "")
    if api_key_env.startswith("$"):
        env_var = api_key_env[1:]
        if not os.getenv(env_var):
            raise ValueError(
                f"{model_name} requires '{env_var}' environment variable to be set."
            )
    
    # Validate required fields
    if not model_cfg.get("name"):
        raise ValueError(f"{model_name} config must have a 'name' field.")
    
    ctx_len = model_cfg.get("context_length", 0)
    if ctx_len <= 0:
        raise ValueError(
            f"Invalid context_length for {model_name}: {ctx_len}"
        )
