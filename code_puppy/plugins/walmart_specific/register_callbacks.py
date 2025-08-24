import asyncio
import os
import pathlib

import uvicorn

from code_puppy.callbacks import register_callback
from code_puppy.config import get_puppy_token
from code_puppy.http_utils import find_available_port
from code_puppy.messaging import emit_system_message
from code_puppy.plugins.walmart_specific.agent_prompt import prompt
from code_puppy.plugins.walmart_specific.auth import authenticate_puppy
from code_puppy.plugins.walmart_specific.auto_update import _handle_update
from code_puppy.plugins.walmart_specific.disclaimer import display_disclaimer
from code_puppy.plugins.walmart_specific.model_config_fetcher import ModelConfigFetcher


def set_cert_bundle():
    module_dir = pathlib.Path(__file__).parent.absolute()
    cert_path = module_dir / "certs" / "walmart-bundle.pem"
    os.environ["SSL_CERT_FILE"] = str(cert_path)


set_cert_bundle()

register_callback("version_check", _handle_update)
register_callback("startup", display_disclaimer)


async def auth_flow():
    # HTTP server starts silently in the background

    # Start the HTTP server in the background
    async def run_http_server():
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

    async def shutdown_http_server():
        if not http_server_task.done():
            http_server_task.cancel()
            try:
                await http_server_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                emit_system_message(
                    f"[dim red]HTTP server cleanup error: {e}[/dim red]"
                )

    register_callback("shutdown", shutdown_http_server)

    available_port = find_available_port()
    await authenticate_puppy(available_port)

    token = get_puppy_token()
    os.environ["puppy_token"] = token


register_callback("startup", auth_flow)


def load_model_config(config_path):
    config_fetcher = ModelConfigFetcher()
    return config_fetcher.load_config(config_path)


register_callback("load_model_config", load_model_config)
register_callback("load_prompt", lambda: prompt)
