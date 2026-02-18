import asyncio
import atexit
import os
import pathlib
import sys
import uuid
from typing import Any, Dict, Union

import uvicorn

from rich.text import Text

from code_puppy.callbacks import register_callback
from code_puppy.config import get_puppy_token
from code_puppy.http_utils import find_available_port
from code_puppy.messaging import emit_system_message

# CRITICAL: Import walmart_specific package to trigger monkey patches
# This must happen BEFORE any other imports that might use HTTP libraries
import code_puppy.plugins.walmart_specific  # noqa: F401

from code_puppy.plugins.walmart_specific.agent_prompt import get_prompt
from code_puppy.plugins.walmart_specific.auth import authenticate_puppy
from code_puppy.plugins.walmart_specific.auto_update import _handle_update
from code_puppy.plugins.walmart_specific.model_config_fetcher import ModelConfigFetcher
from code_puppy.plugins.walmart_specific.pingfed_auth import (
    get_pingfed_auth_help,
    get_puppy_auth_help,
    handle_pingfed_auth_command,
    handle_puppy_auth_command,
)
from code_puppy.plugins.walmart_specific.walmart_models import get_walmart_models
from code_puppy.plugins.walmart_specific.workspace_safety import (
    ensure_safe_windows_workspace,
)
from code_puppy.plugins.walmart_specific.bigquery_auth import (
    get_bigquery_auth_help,
    handle_bigquery_auth_command,
)
from code_puppy.plugins.walmart_specific.confluence_auth import (
    get_confluence_auth_help,
    handle_confluence_auth_command,
)
from code_puppy.plugins.walmart_specific.jira_auth import (
    get_jira_auth_help,
    handle_jira_auth_command,
    handle_jira_test_command,
)
from code_puppy.plugins.walmart_specific.msgraph_auth import (
    get_msgraph_auth_help,
    handle_msgraph_auth_command,
    handle_msgraph_test_command,
)
from code_puppy.plugins.walmart_specific.powerbi_auth import (
    get_powerbi_auth_help,
    handle_powerbi_auth_command,
    handle_powerbi_test_command,
)
from code_puppy.plugins.walmart_specific.disclaimer import (
    get_disclaimer_help,
    handle_disclaimer_command,
)
from code_puppy.plugins.walmart_specific.databricks_auth import (
    get_databricks_auth_help,
    handle_databricks_auth_command,
)
from code_puppy.plugins.walmart_specific.telemetry_utils import (
    build_delete_file_telemetry_data,
    build_shell_command_telemetry_data,
    build_telemetry_data,
    enqueue_telemetry_data,
)
from code_puppy.plugins.walmart_specific.camoufox_browser import (
    get_camoufox_browser_types,
)
from code_puppy.tools.command_runner import ShellCommandOutput
from code_puppy.mcp_.server_registry_catalog import (
    MCPServerTemplate,
    MCPServerRequirements,
)
from code_puppy.plugins.walmart_specific.walmart_gemini_model import WalmartGeminiModel
from code_puppy.plugins.walmart_specific.enterprise_tools import get_enterprise_tools


def get_walmart_mcp_servers():
    """Return Walmart-specific MCP server templates for the catalog."""
    return [
        MCPServerTemplate(
            id="github_enterprise",
            name="github_enterprise",
            display_name="GitHub Enterprise API",
            description="Access Walmart GitHub Enterprise APIs",
            category="Development",
            tags=["github", "api", "repository", "issues", "pull-requests", "walmart"],
            type="stdio",
            config={
                "command": "podman",
                "args": [
                    "run",
                    "-i",
                    "--rm",
                    "-e",
                    "GITHUB_PERSONAL_ACCESS_TOKEN",
                    "docker.ci.artifacts.walmart.com/ghcr-docker-release-remote/github/github-mcp-server",
                    "--gh-host",
                    "https://gecgithub01.walmart.com",
                    "stdio",
                ],
                "env": {
                    "GITHUB_PERSONAL_ACCESS_TOKEN": "$GITHUB_PERSONAL_ACCESS_TOKEN",
                },
                "timeout": 30,
            },
            verified=True,
            popular=True,
            requires=MCPServerRequirements(
                environment_vars=["GITHUB_PERSONAL_ACCESS_TOKEN"],
                required_tools=["podman"],
                package_dependencies=[],
                system_requirements=["GitHub account with personal access token"],
            ),
        ),
    ]


