import json
import logging
import os
import pathlib
from typing import Any, Dict

import httpx
from anthropic import AsyncAnthropic
from openai import AsyncAzureOpenAI
from pydantic_ai.models.anthropic import AnthropicModel, AnthropicModelSettings
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import (
    OpenAIChatModel,
    OpenAIChatModelSettings,
    OpenAIResponsesModel,
)
from pydantic_ai.profiles import ModelProfile
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.cerebras import CerebrasProvider
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider
from pydantic_ai.settings import ModelSettings

from code_puppy.messaging import emit_warning

from . import callbacks
from .claude_cache_client import ClaudeCacheAsyncClient, patch_anthropic_client_messages
from .config import EXTRA_MODELS_FILE, get_value
from .http_utils import create_async_client, get_cert_bundle_path, get_http2
from .round_robin_model import RoundRobinModel


def get_api_key(env_var_name: str) -> str | None:
    """Get an API key from config first, then fall back to environment variable.

    This allows users to set API keys via `/set KIMI_API_KEY=xxx` in addition to
    setting them as environment variables.

    Args:
        env_var_name: The name of the environment variable (e.g., "OPENAI_API_KEY")

    Returns:
        The API key value, or None if not found in either config or environment.
    """
    # First check config (case-insensitive key lookup)
    config_value = get_value(env_var_name.lower())
    if config_value:
        return config_value

    # Fall back to environment variable
    return os.environ.get(env_var_name)


def make_model_settings(
    model_name: str, max_tokens: int | None = None
) -> ModelSettings:
    """Create appropriate ModelSettings for a given model.

    This handles model-specific settings:
    - GPT-5 models: reasoning_effort and verbosity (non-codex only)
    - Claude/Anthropic models: extended_thinking and budget_tokens
    - Automatic max_tokens calculation based on model context length

    Args:
        model_name: The name of the model to create settings for.
        max_tokens: Optional max tokens limit. If None, automatically calculated
            as: max(2048, min(15% of context_length, 65536))

    Returns:
        Appropriate ModelSettings subclass instance for the model.
    """
    from code_puppy.config import (
        get_effective_model_settings,
        get_openai_reasoning_effort,
        get_openai_verbosity,
    )

    model_settings_dict: dict = {}

    # Calculate max_tokens if not explicitly provided
    if max_tokens is None:
        # Load model config to get context length
        try:
            models_config = ModelFactory.load_config()
            model_config = models_config.get(model_name, {})
            context_length = model_config.get("context_length", 128000)
        except Exception:
            # Fallback if config loading fails (e.g., in CI environments)
            context_length = 128000
        # min 2048, 15% of context, max 65536
        max_tokens = max(2048, min(int(0.15 * context_length), 65536))

    model_settings_dict["max_tokens"] = max_tokens
    effective_settings = get_effective_model_settings(model_name)
    model_settings_dict.update(effective_settings)

    model_settings: ModelSettings = ModelSettings(**model_settings_dict)

    if "gpt-5" in model_name:
        model_settings_dict["openai_reasoning_effort"] = get_openai_reasoning_effort()
        # Verbosity only applies to non-codex GPT-5 models (codex only supports "medium")
        if "codex" not in model_name:
            verbosity = get_openai_verbosity()
            model_settings_dict["extra_body"] = {"verbosity": verbosity}
        model_settings = OpenAIChatModelSettings(**model_settings_dict)
    elif model_name.startswith("claude-") or model_name.startswith("anthropic-"):
        # Handle Anthropic extended thinking settings
        # Remove top_p as Anthropic doesn't support it with extended thinking
        model_settings_dict.pop("top_p", None)

        # Claude extended thinking requires temperature=1.0 (API restriction)
        # Default to 1.0 if not explicitly set by user
        if model_settings_dict.get("temperature") is None:
            model_settings_dict["temperature"] = 1.0

        extended_thinking = effective_settings.get("extended_thinking", True)
        budget_tokens = effective_settings.get("budget_tokens", 10000)
        if extended_thinking and budget_tokens:
            model_settings_dict["anthropic_thinking"] = {
                "type": "enabled",
                "budget_tokens": budget_tokens,
            }
        model_settings = AnthropicModelSettings(**model_settings_dict)

    return model_settings


