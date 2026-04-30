"""
Devcontainer/remote environment detection and callback URL construction.

Automatically detects VS Code Remote Containers, GitHub Codespaces, Gitpod,
and other remote development environments, building appropriate callback URLs
for OAuth flows that can't use localhost.
"""

import os
import re
from typing import Optional

from code_puppy.messaging import emit_info, emit_system_message


def get_devcontainer_callback_url(port: int) -> Optional[str]:
    """
    Detect if we're in a devcontainer/remote environment and build the callback URL.

    Supports:
    - VS Code Remote Containers: VSCODE_PROXY_URI with {{port}} placeholder
    - GitHub Codespaces: CODESPACE_NAME + GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN
    - Gitpod: GITPOD_WORKSPACE_URL
    - Generic: AUTH_CALLBACK_URL env var with {{port}} or {port} placeholder

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

    # 2. Check for VS Code Remote Containers / Devcontainers
    vscode_proxy_uri = os.environ.get("VSCODE_PROXY_URI")
    if vscode_proxy_uri:
        # Format: https://agent-sandbox.stage.walmart.com/proxy/ws/test-app-22135501/proxy/{{port}}/
        url = _replace_port_placeholder(vscode_proxy_uri, port)
        url = _ensure_save_token_endpoint(url)
        emit_system_message(f"Detected devcontainer - using proxy URL: {url}")
        return url

    # 3. Check for GitHub Codespaces
    codespace_name = os.environ.get("CODESPACE_NAME")
    forwarding_domain = os.environ.get("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN")
    if codespace_name and forwarding_domain:
        # Codespaces format: https://{codespace_name}-{port}.{forwarding_domain}/
        url = f"https://{codespace_name}-{port}.{forwarding_domain}/save_token"
        emit_system_message(f"Detected Codespace - using: {url}")
        return url

    # 4. Check for Gitpod
    gitpod_workspace_url = os.environ.get("GITPOD_WORKSPACE_URL")
    if gitpod_workspace_url:
        # Gitpod format: Replace https:// with https://{port}-
        url = re.sub(r"^https://", f"https://{port}-", gitpod_workspace_url)
        url = _ensure_save_token_endpoint(url)
        emit_system_message(f"Detected Gitpod - using: {url}")
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
        "CODESPACE_NAME",
        "GITPOD_WORKSPACE_URL",
        "AUTH_CALLBACK_URL",
        "REMOTE_CONTAINERS",  # VS Code Remote Containers extension
    ]
    return any(os.environ.get(var) for var in indicators)