def set_cert_bundle() -> None:
    module_dir = pathlib.Path(__file__).parent.absolute()
    cert_path = module_dir / "certs" / "walmart-bundle.pem"
    if "_SSL_CERT_FILE" not in os.environ:
        os.environ["_SSL_CERT_FILE"] = str(cert_path)
        return
    print(
        "Warning: Existing SSL_CERT_FILE environment variable - NOT OVERRIDING WITH PACKAGED WALMART CERT",
        file=sys.stderr,
    )


session_id = str(uuid.uuid4())

set_cert_bundle()

register_callback("version_check", _handle_update)
register_callback("register_mcp_catalog_servers", get_walmart_mcp_servers)
register_callback("register_browser_types", get_camoufox_browser_types)
# Disclaimer is now shown via /disclaimer command instead of on startup


async def auth_flow() -> None:
    # HTTP server starts silently in the background

    # Find an available port before starting the HTTP server
    available_port = find_available_port()

    # Start the HTTP server in the background
    async def run_http_server() -> None:
        try:
            from code_puppy.plugins.walmart_specific.http_server import app as http_app

            config = uvicorn.Config(
                http_app,
                host="127.0.0.1",
                port=available_port,
                log_level="critical",  # suppress most logs
                access_log=False,  # suppress access logs
            )
            server = uvicorn.Server(config)
            await server.serve()
        except Exception as e:
            # Log HTTP server errors but don't crash the main application
            emit_system_message(
                Text.from_markup(f"[dim red]HTTP server error: {e}[/dim red]")
            )

    # Store the HTTP server task for proper lifecycle management
    http_server_task = asyncio.create_task(run_http_server())

    def shutdown_http_server() -> None:
        if not http_server_task.done():
            http_server_task.cancel()

    register_callback("shutdown", shutdown_http_server)

    await authenticate_puppy(available_port)

    token = get_puppy_token()
    os.environ["puppy_token"] = token


register_callback("startup", ensure_safe_windows_workspace)
register_callback("startup", auth_flow)


def load_model_config() -> Dict[str, Any]:
    config_fetcher = ModelConfigFetcher()
    return config_fetcher.load_config()


register_callback("load_model_config", load_model_config)
register_callback("load_models_config", get_walmart_models)
register_callback("load_prompt", get_prompt)


def collect_edit_file_telemetry(*args, **kwargs) -> None:
    """Collect telemetry data for edit_file operations.

    Accepts variable arguments to handle multiple call signatures:
    - collect_edit_file_telemetry(payload)
    - collect_edit_file_telemetry(context, result, payload)

    Uses the queue-based telemetry system for non-blocking, rate-limited processing.
    """
    try:
        # Handle both call signatures: payload alone, or (context, result, payload)
        if len(args) == 1:
            payload = args[0]
        elif len(args) == 3:
            payload = args[2]  # Third argument is the payload
        else:
            # Unexpected signature, log and return
            emit_system_message(
                f"[dim red]Edit file telemetry called with unexpected args count: {len(args)}[/dim red]"
            )
            return

        telemetry_data = build_telemetry_data(payload, session_id)
        enqueue_telemetry_data(telemetry_data)
    except Exception as e:
        emit_system_message(
            f"[dim red]Edit file telemetry error: {str(e)[:50]}[/dim red]"
        )


def collect_delete_file_telemetry(*args, **kwargs) -> None:
    """Collect telemetry data for delete_file operations.

    Accepts variable arguments to handle multiple call signatures:
    - collect_delete_file_telemetry(result)
    - collect_delete_file_telemetry(context, result, file_path)

    Uses the queue-based telemetry system for non-blocking, rate-limited processing.
    """
    try:
        if len(args) == 1:
            result = args[0]
        elif len(args) == 3:
            result = args[1]
        else:
            # Unexpected signature, log and return
            emit_system_message(
                f"[dim red]Delete file telemetry called with unexpected args count: {len(args)}[/dim red]"
            )
            return

        telemetry_data = build_delete_file_telemetry_data(result, session_id)
        enqueue_telemetry_data(telemetry_data)
    except Exception as e:
        emit_system_message(
            f"[dim red]Delete file telemetry error: {str(e)[:50]}[/dim red]"
        )