class ZaiChatModel(OpenAIChatModel):
    def _process_response(self, response):
        response.object = "chat.completion"
        return super()._process_response(response)


def get_custom_config(model_config):
    custom_config = model_config.get("custom_endpoint", {})
    if not custom_config:
        raise ValueError("Custom model requires 'custom_endpoint' configuration")

    url = custom_config.get("url")
    if not url:
        raise ValueError("Custom endpoint requires 'url' field")

    headers = {}
    for key, value in custom_config.get("headers", {}).items():
        if value.startswith("$"):
            env_var_name = value[1:]
            resolved_value = get_api_key(env_var_name)
            if resolved_value is None:
                emit_warning(
                    f"'{env_var_name}' is not set (check config or environment) for custom endpoint header '{key}'. Proceeding with empty value."
                )
                resolved_value = ""
            value = resolved_value
        elif "$" in value:
            tokens = value.split(" ")
            resolved_values = []
            for token in tokens:
                if token.startswith("$"):
                    env_var = token[1:]
                    resolved_value = get_api_key(env_var)
                    if resolved_value is None:
                        emit_warning(
                            f"'{env_var}' is not set (check config or environment) for custom endpoint header '{key}'. Proceeding with empty value."
                        )
                        resolved_values.append("")
                    else:
                        resolved_values.append(resolved_value)
                else:
                    resolved_values.append(token)
            value = " ".join(resolved_values)
        headers[key] = value
    api_key = None
    if "api_key" in custom_config:
        if custom_config["api_key"].startswith("$"):
            env_var_name = custom_config["api_key"][1:]
            api_key = get_api_key(env_var_name)
            if api_key is None:
                emit_warning(
                    f"API key '{env_var_name}' is not set (checked config and environment); proceeding without API key."
                )
        else:
            api_key = custom_config["api_key"]
    if "ca_certs_path" in custom_config:
        verify = custom_config["ca_certs_path"]
    else:
        verify = None
    return url, headers, verify, api_key


