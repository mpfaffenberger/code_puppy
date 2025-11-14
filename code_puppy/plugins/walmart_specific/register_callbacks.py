import asyncio
import atexit
import os
import pathlib
import sys
import uuid
from typing import Any, Dict, Union

import uvicorn

from code_puppy.callbacks import register_callback
from code_puppy.config import get_puppy_token
from code_puppy.http_utils import find_available_port
from code_puppy.messaging import emit_system_message

# CRITICAL: Import walmart_specific package to trigger monkey patches
# This must happen BEFORE any other imports that might use HTTP libraries
import code_puppy.plugins.walmart_specific  # noqa: F401

from code_puppy.plugins.walmart_specific.agent_prompt import prompt
from code_puppy.plugins.walmart_specific.auth import authenticate_puppy
from code_puppy.plugins.walmart_specific.auto_update import _handle_update
from code_puppy.plugins.walmart_specific.model_config_fetcher import ModelConfigFetcher
from code_puppy.plugins.walmart_specific.pingfed_auth import (
    get_pingfed_auth_help,
    handle_pingfed_auth_command,
)
from code_puppy.plugins.walmart_specific.confluence_auth import (
    get_confluence_auth_help,
    handle_confluence_auth_command,
)
from code_puppy.plugins.walmart_specific.telemetry_utils import (
    build_delete_file_telemetry_data,
    build_shell_command_telemetry_data,
    build_telemetry_data,
    enqueue_telemetry_data,
)
from code_puppy.tools.command_runner import ShellCommandOutput


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
# Disclaimer is now shown via /disclaimer command instead of on startup


async def auth_flow() -> None:
    # HTTP server starts silently in the background

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
            emit_system_message(f"[dim red]HTTP server error: {e}[/dim red]")

    # Store the HTTP server task for proper lifecycle management
    http_server_task = asyncio.create_task(run_http_server())

    def shutdown_http_server() -> None:
        if not http_server_task.done():
            http_server_task.cancel()

    register_callback("shutdown", shutdown_http_server)

    available_port = find_available_port()
    await authenticate_puppy(available_port)

    token = get_puppy_token()
    os.environ["puppy_token"] = token


register_callback("startup", auth_flow)


def load_model_config() -> Dict[str, Any]:
    config_fetcher = ModelConfigFetcher()
    return config_fetcher.load_config()


register_callback("load_model_config", load_model_config)
register_callback("load_prompt", lambda: prompt)


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


def collect_delete_file_telemetry(result: Dict[str, Any]) -> None:
    """Collect telemetry data for delete_file operations.

    Uses the queue-based telemetry system for non-blocking, rate-limited processing.
    """
    try:
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
register_callback("custom_command_help", get_confluence_auth_help)
register_callback("custom_command", handle_confluence_auth_command)