def collect_shell_command_telemetry(
    result: Union[ShellCommandOutput, Dict[str, Any]],
) -> None:
    """Collect telemetry data for run_shell_command operations.

    Uses the queue-based telemetry system for non-blocking, rate-limited processing.
    """
    try:
        telemetry_data = build_shell_command_telemetry_data(result, session_id)
        enqueue_telemetry_data(telemetry_data)
    except Exception as e:
        emit_system_message(
            f"[dim red]Shell command telemetry error: {str(e)[:50]}[/dim red]"
        )


# Telemetry shutdown handler
def shutdown_telemetry() -> None:
    """Gracefully shutdown the telemetry queue on application exit."""
    try:
        from code_puppy.plugins.walmart_specific.telemetry_queue import (
            shutdown_telemetry_queue,
        )

        shutdown_telemetry_queue()
    except ImportError:
        pass  # Telemetry queue not available
    except Exception as e:
        emit_system_message(
            f"[dim red]Telemetry shutdown error: {str(e)[:50]}[/dim red]"
        )


# Register telemetry callbacks
register_callback("edit_file", collect_edit_file_telemetry)
register_callback("delete_file", collect_delete_file_telemetry)
register_callback("run_shell_command_output", collect_shell_command_telemetry)
register_callback("shutdown", shutdown_telemetry)

atexit.register(shutdown_telemetry)

# Register custom command handlers
register_callback("custom_command_help", get_pingfed_auth_help)
register_callback("custom_command", handle_pingfed_auth_command)
register_callback("custom_command_help", get_puppy_auth_help)
register_callback("custom_command", handle_puppy_auth_command)
register_callback("custom_command_help", get_confluence_auth_help)
register_callback("custom_command", handle_confluence_auth_command)
register_callback("custom_command_help", get_jira_auth_help)
register_callback("custom_command", handle_jira_auth_command)
register_callback("custom_command", handle_jira_test_command)
register_callback("custom_command_help", get_bigquery_auth_help)
register_callback("custom_command", handle_bigquery_auth_command)
register_callback("custom_command_help", get_disclaimer_help)
register_callback("custom_command", handle_disclaimer_command)
register_callback("custom_command_help", get_msgraph_auth_help)
register_callback("custom_command", handle_msgraph_auth_command)
register_callback("custom_command", handle_msgraph_test_command)
register_callback("custom_command_help", get_powerbi_auth_help)
register_callback("custom_command", handle_powerbi_auth_command)
register_callback("custom_command", handle_powerbi_test_command)
register_callback("custom_command_help", get_databricks_auth_help)
register_callback("custom_command", handle_databricks_auth_command)


def get_walmart_model_providers():
    """Return Walmart-specific model provider classes for the plugin system."""
    return {"walmart_gemini": WalmartGeminiModel}


register_callback("register_model_providers", get_walmart_model_providers)
register_callback("register_tools", get_enterprise_tools)


# MOTD (Message of the Day) for Walmart internal users
def get_walmart_motd() -> tuple[str, str]:
    """Return Walmart-specific MOTD content.

    Returns:
        Tuple of (message, version) for the Walmart MOTD.
    """
    version = "2026-02-07"
    message = """🐕‍🦺
🐾```
# 🐶 What's New 🐕

- Fixed bugs in Opus 4.6 thinking/signature handling
  across provider swaps (Claude ↔ Gemini)
- Fixed typos and clarified rules in system prompt
- Gemini streaming now correctly persists thought
  signatures between turns
```
"""
    return (message, version)


register_callback("get_motd", get_walmart_motd)


# NOTE: Signature stripping callback was removed.
#
# Cross-provider signature handling is now done at the model layer:
# - pydantic-ai's built-in Anthropic model checks provider_name and only
#   sends signatures back when they match (Gemini parts become text).
# - Our custom GeminiModel._map_model_response checks provider_name and
#   converts foreign ThinkingParts to <thinking> XML text blocks.
#
# The old callback was destructive — it stripped Claude's OWN valid
# signatures between turns, forcing all prior thinking to become
# bloated XML text blocks and wasting tokens.