class ModelFactory:
    """A factory for creating and managing different AI models."""

    @staticmethod
    def load_config() -> Dict[str, Any]:
        load_model_config_callbacks = callbacks.get_callbacks("load_model_config")
        if len(load_model_config_callbacks) > 0:
            if len(load_model_config_callbacks) > 1:
                logging.getLogger(__name__).warning(
                    "Multiple load_model_config callbacks registered, using the first"
                )
            config = callbacks.on_load_model_config()[0]
        else:
            from code_puppy.config import MODELS_FILE

            with open(pathlib.Path(__file__).parent / "models.json", "r") as src:
                with open(pathlib.Path(MODELS_FILE), "w") as target:
                    target.write(src.read())

            with open(MODELS_FILE, "r") as f:
                config = json.load(f)

        # Import OAuth model file paths from main config
        from code_puppy.config import (
            CHATGPT_MODELS_FILE,
            CLAUDE_MODELS_FILE,
            GEMINI_MODELS_FILE,
        )

        # Build list of extra model sources
        extra_sources: list[tuple[pathlib.Path, str, bool]] = [
            (pathlib.Path(EXTRA_MODELS_FILE), "extra models", False),
            (pathlib.Path(CHATGPT_MODELS_FILE), "ChatGPT OAuth models", False),
            (pathlib.Path(CLAUDE_MODELS_FILE), "Claude Code OAuth models", True),
            (pathlib.Path(GEMINI_MODELS_FILE), "Gemini OAuth models", False),
        ]

        for source_path, label, use_filtered in extra_sources:
            if not source_path.exists():
                continue
            try:
                # Use filtered loading for Claude Code OAuth models to show only latest versions
                if use_filtered:
                    try:
                        from code_puppy.plugins.claude_code_oauth.utils import (
                            load_claude_models_filtered,
                        )

                        extra_config = load_claude_models_filtered()
                    except ImportError:
                        # Plugin not available, fall back to standard JSON loading
                        logging.getLogger(__name__).debug(
                            f"claude_code_oauth plugin not available, loading {label} as plain JSON"
                        )
                        with open(source_path, "r") as f:
                            extra_config = json.load(f)
                else:
                    with open(source_path, "r") as f:
                        extra_config = json.load(f)
                config.update(extra_config)
            except json.JSONDecodeError as exc:
                logging.getLogger(__name__).warning(
                    f"Failed to load {label} config from {source_path}: Invalid JSON - {exc}"
                )
            except Exception as exc:
                logging.getLogger(__name__).warning(
                    f"Failed to load {label} config from {source_path}: {exc}"
                )
        return config

    @staticmethod
    def get_model(model_name: str, config: Dict[str, Any]) -> Any:
        """Returns a configured model instance based on the provided name and config.

        API key validation happens naturally within each model type's initialization,
        which emits warnings and returns None if keys are missing.
        """
        model_config = config.get(model_name)
        if not model_config:
            raise ValueError(f"Model '{model_name}' not found in configuration.")

        model_type = model_config.get("type")

        if model_type == "gemini":
            api_key = get_api_key("GEMINI_API_KEY")
            if not api_key:
                emit_warning(
                    f"GEMINI_API_KEY is not set (check config or environment); skipping Gemini model '{model_config.get('name')}'."
                )
                return None

            provider = GoogleProvider(api_key=api_key)
            model = GoogleModel(model_name=model_config["name"], provider=provider)
            setattr(model, "provider", provider)
            return model

        elif model_type == "openai":
            api_key = get_api_key("OPENAI_API_KEY")
            if not api_key:
                emit_warning(
                    f"OPENAI_API_KEY is not set (check config or environment); skipping OpenAI model '{model_config.get('name')}'."
                )
                return None

            provider = OpenAIProvider(api_key=api_key)
            model = OpenAIChatModel(model_name=model_config["name"], provider=provider)
            if "codex" in model_name:
                model = OpenAIResponsesModel(
                    model_name=model_config["name"], provider=provider
                )
            setattr(model, "provider", provider)
            return model

        elif model_type == "anthropic":
            api_key = get_api_key("ANTHROPIC_API_KEY")
            if not api_key:
                emit_warning(
                    f"ANTHROPIC_API_KEY is not set (check config or environment); skipping Anthropic model '{model_config.get('name')}'."
                )
                return None

            # Use the same caching client as claude_code models
            verify = get_cert_bundle_path()
            http2_enabled = get_http2()

            client = ClaudeCacheAsyncClient(
                verify=verify,
                timeout=180,
                http2=http2_enabled,
            )

            # Check if interleaved thinking is enabled for this model
            # Only applies to Claude 4 models (Opus 4.5, Opus 4.1, Opus 4, Sonnet 4)
            from code_puppy.config import get_effective_model_settings

            effective_settings = get_effective_model_settings(model_name)
            interleaved_thinking = effective_settings.get("interleaved_thinking", False)

            default_headers = {}
            if interleaved_thinking:
                default_headers["anthropic-beta"] = "interleaved-thinking-2025-05-14"

            anthropic_client = AsyncAnthropic(
                api_key=api_key,
                http_client=client,
                default_headers=default_headers if default_headers else None,
            )

            # Ensure cache_control is injected at the Anthropic SDK layer
            patch_anthropic_client_messages(anthropic_client)

            provider = AnthropicProvider(anthropic_client=anthropic_client)
            return AnthropicModel(model_name=model_config["name"], provider=provider)

        elif model_type == "custom_anthropic":
            url, headers, verify, api_key = get_custom_config(model_config)
            if not api_key:
                emit_warning(
                    f"API key is not set for custom Anthropic endpoint; skipping model '{model_config.get('name')}'."
                )
                return None

            # Use the same caching client as claude_code models
            if verify is None:
                verify = get_cert_bundle_path()

            http2_enabled = get_http2()

            client = ClaudeCacheAsyncClient(
                headers=headers,
                verify=verify,
                timeout=180,
                http2=http2_enabled,
            )

            # Check if interleaved thinking is enabled for this model
            from code_puppy.config import get_effective_model_settings

            effective_settings = get_effective_model_settings(model_name)
            interleaved_thinking = effective_settings.get("interleaved_thinking", False)

            default_headers = {}
            if interleaved_thinking:
                default_headers["anthropic-beta"] = "interleaved-thinking-2025-05-14"

            anthropic_client = AsyncAnthropic(
                base_url=url,
                http_client=client,
                api_key=api_key,
                default_headers=default_headers if default_headers else None,
            )

            # Ensure cache_control is injected at the Anthropic SDK layer
            patch_anthropic_client_messages(anthropic_client)

            provider = AnthropicProvider(anthropic_client=anthropic_client)
            return AnthropicModel(model_name=model_config["name"], provider=provider)
        elif model_type == "claude_code":
            url, headers, verify, api_key = get_custom_config(model_config)
            if not api_key:
                emit_warning(
                    f"API key is not set for Claude Code endpoint; skipping model '{model_config.get('name')}'."
                )
                return None

            # Check if interleaved thinking is enabled (defaults to True for OAuth models)
            from code_puppy.config import get_effective_model_settings

            effective_settings = get_effective_model_settings(model_name)
            interleaved_thinking = effective_settings.get("interleaved_thinking", True)

            # Handle anthropic-beta header based on interleaved_thinking setting
            if "anthropic-beta" in headers:
                beta_parts = [p.strip() for p in headers["anthropic-beta"].split(",")]
                if interleaved_thinking:
                    # Ensure interleaved-thinking is in the header
                    if "interleaved-thinking-2025-05-14" not in beta_parts:
                        beta_parts.append("interleaved-thinking-2025-05-14")
                else:
                    # Remove interleaved-thinking from the header
                    beta_parts = [
                        p for p in beta_parts if "interleaved-thinking" not in p
                    ]
                headers["anthropic-beta"] = ",".join(beta_parts) if beta_parts else None
                if headers.get("anthropic-beta") is None:
                    del headers["anthropic-beta"]
            elif interleaved_thinking:
                # No existing beta header, add one for interleaved thinking
                headers["anthropic-beta"] = "interleaved-thinking-2025-05-14"

            # Use a dedicated client wrapper that injects cache_control on /v1/messages
            if verify is None:
                verify = get_cert_bundle_path()

            http2_enabled = get_http2()

            client = ClaudeCacheAsyncClient(
                headers=headers,
                verify=verify,
                timeout=180,
                http2=http2_enabled,
            )

            anthropic_client = AsyncAnthropic(
                base_url=url,
                http_client=client,
                auth_token=api_key,
            )
            # Ensure cache_control is injected at the Anthropic SDK layer too
            # so we don't depend solely on httpx internals.
            patch_anthropic_client_messages(anthropic_client)
            anthropic_client.api_key = None
            anthropic_client.auth_token = api_key
            provider = AnthropicProvider(anthropic_client=anthropic_client)
            return AnthropicModel(model_name=model_config["name"], provider=provider)
        elif model_type == "azure_openai":
            azure_endpoint_config = model_config.get("azure_endpoint")
            if not azure_endpoint_config:
                raise ValueError(
                    "Azure OpenAI model type requires 'azure_endpoint' in its configuration."
                )
            azure_endpoint = azure_endpoint_config
            if azure_endpoint_config.startswith("$"):
                azure_endpoint = get_api_key(azure_endpoint_config[1:])
            if not azure_endpoint:
                emit_warning(
                    f"Azure OpenAI endpoint '{azure_endpoint_config[1:] if azure_endpoint_config.startswith('$') else azure_endpoint_config}' not found (check config or environment); skipping model '{model_config.get('name')}'."
                )
                return None

            api_version_config = model_config.get("api_version")
            if not api_version_config:
                raise ValueError(
                    "Azure OpenAI model type requires 'api_version' in its configuration."
                )
            api_version = api_version_config
            if api_version_config.startswith("$"):
                api_version = get_api_key(api_version_config[1:])
            if not api_version:
                emit_warning(
                    f"Azure OpenAI API version '{api_version_config[1:] if api_version_config.startswith('$') else api_version_config}' not found (check config or environment); skipping model '{model_config.get('name')}'."
                )
                return None

            api_key_config = model_config.get("api_key")
            if not api_key_config:
                raise ValueError(
                    "Azure OpenAI model type requires 'api_key' in its configuration."
                )
            api_key = api_key_config
            if api_key_config.startswith("$"):
                api_key = get_api_key(api_key_config[1:])
            if not api_key:
                emit_warning(
                    f"Azure OpenAI API key '{api_key_config[1:] if api_key_config.startswith('$') else api_key_config}' not found (check config or environment); skipping model '{model_config.get('name')}'."
                )
                return None

            # Configure max_retries for the Azure client, defaulting if not specified in config
            azure_max_retries = model_config.get("max_retries", 2)

            azure_client = AsyncAzureOpenAI(
                azure_endpoint=azure_endpoint,
                api_version=api_version,
                api_key=api_key,
                max_retries=azure_max_retries,
            )
            provider = OpenAIProvider(openai_client=azure_client)
            model = OpenAIChatModel(model_name=model_config["name"], provider=provider)
            setattr(model, "provider", provider)
            return model

        elif model_type == "custom_openai":
            url, headers, verify, api_key = get_custom_config(model_config)
            client = create_async_client(headers=headers, verify=verify)
            provider_args = dict(
                base_url=url,
                http_client=client,
            )
            if api_key:
                provider_args["api_key"] = api_key
            provider = OpenAIProvider(**provider_args)
            model = OpenAIChatModel(model_name=model_config["name"], provider=provider)
            if model_name == "chatgpt-gpt-5-codex":
                model = OpenAIResponsesModel(model_config["name"], provider=provider)
            setattr(model, "provider", provider)
            return model
        elif model_type == "zai_coding":
            api_key = get_api_key("ZAI_API_KEY")
            if not api_key:
                emit_warning(
                    f"ZAI_API_KEY is not set (check config or environment); skipping ZAI coding model '{model_config.get('name')}'."
                )
                return None
            provider = OpenAIProvider(
                api_key=api_key,
                base_url="https://api.z.ai/api/coding/paas/v4",
            )
            zai_model = ZaiChatModel(
                model_name=model_config["name"],
                provider=provider,
            )
            setattr(zai_model, "provider", provider)
            return zai_model
        elif model_type == "zai_api":
            api_key = get_api_key("ZAI_API_KEY")
            if not api_key:
                emit_warning(
                    f"ZAI_API_KEY is not set (check config or environment); skipping ZAI API model '{model_config.get('name')}'."
                )
                return None
            provider = OpenAIProvider(
                api_key=api_key,
                base_url="https://api.z.ai/api/paas/v4/",
            )
            zai_model = ZaiChatModel(
                model_name=model_config["name"],
                provider=provider,
            )
            setattr(zai_model, "provider", provider)
            return zai_model
        elif model_type == "custom_gemini":
            url, headers, verify, api_key = get_custom_config(model_config)
            if not api_key:
                emit_warning(
                    f"API key is not set for custom Gemini endpoint; skipping model '{model_config.get('name')}'."
                )
                return None
            os.environ["GEMINI_API_KEY"] = api_key

            class CustomGoogleGLAProvider(GoogleProvider):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)

                @property
                def base_url(self):
                    return url

                @property
                def client(self) -> httpx.AsyncClient:
                    _client = create_async_client(headers=headers, verify=verify)
                    _client.base_url = self.base_url
                    return _client

            google_gla = CustomGoogleGLAProvider(api_key=api_key)
            model = GoogleModel(model_name=model_config["name"], provider=google_gla)
            return model
        elif model_type == "cerebras":

            class ZaiCerebrasProvider(CerebrasProvider):
                def model_profile(self, model_name: str) -> ModelProfile | None:
                    profile = super().model_profile(model_name)
                    if model_name.startswith("zai"):
                        from pydantic_ai.profiles.qwen import qwen_model_profile

                        profile = profile.update(qwen_model_profile("qwen-3-coder"))
                    return profile

            url, headers, verify, api_key = get_custom_config(model_config)
            if not api_key:
                emit_warning(
                    f"API key is not set for Cerebras endpoint; skipping model '{model_config.get('name')}'."
                )
                return None
            client = create_async_client(headers=headers, verify=verify)
            provider_args = dict(
                api_key=api_key,
                http_client=client,
            )
            provider = ZaiCerebrasProvider(**provider_args)

            model = OpenAIChatModel(model_name=model_config["name"], provider=provider)
            setattr(model, "provider", provider)
            return model

        elif model_type == "openrouter":
            # Get API key from config, which can be an environment variable reference or raw value
            api_key_config = model_config.get("api_key")
            api_key = None

            if api_key_config:
                if api_key_config.startswith("$"):
                    # It's an environment variable reference
                    env_var_name = api_key_config[1:]  # Remove the $ prefix
                    api_key = get_api_key(env_var_name)
                    if api_key is None:
                        emit_warning(
                            f"OpenRouter API key '{env_var_name}' not found (check config or environment); skipping model '{model_config.get('name')}'."
                        )
                        return None
                else:
                    # It's a raw API key value
                    api_key = api_key_config
            else:
                # No API key in config, try to get it from config or the default environment variable
                api_key = get_api_key("OPENROUTER_API_KEY")
                if api_key is None:
                    emit_warning(
                        f"OPENROUTER_API_KEY is not set (check config or environment); skipping OpenRouter model '{model_config.get('name')}'."
                    )
                    return None

            provider = OpenRouterProvider(api_key=api_key)

            model = OpenAIChatModel(model_name=model_config["name"], provider=provider)
            setattr(model, "provider", provider)
            return model

        elif model_type == "gemini_oauth":
            # Gemini OAuth models use the Code Assist API (cloudcode-pa.googleapis.com)
            # This is a different API than the standard Generative Language API
            try:
                # Try user plugin first, then built-in plugin
                try:
                    from gemini_oauth.config import GEMINI_OAUTH_CONFIG
                    from gemini_oauth.utils import (
                        get_project_id,
                        get_valid_access_token,
                    )
                except ImportError:
                    from code_puppy.plugins.gemini_oauth.config import (
                        GEMINI_OAUTH_CONFIG,
                    )
                    from code_puppy.plugins.gemini_oauth.utils import (
                        get_project_id,
                        get_valid_access_token,
                    )
            except ImportError as exc:
                emit_warning(
                    f"Gemini OAuth plugin not available; skipping model '{model_config.get('name')}'. "
                    f"Error: {exc}"
                )
                return None

            # Get a valid access token (refreshing if needed)
            access_token = get_valid_access_token()
            if not access_token:
                emit_warning(
                    f"Failed to get valid Gemini OAuth token; skipping model '{model_config.get('name')}'. "
                    "Run /gemini-auth to re-authenticate."
                )
                return None

            # Get project ID from stored tokens
            project_id = get_project_id()
            if not project_id:
                emit_warning(
                    f"No Code Assist project ID found; skipping model '{model_config.get('name')}'. "
                    "Run /gemini-auth to re-authenticate."
                )
                return None

            # Import the Code Assist model wrapper
            from code_puppy.gemini_code_assist import GeminiCodeAssistModel

            # Create the Code Assist model
            model = GeminiCodeAssistModel(
                model_name=model_config["name"],
                access_token=access_token,
                project_id=project_id,
                api_base_url=GEMINI_OAUTH_CONFIG["api_base_url"],
                api_version=GEMINI_OAUTH_CONFIG["api_version"],
            )
            return model

        elif model_type == "chatgpt_oauth":
            # ChatGPT OAuth models use the Codex API at chatgpt.com
            try:
                try:
                    from chatgpt_oauth.config import CHATGPT_OAUTH_CONFIG
                    from chatgpt_oauth.utils import (
                        get_valid_access_token,
                        load_stored_tokens,
                    )
                except ImportError:
                    from code_puppy.plugins.chatgpt_oauth.config import (
                        CHATGPT_OAUTH_CONFIG,
                    )
                    from code_puppy.plugins.chatgpt_oauth.utils import (
                        get_valid_access_token,
                        load_stored_tokens,
                    )
            except ImportError as exc:
                emit_warning(
                    f"ChatGPT OAuth plugin not available; skipping model '{model_config.get('name')}'. "
                    f"Error: {exc}"
                )
                return None

            # Get a valid access token (refreshing if needed)
            access_token = get_valid_access_token()
            if not access_token:
                emit_warning(
                    f"Failed to get valid ChatGPT OAuth token; skipping model '{model_config.get('name')}'. "
                    "Run /chatgpt-auth to authenticate."
                )
                return None

            # Get account_id from stored tokens (required for ChatGPT-Account-Id header)
            tokens = load_stored_tokens()
            account_id = tokens.get("account_id", "") if tokens else ""
            if not account_id:
                emit_warning(
                    f"No account_id found in ChatGPT OAuth tokens; skipping model '{model_config.get('name')}'. "
                    "Run /chatgpt-auth to re-authenticate."
                )
                return None

            # Build headers for ChatGPT Codex API
            originator = CHATGPT_OAUTH_CONFIG.get("originator", "codex_cli_rs")
            client_version = CHATGPT_OAUTH_CONFIG.get("client_version", "0.72.0")

            headers = {
                "ChatGPT-Account-Id": account_id,
                "originator": originator,
                "User-Agent": f"{originator}/{client_version}",
            }
            # Merge with any headers from model config
            config_headers = model_config.get("custom_endpoint", {}).get("headers", {})
            headers.update(config_headers)

            # Get base URL - Codex API uses chatgpt.com, not api.openai.com
            base_url = model_config.get("custom_endpoint", {}).get(
                "url", CHATGPT_OAUTH_CONFIG["api_base_url"]
            )

            # Create HTTP client with Codex interceptor for store=false injection
            from code_puppy.chatgpt_codex_client import create_codex_async_client

            verify = get_cert_bundle_path()
            client = create_codex_async_client(headers=headers, verify=verify)

            provider = OpenAIProvider(
                api_key=access_token,
                base_url=base_url,
                http_client=client,
            )

            # ChatGPT Codex API only supports Responses format
            model = OpenAIResponsesModel(
                model_name=model_config["name"], provider=provider
            )
            setattr(model, "provider", provider)
            return model

        elif model_type == "round_robin":
            # Get the list of model names to use in the round-robin
            model_names = model_config.get("models")
            if not model_names or not isinstance(model_names, list):
                raise ValueError(
                    f"Round-robin model '{model_name}' requires a 'models' list in its configuration."
                )

            # Get the rotate_every parameter (default: 1)
            rotate_every = model_config.get("rotate_every", 1)

            # Resolve each model name to an actual model instance
            models = []
            for name in model_names:
                # Recursively get each model using the factory
                model = ModelFactory.get_model(name, config)
                models.append(model)

            # Create and return the round-robin model
            return RoundRobinModel(*models, rotate_every=rotate_every)

        else:
            raise ValueError(f"Unsupported model type: {model_type}")
