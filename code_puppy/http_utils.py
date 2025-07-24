"""
HTTP utilities module for code-puppy.

This module provides functions for creating properly configured HTTP clients.
"""

import os
import pathlib
from typing import Dict, Optional, Union

import httpx
import requests


def get_cert_bundle_path() -> str:
    """
    Get the path to the certificate bundle to use.

    First checks if SSL_CERT_FILE environment variable is set.
    If not, falls back to the bundled Walmart certificate.

    Returns:
        Path to the certificate bundle file
    """
    # First check if SSL_CERT_FILE environment variable is set
    ssl_cert_file = os.environ.get("SSL_CERT_FILE")
    if ssl_cert_file and os.path.exists(ssl_cert_file):
        return ssl_cert_file

    # Fall back to the bundled certificate
    module_dir = pathlib.Path(__file__).parent.absolute()
    cert_path = module_dir / "certs" / "walmart-bundle.pem"
    return str(cert_path)


def create_client(
    timeout: int = 180,
    verify: Union[bool, str] = None,
    headers: Optional[Dict[str, str]] = None,
) -> httpx.Client:
    """
    Create a synchronous HTTP client with the specified configuration.

    Args:
        verify: Whether to verify SSL certificates. If None, uses the Walmart certificate bundle.
               If True, uses the default CA bundle. If False, disables verification.
               Can also be a path to a specific certificate bundle.
        headers: Optional headers to include with requests

    Returns:
        Configured httpx.Client instance
    """
    # If verify is None, use the Walmart certificate bundle
    if verify is None:
        verify = get_cert_bundle_path()

    return httpx.Client(verify=verify, headers=headers or {}, timeout=timeout)


def create_async_client(
    timeout: int = 180,
    verify: Union[bool, str] = None,
    headers: Optional[Dict[str, str]] = None,
) -> httpx.AsyncClient:
    """
    Create an asynchronous HTTP client with the specified configuration.

    Args:
        verify: Whether to verify SSL certificates. If None, uses the Walmart certificate bundle.
               If True, uses the default CA bundle. If False, disables verification.
               Can also be a path to a specific certificate bundle.
        headers: Optional headers to include with requests

    Returns:
        Configured httpx.AsyncClient instance
    """
    # If verify is None, use the Walmart certificate bundle
    if verify is None:
        verify = get_cert_bundle_path()

    return httpx.AsyncClient(verify=verify, headers=headers or {}, timeout=timeout)


def create_requests_session(
    timeout: float = 5.0,
    verify: Union[bool, str] = None,
    headers: Optional[Dict[str, str]] = None,
) -> requests.Session:
    """
    Create a requests Session with the specified configuration.

    Args:
        timeout: Request timeout in seconds
        verify: Whether to verify SSL certificates. If None, uses the Walmart certificate bundle.
               If True, uses the default CA bundle. If False, disables verification.
               Can also be a path to a specific certificate bundle.
        headers: Optional headers to include with requests

    Returns:
        Configured requests.Session instance
    """
    session = requests.Session()

    # If verify is None, use the Walmart certificate bundle
    if verify is None:
        verify = get_cert_bundle_path()

    session.verify = verify

    if headers:
        session.headers.update(headers or {})

    return session


def create_auth_headers(
    api_key: str, header_name: str = "Authorization"
) -> Dict[str, str]:
    """
    Create authorization headers using the provided API key.

    Args:
        api_key: The API key to use for authorization
        header_name: The header name to use (default: "Authorization")

    Returns:
        Dictionary containing the authorization header
    """
    return {header_name: f"Bearer {api_key}"}


def resolve_env_var_in_header(headers: Dict[str, str]) -> Dict[str, str]:
    """
    Resolve environment variables in header values.

    Header values that start with $ will be replaced with the corresponding
    environment variable value.

    Args:
        headers: Dictionary of headers that may contain environment variable references

    Returns:
        Dictionary with resolved header values
    """
    resolved_headers = {}

    for key, value in headers.items():
        if isinstance(value, str) and value.startswith("$"):
            env_var_name = value[1:]  # Remove the $ prefix
            env_var_value = os.environ.get(env_var_name)
            if env_var_value is not None:
                resolved_headers[key] = env_var_value
            else:
                # Keep the original value if environment variable is not found
                resolved_headers[key] = value
        else:
            resolved_headers[key] = value

    return resolved_headers


def is_cert_bundle_available() -> bool:
    """
    Check if the certificate bundle is available.

    Returns:
        True if the certificate bundle exists, False otherwise
    """
    cert_path = get_cert_bundle_path()
    return os.path.exists(cert_path) and os.path.isfile(cert_path)
