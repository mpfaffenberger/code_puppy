"""Databricks authentication module.

This module handles OAuth U2M (User to Machine) authentication for Databricks
using user credentials. It uses the Databricks SDK's built-in OAuth support
which automatically handles token acquisition and refresh.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from code_puppy.config import CONFIG_DIR
from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning
from code_puppy.plugins.walmart_specific.databricks_client import (
    get_databricks_config_path,
    save_databricks_config,
)


def _install_databricks_dependencies() -> bool:
    """Install Databricks Python dependencies.

    Returns:
        True if installation succeeded or dependencies already present
    """
    try:
        import databricks.sdk  # noqa: F401

        emit_success("Databricks SDK is already installed")
        return True
    except ImportError:
        pass

    emit_info("Installing Databricks SDK...")

    try:
        # Use Walmart's internal PyPI proxy to avoid corporate firewall blocks
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "databricks-sdk>=0.20.0",
                "--index-url",
                "https://repository.walmart.com/repository/pypi-proxy/simple/",
                "--trusted-host",
                "repository.walmart.com",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode == 0:
            emit_success("Databricks SDK installed successfully!")
            return True
        else:
            emit_error(f"Failed to install Databricks SDK: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        emit_error("Installation timed out")
        return False
    except Exception as e:
        emit_error(f"Installation failed: {e}")
        return False


def _get_user_input(prompt: str, default: Optional[str] = None) -> str:
    """Get user input with optional default value.

    Args:
        prompt: The prompt to display
        default: Optional default value

    Returns:
        User input or default value
    """
    if default:
        full_prompt = f"{prompt} [{default}]: "
    else:
        full_prompt = f"{prompt}: "

    try:
        value = input(full_prompt).strip()
        if not value and default:
            return default
        return value
    except (EOFError, KeyboardInterrupt):
        return default or ""


def _test_databricks_connection(
    host: str, warehouse_id: Optional[str] = None
) -> bool:
    """Test Databricks connection with OAuth U2M (external browser).

    Args:
        host: Databricks workspace URL
        warehouse_id: Optional SQL warehouse ID

    Returns:
        True if connection successful
    """
    try:
        from databricks.sdk import WorkspaceClient

        emit_info("Testing connection...")

        # Initialize client with external-browser auth type
        # This explicitly triggers the OAuth U2M browser-based flow
        # which opens a browser for user authentication
        client = WorkspaceClient(host=host, auth_type="external-browser")

        # Test by getting current user
        current_user = client.current_user.me()
        emit_success(f"Authenticated as: {current_user.user_name}")

        # List available warehouses
        emit_info("Listing available SQL warehouses...")
        warehouses = list(client.warehouses.list())

        if warehouses:
            emit_info("Available SQL warehouses:")
            for wh in warehouses:
                state = str(wh.state) if wh.state else "UNKNOWN"
                marker = " (selected)" if wh.id == warehouse_id else ""
                emit_info(f"  - {wh.name} (ID: {wh.id}) - State: {state}{marker}")
        else:
            emit_warning("No SQL warehouses found. You may need to create one.")

        return True

    except Exception as e:
        emit_error(f"Connection test failed: {e}")
        return False


def handle_databricks_auth_command(command: str, name: str) -> Optional[str]:
    """Handle the /databricks_auth command.

    This command:
    1. Installs Databricks SDK if needed
    2. Prompts for Databricks workspace configuration
    3. Tests OAuth U2M authentication (opens browser for login)
    4. Saves configuration to ~/.code_puppy/databricks.json

    Args:
        command: The full command string
        name: The command name without the slash

    Returns:
        Optional[str]: Success/error message, or None if not handled
    """
    if name != "databricks_auth":
        return None

    emit_info("Starting Databricks authentication flow...")

    # Step 1: Install dependencies
    if not _install_databricks_dependencies():
        return "Failed to install Databricks dependencies. Please install manually: pip install databricks-sdk"

    # Step 2: Load existing config or prompt for new values
    config_path = get_databricks_config_path()
    existing_config = {}

    if config_path.exists():
        try:
            with open(config_path, "r") as f:
                existing_config = json.load(f)
            emit_info(f"Found existing configuration at {config_path}")
        except Exception:
            pass

    emit_info("")
    emit_info("=" * 60)
    emit_info("Databricks Workspace Configuration")
    emit_info("=" * 60)
    emit_info("")
    emit_info("Please provide your Databricks workspace details.")
    emit_info("Press Enter to keep existing values (shown in brackets).")
    emit_info("")

    # Get workspace URL
    default_host = existing_config.get("host") or os.environ.get("DATABRICKS_HOST")
    host = _get_user_input(
        "Databricks workspace URL (e.g., https://xxx.cloud.databricks.com)",
        default_host,
    )

    if not host:
        emit_error("Workspace URL is required")
        return "Databricks authentication cancelled - no workspace URL provided"

    # Ensure URL has https://
    if not host.startswith("http"):
        host = f"https://{host}"

    emit_info("")

    # Step 3: Test connection with OAuth U2M (external-browser)
    emit_info("Testing OAuth authentication...")
    emit_info("")
    emit_warning("IMPORTANT: A browser window should open automatically.")
    emit_info("If it doesn't open, please check:")
    emit_info("  1. Your default browser is running")
    emit_info("  2. No popup blockers are preventing the window")
    emit_info("  3. You have network access to Databricks")
    emit_info("")
    emit_info("The browser will ask you to log in with your corporate credentials.")
    emit_info("After successful login, return to this terminal.")
    emit_info("")

    if not _test_databricks_connection(host):
        return "Databricks authentication failed. Please check your workspace URL and try again."

    emit_info("")

    # Step 4: Get warehouse ID
    default_warehouse = existing_config.get("warehouse_id") or os.environ.get(
        "DATABRICKS_WAREHOUSE_ID"
    )
    warehouse_id = _get_user_input(
        "SQL Warehouse ID (from the list above, or leave empty to skip)",
        default_warehouse,
    )

    # Step 5: Get default catalog/schema (optional)
    default_catalog = existing_config.get("catalog") or os.environ.get(
        "DATABRICKS_CATALOG"
    )
    catalog = _get_user_input(
        "Default catalog (optional, e.g., 'main' or 'hive_metastore')",
        default_catalog,
    )

    default_schema = existing_config.get("schema") or os.environ.get(
        "DATABRICKS_SCHEMA"
    )
    schema = _get_user_input(
        "Default schema (optional, e.g., 'default')",
        default_schema,
    )

    # Step 6: Save configuration
    config = {
        "host": host,
        "auth_type": "external-browser",  # Use OAuth U2M browser-based auth
        "warehouse_id": warehouse_id or None,
        "catalog": catalog or None,
        "schema": schema or None,
    }

    if save_databricks_config(config):
        emit_success(f"Configuration saved to {config_path}")
    else:
        emit_warning("Failed to save configuration, but authentication succeeded")

    emit_info("")
    emit_success("=" * 60)
    emit_success("Databricks authentication successful!")
    emit_success("=" * 60)
    emit_info("")
    emit_info("You can now use Databricks tools:")
    emit_info("  - Switch to the Databricks agent: /agent databricks")
    emit_info("  - List catalogs, schemas, and tables")
    emit_info("  - Execute SQL queries on your data")
    emit_info("")
    emit_info("Note: OAuth tokens are managed automatically by the SDK.")
    emit_info("      You'll be prompted to re-authenticate when tokens expire.")

    return "Databricks authentication successful!"


def get_databricks_auth_help() -> list[tuple[str, str]]:
    """Get help information for Databricks authentication.

    Returns:
        List of (command_name, description) tuples
    """
    return [
        ("databricks_auth", "Authenticate with Databricks using OAuth (user credentials)"),
    ]
