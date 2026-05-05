"""Devcontainer/remote environment detection and callback URL construction.

Automatically detects VS Code devcontainers (e.g., agent-sandbox) and builds
appropriate callback URLs for OAuth flows that can't use localhost.
"""

import os
from typing import Optional

from code_puppy.messaging import emit_info, emit_system_message


def get_devcontainer_callback_url(port: int) -> Optional[str]:
    """
    Detect if we're in a devcontainer/remote environment and build the callback URL.

    Supports:
    - VS Code devcontainers: VSCODE_PROXY_URI with {{port}} placeholder
    - Manual override: AUTH_CALLBACK_URL env var with {{port}} or {port} placeholder

    Args:
        port: The local port code-puppy's HTTP server is listening on.

    Returns:
        Full callback URL if in a supported remote environment, None otherwise.
    """

    # 1. Check for explicit AUTH_CALLBACK_URL (highest priority - user override)
    auth_callback_url = os.environ.get("AUTH_CALLBACK_URL")
    if auth_callback_url:
        url = _replace_port_placeholder(auth_callback_url, port)
        url = _ensure_save_token_endpoint(url)
        emit_info(f"Using AUTH_CALLBACK_URL: {url}")
        return url

    # 2. Check for VS Code devcontainers (e.g., agent-sandbox)
    vscode_proxy_uri = os.environ.get("VSCODE_PROXY_URI")
    if vscode_proxy_uri:
        # Format: https://agent-sandbox.stage.walmart.com/proxy/ws/test-app-22135501/proxy/{{port}}/
        url = _replace_port_placeholder(vscode_proxy_uri, port)
        url = _ensure_save_token_endpoint(url)
        emit_system_message(f"Detected devcontainer - using proxy URL: {url}")
        return url

    # Not in a detected remote environment
    return None


def _replace_port_placeholder(url: str, port: int) -> str:
    """Replace port placeholders in URL template."""
    # Handle VS Code's {{port}} syntax
    url = url.replace("{{port}}", str(port))
    # Handle {port} syntax (Python format string style)
    url = url.replace("{port}", str(port))
    return url


def _ensure_save_token_endpoint(url: str) -> str:
    """Ensure the URL ends with /save_token endpoint."""
    url = url.rstrip("/")
    if not url.endswith("/save_token"):
        url = f"{url}/save_token"
    return url


def is_remote_environment() -> bool:
    """Check if we're running in any known remote/devcontainer environment."""
    indicators = [
        "VSCODE_PROXY_URI",
        "AUTH_CALLBACK_URL",
        "REMOTE_CONTAINERS",  # VS Code Remote Containers extension
    ]
    return any(os.environ.get(var) for var in indicators)
