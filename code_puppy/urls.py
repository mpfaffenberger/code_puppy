"""
URL management module for code-puppy.

This module handles construction of URLs for different environments (dev, prod, and stage).
It provides a consistent interface for accessing all application endpoints.
"""

from enum import Enum
from typing import Optional


class Environment(Enum):
    """Supported environments for URL construction."""

    DEV = "dev"
    STAGE = "stg"
    PROD = "prod"


class BaseURLs:
    """Base URLs for different environments."""

    DEV = "https://puppy.dev.walmart.com"
    STAGE = "https://puppy.stg.walmart.com"
    PROD = "https://puppy.walmart.com"


def get_base_url(environment: Environment = Environment.STAGE) -> str:
    """
    Get the base URL for the specified environment.

    Args:
        environment: The target environment

    Returns:
        The base URL for the specified environment
    """
    if environment == Environment.DEV:
        return BaseURLs.DEV
    elif environment == Environment.STAGE:
        return BaseURLs.STAGE
    elif environment == Environment.PROD:
        return BaseURLs.PROD
    else:
        raise ValueError(f"Unsupported environment: {environment}")


def get_models_url(environment: Environment = Environment.STAGE) -> str:
    """
    Get the URL for fetching model configurations.

    Args:
        environment: The target environment

    Returns:
        The models URL for the specified environment
    """
    base_url = get_base_url(environment)
    return f"{base_url}/api/puppy-models/latest"


def get_authentication_url(
    port: Optional[int] = None, environment: Environment = Environment.STAGE
) -> str:
    """
    Get the URL for puppy authentication.

    Args:
        port: The local port for the callback server
        environment: The target environment

    Returns:
        The authentication URL for the specified environment
    """
    base_url = get_base_url(environment)
    url = f"{base_url}/authenticate_puppy"

    if port is not None:
        url = f"{url}?port={port}"

    return url


def get_latest_version_url(environment: Environment = Environment.STAGE) -> str:
    """
    Get the URL for fetching the latest version information.

    Args:
        environment: The target environment

    Returns:
        The latest version URL for the specified environment
    """
    base_url = get_base_url(environment)
    return f"{base_url}/api/releases/latest"


def get_setup_url(environment: Environment = Environment.STAGE) -> str:
    """
    Get the URL for the setup script.

    Args:
        environment: The target environment

    Returns:
        The setup URL for the specified environment
    """
    base_url = get_base_url(environment)
    return f"{base_url}/api/releases/setup"
