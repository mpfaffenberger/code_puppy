import json
import logging
import os
import pathlib
from typing import Any, Dict

import httpx
from anthropic import AsyncAnthropic
from openai import AsyncAzureOpenAI
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.gemini import GeminiModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.google_gla import GoogleGLAProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.cerebras import CerebrasProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider

from . import callbacks
from .config import EXTRA_MODELS_FILE
from .http_utils import create_async_client
from .round_robin_model import RoundRobinModel

# Environment variables used in this module:
# - GEMINI_API_KEY: API key for Google's Gemini models. Required when using Gemini models.
# - OPENAI_API_KEY: API key for OpenAI models. Required when using OpenAI models or custom_openai endpoints.
# - TOGETHER_AI_KEY: API key for Together AI models. Required when using Together AI models.
#
# When using custom endpoints (type: "custom_openai" in models.json):
# - Environment variables can be referenced in header values by prefixing with $ in models.json.
#   Example: "X-Api-Key": "$OPENAI_API_KEY" will use the value from os.environ.get("OPENAI_API_KEY")


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
            resolved_value = os.environ.get(env_var_name)
            if resolved_value is None:
                raise ValueError(
                    f"Environment variable '{env_var_name}' is required for custom endpoint headers but is not set. "
                    f"Please set the environment variable: export {env_var_name}=your_value"
                )
            value = resolved_value
        headers[key] = value

    api_key = None
    if "api_key" in custom_config:
        if custom_config["api_key"].startswith("$"):
            env_var_name = custom_config["api_key"][1:]
            api_key = os.environ.get(env_var_name)
            if api_key is None:
                raise ValueError(
                    f"Environment variable '{env_var_name}' is required for custom endpoint API key but is not set. "
                    f"Please set the environment variable: export {env_var_name}=your_value"
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

        if pathlib.Path(EXTRA_MODELS_FILE).exists():
            try:
                with open(EXTRA_MODELS_FILE, "r") as f:
                    extra_config = json.load(f)
                    config.update(extra_config)
            except json.JSONDecodeError as e:
                logging.getLogger(__name__).warning(
                    f"Failed to load extra models config from {EXTRA_MODELS_FILE}: Invalid JSON - {e}\n"
                    f"Please check your extra_models.json file for syntax errors."
                )
            except Exception as e:
                logging.getLogger(__name__).warning(
                    f"Failed to load extra models config from {EXTRA_MODELS_FILE}: {e}\n"
                    f"The extra models configuration will be ignored."
                )
        return config

    @staticmethod
    def get_model(model_name: str, config: Dict[str, Any]) -> Any:
        """Returns a configured model instance based on the provided name and config."""
        model_config = config.get(model_name)
        if not model_config:
            raise ValueError(f"Model '{model_name}' not found in configuration.")

        model_type = model_config.get("type")

        if model_type == "gemini":
            provider = GoogleGLAProvider(api_key=os.environ.get("GEMINI_API_KEY", ""))

            model = GeminiModel(model_name=model_config["name"], provider=provider)
            setattr(model, "provider", provider)
            return model

        elif model_type == "openai":
            provider = OpenAIProvider(api_key=os.environ.get("OPENAI_API_KEY", ""))

            model = OpenAIChatModel(model_name=model_config["name"], provider=provider)
            setattr(model, "provider", provider)
            return model

        elif model_type == "anthropic":
            api_key = os.environ.get("ANTHROPIC_API_KEY", None)
            if not api_key:
                raise ValueError(
                    "ANTHROPIC_API_KEY environment variable must be set for Anthropic models."
                )
            anthropic_client = AsyncAnthropic(api_key=api_key)
            provider = AnthropicProvider(anthropic_client=anthropic_client)
            return AnthropicModel(model_name=model_config["name"], provider=provider)

        elif model_type == "custom_anthropic":
            url, headers, verify, api_key = get_custom_config(model_config)
            client = create_async_client(headers=headers, verify=verify)
            anthropic_client = AsyncAnthropic(
                base_url=url,
                http_client=client,
                api_key=api_key,
            )
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
                azure_endpoint = os.environ.get(azure_endpoint_config[1:])
            if not azure_endpoint:
                raise ValueError(
                    f"Azure OpenAI endpoint environment variable '{azure_endpoint_config[1:] if azure_endpoint_config.startswith('$') else ''}' not found or is empty."
                )

            api_version_config = model_config.get("api_version")
            if not api_version_config:
                raise ValueError(
                    "Azure OpenAI model type requires 'api_version' in its configuration."
                )
            api_version = api_version_config
            if api_version_config.startswith("$"):
                api_version = os.environ.get(api_version_config[1:])
            if not api_version:
                raise ValueError(
                    f"Azure OpenAI API version environment variable '{api_version_config[1:] if api_version_config.startswith('$') else ''}' not found or is empty."
                )

            api_key_config = model_config.get("api_key")
            if not api_key_config:
                raise ValueError(
                    "Azure OpenAI model type requires 'api_key' in its configuration."
                )
            api_key = api_key_config
            if api_key_config.startswith("$"):
                api_key = os.environ.get(api_key_config[1:])
            if not api_key:
                raise ValueError(
                    f"Azure OpenAI API key environment variable '{api_key_config[1:] if api_key_config.startswith('$') else ''}' not found or is empty."
                )

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
            setattr(model, "provider", provider)
            return model

        elif model_type == "custom_gemini":
            url, headers, verify, api_key = get_custom_config(model_config)
            os.environ["GEMINI_API_KEY"] = api_key

            class CustomGoogleGLAProvider(GoogleGLAProvider):
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
            model = GeminiModel(model_name=model_config["name"], provider=google_gla)
            return model
        elif model_type == "cerebras":
            url, headers, verify, api_key = get_custom_config(model_config)
            client = create_async_client(headers=headers, verify=verify)
            provider_args = dict(
                api_key=api_key,
                http_client=client,
            )
            if api_key:
                provider_args["api_key"] = api_key
            provider = CerebrasProvider(**provider_args)

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
                    api_key = os.environ.get(env_var_name)
                    if api_key is None:
                        raise ValueError(
                            f"OpenRouter API key environment variable '{env_var_name}' not found or is empty. "
                            f"Please set the environment variable: export {env_var_name}=your_value"
                        )
                else:
                    # It's a raw API key value
                    api_key = api_key_config
            else:
                # No API key in config, try to get it from the default environment variable
                api_key = os.environ.get("OPENROUTER_API_KEY")

            provider = OpenRouterProvider(api_key=api_key)

            model = OpenAIChatModel(model_name=model_config["name"], provider=provider)
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
