"""AWS Bedrock Plugin callbacks for Code Puppy CLI.

This plugin enables Code Puppy to use Anthropic Claude models hosted on
AWS Bedrock with standard AWS credential chain authentication.
"""

from __future__ import annotations

import logging
from typing import Any

from code_puppy.callbacks import register_callback
from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

from .config import (
    get_aws_profile,
    get_bedrock_region,
)
from .utils import (
    add_bedrock_models_to_config,
    get_bedrock_models_from_config,
    remove_bedrock_models_from_config,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Slash Command Handlers
# ============================================================================


def _handle_bedrock_status() -> None:
    """Handle the /bedrock-status command."""
    emit_info("")
    emit_info("AWS Bedrock Status")
    emit_info("=" * 40)

    region = get_bedrock_region()
    profile = get_aws_profile()

    emit_info(f"Region: {region}")
    if profile:
        emit_info(f"Profile: {profile}")
    else:
        emit_info("Profile: (default credential chain)")

    # Check AWS credentials
    try:
        import boto3

        session = boto3.Session(profile_name=profile, region_name=region)
        sts = session.client("sts")
        identity = sts.get_caller_identity()
        arn = identity.get("Arn", "unknown")
        emit_success(f"Authenticated: {arn}")
    except ImportError:
        emit_warning("boto3 not installed - cannot verify credentials")
    except Exception as e:
        emit_warning(f"Authentication: {e}")

    emit_info("")
    bedrock_models = get_bedrock_models_from_config()
    if bedrock_models:
        emit_info(f"Configured Models ({len(bedrock_models)}):")
        for model_key, config in bedrock_models.items():
            model_id = config.get("name", "unknown")
            emit_info(f"   - {model_key}: {model_id}")
    else:
        emit_info("Configured Models: None")
        emit_info("   Run /bedrock-setup to configure models")

    emit_info("")


def _handle_bedrock_setup() -> None:
    """Handle the /bedrock-setup command.

    Region and credentials auto-resolve from the AWS environment
    (IAM role, env vars, ~/.aws/config). No prompts needed.
    """

    added_models = add_bedrock_models_to_config(
        aws_region=get_bedrock_region(),
        aws_profile=get_aws_profile(),
    )

    if added_models:
        emit_success(f"Bedrock: added {len(added_models)} model(s):")
        for model_key in added_models:
            emit_info(f"   - {model_key}")

        from code_puppy.model_switching import set_model_and_reload_agent

        set_model_and_reload_agent("bedrock-opus-4-7")
        emit_info("Switched to bedrock-opus-4-7.")
    else:
        emit_warning("Bedrock: no models added — check configuration.")


def _handle_bedrock_remove() -> None:
    """Handle the /bedrock-remove command."""
    removed = remove_bedrock_models_from_config()
    if removed:
        emit_success(f"Removed {len(removed)} Bedrock model(s):")
        for model_key in removed:
            emit_info(f"   - {model_key}")
    else:
        emit_info("No Bedrock models found in configuration.")


# ============================================================================
# Custom Command Registration
# ============================================================================


def _custom_help() -> list[tuple[str, str]]:
    """Return help entries for custom commands."""
    return [
        ("bedrock-status", "Check AWS Bedrock authentication and configuration"),
        ("bedrock-setup", "Auto-configure Bedrock Claude models"),
        ("bedrock-remove", "Remove all Bedrock model configurations"),
    ]


def _handle_custom_command(command: str, name: str) -> bool | None:
    """Handle custom slash commands for the AWS Bedrock plugin."""
    handlers = {
        "bedrock-status": _handle_bedrock_status,
        "bedrock-setup": _handle_bedrock_setup,
        "bedrock-remove": _handle_bedrock_remove,
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
        return True


# ============================================================================
# Model Type Handler
# ============================================================================


def _create_aws_bedrock_model(model_name: str, model_config: dict, config: dict) -> Any:
    """Create an AWS Bedrock model instance.

    Uses AsyncAnthropicBedrock from the anthropic SDK with standard
    AWS credential chain (env vars, profiles, IAM roles, SSO).
    """
    try:
        from anthropic import AsyncAnthropicBedrock
        from pydantic_ai.models.anthropic import AnthropicModel
    except ImportError as e:
        emit_error(
            f"Failed to create Bedrock model '{model_name}': Missing dependency - {e}"
        )
        return None

    from code_puppy.claude_cache_client import patch_anthropic_client_messages
    from code_puppy.config import get_effective_model_settings
    from code_puppy.model_factory import CONTEXT_1M_BETA
    from code_puppy.provider_identity import (
        make_anthropic_provider,
        resolve_provider_identity,
    )

    model_id = model_config.get("name")
    if not model_id:
        emit_warning(f"Model ID not specified for '{model_name}'.")
        return None

    try:
        effective_settings = get_effective_model_settings(model_name)
        interleaved_thinking = effective_settings.get("interleaved_thinking", True)

        beta_parts: list[str] = []
        if interleaved_thinking:
            beta_parts.append("interleaved-thinking-2025-05-14")

        context_length = model_config.get("context_length", 200000)
        if context_length >= 1_000_000:
            beta_parts.append(CONTEXT_1M_BETA)

        default_headers: dict[str, str] | None = None
        if beta_parts:
            default_headers = {"anthropic-beta": ",".join(beta_parts)}

        client_kwargs: dict[str, Any] = {
            "aws_region": model_config.get("aws_region") or get_bedrock_region(),
        }

        aws_profile = model_config.get("aws_profile") or get_aws_profile()
        if aws_profile:
            client_kwargs["aws_profile"] = aws_profile

        if default_headers:
            client_kwargs["default_headers"] = default_headers

        anthropic_client = AsyncAnthropicBedrock(**client_kwargs)

        patch_anthropic_client_messages(anthropic_client)

        provider_identity = resolve_provider_identity(model_name, model_config)
        provider = make_anthropic_provider(
            provider_identity,
            anthropic_client=anthropic_client,
        )

        model = AnthropicModel(model_name=model_id, provider=provider)
        logger.info(
            "Created Bedrock model: %s -> %s @ %s",
            model_name,
            model_id,
            client_kwargs.get("aws_region", "auto"),
        )
        return model

    except Exception as e:
        emit_error(f"Failed to create Bedrock model '{model_name}': {e}")
        logger.exception("Error creating Bedrock model: %s", e)
        return None


def _register_model_types() -> list[dict[str, Any]]:
    """Register the aws_bedrock model type handler."""
    return [{"type": "aws_bedrock", "handler": _create_aws_bedrock_model}]


# ============================================================================
# Callback Registration
# ============================================================================

register_callback("custom_command_help", _custom_help)
register_callback("custom_command", _handle_custom_command)
register_callback("register_model_type", _register_model_types)
