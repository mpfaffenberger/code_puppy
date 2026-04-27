"""Azure AI Foundry Plugin callbacks for Code Puppy CLI.

This plugin enables Code Puppy to use Anthropic Claude models hosted on
Microsoft Azure AI Foundry with Azure AD (Entra ID) authentication.

The plugin uses credentials from `az login` to authenticate, eliminating
the need for API keys.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from code_puppy.callbacks import register_callback
from code_puppy.command_line.utils import safe_input
from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning
from code_puppy.tools.command_runner import set_awaiting_user_input

from .config import (
    DEFAULT_DEPLOYMENT_NAMES,
    ENV_FOUNDRY_RESOURCE,
    get_foundry_resource,
    set_foundry_resource,
)
from .discovery import find_account, list_deployments
from .token import get_token_provider
from .utils import (
    add_discovered_models_to_config,
    add_foundry_models_to_config,
    get_foundry_models_from_config,
    remove_foundry_models_from_config,
    resolve_env_var,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Slash Command Handlers
# ============================================================================


def _handle_foundry_status() -> None:
    """Handle the /foundry-status command.

    Displays the current Azure AD authentication status and configured
    Foundry models.
    """
    emit_info("")
    emit_info("Azure AI Foundry Status")
    emit_info("=" * 40)

    # Check Azure AD authentication
    token_provider = get_token_provider()
    is_auth, status_msg, user_info = token_provider.check_auth_status()

    if is_auth:
        emit_success(f"Authentication: {status_msg}")
        if user_info:
            emit_info(f"   Logged in as: {user_info}")
    else:
        emit_warning(f"Authentication: {status_msg}")

    # List configured models and check resource
    foundry_models = get_foundry_models_from_config()

    # Check resource - from env var or from configured models
    resource = get_foundry_resource()
    if not resource and foundry_models:
        # Get resource from first configured model
        first_model = next(iter(foundry_models.values()))
        resource = first_model.get("foundry_resource", "")
        if resource.startswith("$"):
            resource = None  # It's an unresolved env var reference

    emit_info("")
    if resource:
        emit_info(f"Foundry Resource: {resource}")
    else:
        emit_warning(
            f"Foundry Resource: Not set "
            f"(run /foundry-setup or set {ENV_FOUNDRY_RESOURCE})"
        )

    emit_info("")
    if foundry_models:
        emit_info(f"Configured Models ({len(foundry_models)}):")
        for model_key, config in foundry_models.items():
            deployment = config.get("name", "unknown")
            emit_info(f"   - {model_key}: {deployment}")
    else:
        emit_info("Configured Models: None")
        emit_info("   Run /foundry-setup to configure models")

    emit_info("")


def _handle_foundry_setup() -> None:
    """Handle the /foundry-setup command.

    Interactive wizard to configure Azure Foundry models.
    Uses print() for synchronous output to avoid message bus buffering issues.
    """

    def _print(msg: str = "") -> None:
        """Print with immediate flush."""
        print(msg, flush=True)

    _print()
    _print("Azure AI Foundry Setup")
    _print("=" * 40)
    _print()

    # Check Azure CLI authentication first
    _print("Step 1: Checking Azure CLI authentication...")
    token_provider = get_token_provider()
    is_auth, status_msg, user_info = token_provider.check_auth_status()

    if not is_auth:
        _print(f"   ERROR: {status_msg}")
        _print()
        _print("Please run 'az login' first, then try again.")
        return

    _print(f"   OK: {status_msg}")
    if user_info:
        _print(f"   User: {user_info}")
    _print()

    # Get resource name
    _print("Step 2: Azure Resource Name")
    current_resource = get_foundry_resource()
    if current_resource:
        _print(f"   Current: {current_resource}")

    resource_prompt = "   Enter resource name"
    if current_resource:
        resource_prompt += f" [{current_resource}]"
    resource_prompt += ": "

    set_awaiting_user_input(True)
    try:
        sys.stdout.flush()
        resource_input = safe_input(resource_prompt).strip()
        resource_name = resource_input if resource_input else current_resource

        if not resource_name:
            _print("   ERROR: Resource name is required.")
            return

        _print()

        # Step 3: Try auto-discovery, fall back to manual
        _print("Step 3: Discovering deployments...")
        account = find_account(resource_name)

        if account:
            _print(f"   Found: {account.name} ({account.location})")
            _print(f"   RG: {account.resource_group}")
            _print()

            deployments = list_deployments(account)
            succeeded = [d for d in deployments if d.provisioning_state == "Succeeded"]

            if succeeded:
                _print(f"   {len(succeeded)} active deployment(s):")
                for d in succeeded:
                    _print(f"   - {d.name} ({d.model_format}: {d.model_name})")
                _print()

                sys.stdout.flush()
                confirm = safe_input("   Configure these? [Y/n]: ").strip().lower()
                if confirm not in ("", "y", "yes"):
                    _print("   Skipped.")
                    return
            else:
                _print("   No active deployments found.")
                return
        else:
            _print("   Discovery failed — falling back to manual entry.")
            _print()
            succeeded = None

    except (KeyboardInterrupt, EOFError):
        _print()
        _print("Setup cancelled.")
        return
    finally:
        set_awaiting_user_input(False)

    _print()

    # Step 4: Save configuration
    _print("Step 4: Saving configuration...")

    # Persist the resource name so the next run pre-populates it.
    # (Env var still wins at lookup time if the user sets one explicitly.)
    try:
        set_foundry_resource(resource_name)
        _print(f"   Saved resource '{resource_name}' to puppy.cfg")
    except Exception as e:
        logger.warning("Failed to persist foundry resource to puppy.cfg: %s", e)
        _print(
            f"   Warning: could not save to puppy.cfg "
            f"(set {ENV_FOUNDRY_RESOURCE}={resource_name} to persist)"
        )

    if succeeded is not None:
        # Auto-discovered — configure all succeeded deployments
        added_models = add_discovered_models_to_config(resource_name, succeeded)
    else:
        # Manual fallback — use hardcoded Anthropic defaults
        added_models = add_foundry_models_to_config(
            resource_name=resource_name,
            opus_deployment=DEFAULT_DEPLOYMENT_NAMES["opus"],
            sonnet_deployment=DEFAULT_DEPLOYMENT_NAMES["sonnet"],
            haiku_deployment=DEFAULT_DEPLOYMENT_NAMES["haiku"],
        )

    _print()
    if added_models:
        _print(f"OK: Configured {len(added_models)} model(s):")
        for model_key in added_models:
            _print(f"   - {model_key}")
        _print()
        _print(f"Use '/model {added_models[0]}' to switch to a Foundry model.")
    else:
        _print("WARNING: No models were added. Check the configuration.")

    _print()


def _handle_foundry_remove() -> None:
    """Handle the /foundry-remove command.

    Removes all Azure Foundry model configurations.
    """
    removed = remove_foundry_models_from_config()
    if removed:
        emit_success(f"Removed {len(removed)} Foundry model(s):")
        for model_key in removed:
            emit_info(f"   - {model_key}")
    else:
        emit_info("No Foundry models found in configuration.")


# ============================================================================
# Custom Command Registration
# ============================================================================


def _custom_help() -> list[tuple[str, str]]:
    """Return help entries for custom commands."""
    return [
        (
            "foundry-status",
            "Check Azure AI Foundry authentication and configuration status",
        ),
        ("foundry-setup", "Interactive wizard to configure Azure Foundry models"),
        ("foundry-remove", "Remove all Azure Foundry model configurations"),
    ]


def _handle_custom_command(command: str, name: str) -> bool | None:
    """Handle custom slash commands for the Azure Foundry plugin.

    Dispatches to handlers for "foundry-status", "foundry-setup", and
    "foundry-remove" commands.

    Args:
        command: The full command string.
        name: The command name (without slash).

    Returns:
        True if the command was handled successfully.
        False if the command was recognized but handler() raised an exception.
        None if the command is not handled by this plugin.
    """
    handlers = {
        "foundry-status": _handle_foundry_status,
        "foundry-setup": _handle_foundry_setup,
        "foundry-remove": _handle_foundry_remove,
    }

    handler = handlers.get(name)
    if handler is None:
        return None

    try:
        handler()
        return True
    except Exception as e:
        logger.exception("Error handling /%s command: %s", name, e)
        emit_error(f"Command /{name} failed: {e}")
        return False


# ============================================================================
# Model Type Handler
# ============================================================================


def _create_azure_foundry_model(
    model_name: str, model_config: dict, config: dict
) -> Any:
    """Create an Azure Foundry model instance.

    This handler is registered via the 'register_model_type' callback to handle
    models with type='azure_foundry'.

    Args:
        model_name: The model key name (e.g., 'foundry-claude-opus').
        model_config: The model configuration dictionary.
        config: The full models configuration.

    Returns:
        An AnthropicModel instance configured for Azure Foundry, or None on error.
    """
    try:
        from anthropic import AsyncAnthropicFoundry
        from pydantic_ai.models.anthropic import AnthropicModel
    except ImportError as e:
        emit_error(
            f"Failed to create Azure Foundry model '{model_name}': "
            f"Missing dependency - {e}"
        )
        return None

    from code_puppy.claude_cache_client import patch_anthropic_client_messages
    from code_puppy.config import get_effective_model_settings
    from code_puppy.model_factory import CONTEXT_1M_BETA
    from code_puppy.provider_identity import (
        make_anthropic_provider,
        resolve_provider_identity,
    )

    # Get the Foundry resource name
    resource_config = model_config.get("foundry_resource", f"${ENV_FOUNDRY_RESOURCE}")
    resource_name = resolve_env_var(resource_config)

    if not resource_name:
        emit_warning(
            f"Azure Foundry resource not configured for model '{model_name}'. "
            f"Set {ENV_FOUNDRY_RESOURCE} or run /foundry-setup."
        )
        return None

    # Get the deployment name (model name in Azure)
    deployment_name = model_config.get("name")
    if not deployment_name:
        emit_warning(f"Deployment name not specified for model '{model_name}'.")
        return None

    # Get the token provider
    token_provider = get_token_provider()

    # Check authentication status
    is_auth, status_msg, _ = token_provider.check_auth_status()
    if not is_auth:
        emit_warning(
            f"Azure AD authentication failed for model '{model_name}': {status_msg}"
        )
        return None

    try:
        # Check for interleaved thinking setting (default True for Foundry models)
        effective_settings = get_effective_model_settings(model_name)
        interleaved_thinking = effective_settings.get("interleaved_thinking", True)

        # Build anthropic-beta header if needed
        beta_parts: list[str] = []
        if interleaved_thinking:
            beta_parts.append("interleaved-thinking-2025-05-14")

        # Add 1M context beta header for long-context models
        context_length = model_config.get("context_length", 200000)
        if context_length >= 1_000_000:
            beta_parts.append(CONTEXT_1M_BETA)

        # Build default headers dict if we have beta features
        default_headers: dict[str, str] | None = None
        if beta_parts:
            default_headers = {"anthropic-beta": ",".join(beta_parts)}

        # Create the Azure Foundry Anthropic client with token provider
        # Note: We pass default_headers here because AsyncAnthropicFoundry.with_options()
        # has a bug where copy() passes auth_token which isn't a valid __init__ param
        anthropic_client = AsyncAnthropicFoundry(
            resource=resource_name,
            azure_ad_token_provider=token_provider.get_token,
            default_headers=default_headers,
        )

        # Patch for cache control injection
        patch_anthropic_client_messages(anthropic_client)

        # Create the pydantic-ai provider and model
        provider_identity = resolve_provider_identity(model_name, model_config)
        provider = make_anthropic_provider(
            provider_identity,
            anthropic_client=anthropic_client,
        )

        model = AnthropicModel(model_name=deployment_name, provider=provider)
        logger.info(
            "Created Azure Foundry model: %s -> %s @ %s",
            model_name,
            deployment_name,
            resource_name,
        )
        return model

    except Exception as e:
        emit_error(f"Failed to create Azure Foundry model '{model_name}': {e}")
        logger.exception(f"Error creating Azure Foundry model: {e}")
        return None


def _create_azure_foundry_openai_model(
    model_name: str, model_config: dict, config: dict
) -> Any:
    """Create an Azure Foundry OpenAI model instance.

    Handles models with type='azure_foundry_openai' — OpenAI models on
    Azure AI Services using Azure AD token auth (no API keys).
    """
    try:
        from openai import AsyncAzureOpenAI
        from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
    except ImportError as e:
        emit_error(f"Failed to create Azure Foundry OpenAI model '{model_name}': {e}")
        return None

    from code_puppy.provider_identity import (
        make_openai_provider,
        resolve_provider_identity,
    )

    resource_config = model_config.get("foundry_resource", f"${ENV_FOUNDRY_RESOURCE}")
    resource_name = resolve_env_var(resource_config)

    if not resource_name:
        emit_warning(
            f"Azure Foundry resource not configured for model '{model_name}'. "
            f"Set {ENV_FOUNDRY_RESOURCE} or run /foundry-setup."
        )
        return None

    deployment_name = model_config.get("name")
    if not deployment_name:
        emit_warning(f"Deployment name not specified for model '{model_name}'.")
        return None

    token_provider = get_token_provider()
    is_auth, status_msg, _ = token_provider.check_auth_status()
    if not is_auth:
        emit_warning(f"Azure AD auth failed for model '{model_name}': {status_msg}")
        return None

    try:
        api_version = model_config.get("api_version", "2025-04-01-preview")
        azure_endpoint = f"https://{resource_name}.openai.azure.com"

        azure_client = AsyncAzureOpenAI(
            azure_endpoint=azure_endpoint,
            api_version=api_version,
            azure_ad_token_provider=token_provider.get_token,
        )

        provider_identity = resolve_provider_identity(model_name, model_config)
        provider = make_openai_provider(provider_identity, openai_client=azure_client)

        if deployment_name.startswith("gpt-5"):
            model = OpenAIResponsesModel(model_name=deployment_name, provider=provider)
        else:
            model = OpenAIChatModel(model_name=deployment_name, provider=provider)
        logger.info(
            "Created Azure Foundry OpenAI model: %s -> %s @ %s",
            model_name,
            deployment_name,
            resource_name,
        )
        return model

    except Exception as e:
        emit_error(f"Failed to create Azure Foundry OpenAI model '{model_name}': {e}")
        logger.exception("Error creating Azure Foundry OpenAI model: %s", e)
        return None


def _register_model_types() -> list[dict[str, Any]]:
    """Register azure_foundry and azure_foundry_openai model type handlers."""
    return [
        {"type": "azure_foundry", "handler": _create_azure_foundry_model},
        {"type": "azure_foundry_openai", "handler": _create_azure_foundry_openai_model},
    ]


# ============================================================================
# Callback Registration
# ============================================================================

# Register all callbacks when this module is imported
register_callback("custom_command_help", _custom_help)
register_callback("custom_command", _handle_custom_command)
register_callback("register_model_type", _register_model_types)
