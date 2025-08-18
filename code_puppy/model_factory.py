import json
import os
import random
import asyncio
import time
import math
from collections import deque
from typing import Any, Dict, Optional, Deque

import httpx
from anthropic import AsyncAnthropic
from openai import AsyncAzureOpenAI  # For Azure OpenAI client
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.gemini import GeminiModel
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.google_gla import GoogleGLAProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider

from code_puppy.tools.common import console

# Environment variables used in this module:
# - GEMINI_API_KEY: API key for Google's Gemini models. Required when using Gemini models.
# - OPENAI_API_KEY: API key for OpenAI models. Required when using OpenAI models or custom_openai endpoints.
# - TOGETHER_AI_KEY: API key for Together AI models. Required when using Together AI models.
#
# When using custom endpoints (type: "custom_openai" in models.json):
# - Environment variables can be referenced in header values by prefixing with $ in models.json.
#   Example: "X-Api-Key": "$OPENAI_API_KEY" will use the value from os.environ.get("OPENAI_API_KEY")


def build_proxy_dict(proxy):
    proxy_tokens = proxy.split(":")
    structure = "{}:{}@{}:{}".format(
        proxy_tokens[2], proxy_tokens[3], proxy_tokens[0], proxy_tokens[1]
    )
    proxies = {
        "http": "http://{}/".format(structure),
        "https": "http://{}".format(structure),
    }
    return proxies


def build_httpx_proxy(proxy):
    """Build an httpx.Proxy object from a proxy string in format ip:port:username:password"""
    proxy_tokens = proxy.split(":")
    if len(proxy_tokens) != 4:
        raise ValueError(
            f"Invalid proxy format: {proxy}. Expected format: ip:port:username:password"
        )

    ip, port, username, password = proxy_tokens
    proxy_url = f"http://{ip}:{port}"
    proxy_auth = (username, password)

    # Log the proxy being used
    console.log(f"Using proxy: {proxy_url} with username: {username}")

    return httpx.Proxy(url=proxy_url, auth=proxy_auth)


def get_random_proxy_from_file(file_path):
    """Reads proxy file and returns a random proxy formatted for httpx.AsyncClient"""
    if not os.path.exists(file_path):
        raise ValueError(f"Proxy file '{file_path}' not found.")

    with open(file_path, "r") as f:
        proxies = [line.strip() for line in f.readlines() if line.strip()]

    if not proxies:
        raise ValueError(
            f"Proxy file '{file_path}' is empty or contains only whitespace."
        )

    selected_proxy = random.choice(proxies)
    try:
        return build_httpx_proxy(selected_proxy)
    except ValueError:
        console.log(
            f"Warning: Malformed proxy '{selected_proxy}' found in file '{file_path}', ignoring and continuing without proxy."
        )
        return None


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
            value = os.environ.get(value[1:])
        headers[key] = value

    ca_certs_path = None
    if "ca_certs_path" in custom_config:
        ca_certs_path = custom_config.get("ca_certs_path")
        if ca_certs_path.lower() == "false":
            ca_certs_path = False

    api_key = None
    if "api_key" in custom_config:
        if custom_config["api_key"].startswith("$"):
            api_key = os.environ.get(custom_config["api_key"][1:])
        else:
            api_key = custom_config["api_key"]
    return url, headers, ca_certs_path, api_key


class RateLimiter:
    """Async rate limiter supporting RPM, min interval, max total requests,
    and token-per-minute limits.

    - requests_per_minute: max requests allowed per rolling 60s window
    - min_interval_seconds (aka rate_limit): minimum seconds between requests
    - max_requests_total: hard cap for total requests over the client's lifetime
    - tokens_per_minute: max estimated tokens allowed per rolling 60s window
    """

    def __init__(
        self,
        requests_per_minute: Optional[int] = None,
        min_interval_seconds: Optional[float] = None,
        max_requests_total: Optional[int] = None,
        tokens_per_minute: Optional[int] = None,
    ) -> None:
        self._rpm: Optional[int] = requests_per_minute
        self._min_interval: Optional[float] = min_interval_seconds
        self._max_total: Optional[int] = max_requests_total
        self._tpm: Optional[int] = tokens_per_minute

        self._lock = asyncio.Lock()
        # Per-request timestamps for RPM enforcement
        self._timestamps: Deque[float] = deque()
        # Token events (timestamp, tokens) for TPM enforcement
        self._token_events: Deque[tuple[float, int]] = deque()
        self._count: int = 0
        self._last_request_time: Optional[float] = None

    async def acquire(self, tokens: int = 0) -> None:
        while True:
            # Compute wait time inside lock based on current state
            async with self._lock:
                if self._max_total is not None and self._count >= self._max_total:
                    raise RuntimeError(
                        "Max requests limit reached (max_requests)."
                    )

                now = time.monotonic()
                wait_seconds = 0.0

                # Enforce min interval between requests
                if self._min_interval is not None and self._last_request_time is not None:
                    delta = now - self._last_request_time
                    if delta < self._min_interval:
                        wait_seconds = max(wait_seconds, self._min_interval - delta)

                # Enforce requests per rolling minute
                if self._rpm is not None and self._rpm > 0:
                    # Drop timestamps older than 60s
                    while self._timestamps and now - self._timestamps[0] >= 60.0:
                        self._timestamps.popleft()
                    if len(self._timestamps) >= self._rpm:
                        oldest = self._timestamps[0]
                        wait_seconds = max(wait_seconds, 60.0 - (now - oldest))

                # Enforce tokens per rolling minute
                if self._tpm is not None and self._tpm > 0 and tokens > 0:
                    # Drop token events older than 60s
                    while self._token_events and now - self._token_events[0][0] >= 60.0:
                        self._token_events.popleft()
                    current_tokens = sum(t for _, t in self._token_events)
                    if current_tokens + tokens > self._tpm and self._token_events:
                        oldest_ts, _ = self._token_events[0]
                        wait_seconds = max(wait_seconds, 60.0 - (now - oldest_ts))

                if wait_seconds <= 0.0:
                    # Record the request and proceed
                    self._count += 1
                    self._last_request_time = now
                    self._timestamps.append(now)
                    if self._tpm is not None and tokens > 0:
                        self._token_events.append((now, tokens))
                    return

            # Sleep outside the lock
            await asyncio.sleep(wait_seconds)


def _maybe_create_rate_limited_client(client_args: Dict[str, Any], model_config: Dict[str, Any]) -> httpx.AsyncClient:
    """Attach a rate limiter to httpx.AsyncClient via event hooks if configured.

    Supports keys at the model's top-level:
    - requests_per_minute (preferred)
    - max_requests_per_minute (backward-compatible alias)
    - rate_limit (interpreted as minimum seconds between requests)
    - max_requests (hard cap for the client lifetime)
    - max_token_limit_per_minute (token budget per rolling minute)
    """

    # Backward-compat alias for RPM
    rpm_val = model_config.get("requests_per_minute")
    if rpm_val is None:
        rpm_val = model_config.get("max_requests_per_minute")

    # Normalize/parse values if present
    def _to_int(val):
        try:
            return int(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    def _to_float(val):
        try:
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    rpm = _to_int(rpm_val)
    min_interval = _to_float(model_config.get("rate_limit"))
    max_total = _to_int(model_config.get("max_requests"))
    tpm = _to_int(model_config.get("max_token_limit_per_minute"))

    if any(v is not None for v in (rpm, min_interval, max_total, tpm)):
        limiter = RateLimiter(
            requests_per_minute=rpm,
            min_interval_seconds=min_interval,
            max_requests_total=max_total,
            tokens_per_minute=tpm,
        )

        def _estimate_tokens_from_request(req: httpx.Request) -> int:
            try:
                # Only attempt parse for JSON bodies
                content_type = req.headers.get("content-type", "").lower()
                if "json" not in content_type:
                    return 0
                body_bytes = req.content or b""
                if not body_bytes:
                    return 0
                data = json.loads(body_bytes.decode("utf-8", errors="ignore"))
            except Exception:
                return 0

            texts: list[str] = []
            try:
                # OpenAI Chat-like schema
                if isinstance(data, dict):
                    msgs = data.get("messages")
                    if isinstance(msgs, list):
                        for m in msgs:
                            if not isinstance(m, dict):
                                continue
                            c = m.get("content")
                            if isinstance(c, str):
                                texts.append(c)
                            elif isinstance(c, list):
                                for part in c:
                                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                                        texts.append(part["text"])
                    # Responses API / completion-like fields
                    for key in ("input", "prompt", "text"):
                        val = data.get(key)
                        if isinstance(val, str):
                            texts.append(val)
                        elif isinstance(val, list):
                            for item in val:
                                if isinstance(item, str):
                                    texts.append(item)
                                elif isinstance(item, dict) and isinstance(item.get("text"), str):
                                    texts.append(item["text"])
            except Exception:
                return 0

            approx_tokens = 0
            if texts:
                combined = "\n".join(texts)
                # Very rough heuristic: ~4 characters per token for inputs
                approx_tokens = max(1, math.ceil(len(combined) / 4))

            # Also try to include declared output token caps if present
            try:
                if isinstance(data, dict):
                    for out_key in ("max_output_tokens", "max_tokens"):
                        out_val = data.get(out_key)
                        if isinstance(out_val, int) and out_val > 0:
                            approx_tokens += out_val
                            break
            except Exception:
                pass

            return int(approx_tokens)

        async def _on_request(request: httpx.Request) -> None:  # type: ignore[name-defined]
            tokens = _estimate_tokens_from_request(request) if tpm else 0
            await limiter.acquire(tokens=tokens)

        # Merge with any existing event hooks provided via client_args
        existing_hooks = client_args.get("event_hooks") or {}
        # Ensure we don't mutate the original dicts
        merged_hooks = {k: list(v) for k, v in existing_hooks.items()}
        merged_hooks.setdefault("request", []).append(_on_request)
        client_args = dict(client_args)
        client_args["event_hooks"] = merged_hooks

        console.log(
            f"Enabled rate limiting - rpm={rpm}, min_interval={min_interval}, max_total={max_total}, tpm={tpm}"
        )

    # Build the AsyncClient with (possibly) augmented client_args
    return httpx.AsyncClient(**client_args)


class ModelFactory:
    """A factory for creating and managing different AI models."""

    @staticmethod
    def load_config(config_path: str) -> Dict[str, Any]:
        """Loads model configurations from a JSON file."""
        with open(config_path, "r") as f:
            return json.load(f)

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

            model = OpenAIModel(model_name=model_config["name"], provider=provider)
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
            url, headers, ca_certs_path, api_key = get_custom_config(model_config)

            # Check for proxy configuration
            proxy_file_path = os.environ.get("CODE_PUPPY_PROXIES")
            proxy = None
            if proxy_file_path:
                proxy = get_random_proxy_from_file(proxy_file_path)

            # Only pass proxy to client if it's valid
            client_args = {"headers": headers, "verify": ca_certs_path}
            if proxy is not None:
                client_args["proxy"] = proxy
            client = _maybe_create_rate_limited_client(client_args, model_config)
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
            model = OpenAIModel(model_name=model_config["name"], provider=provider)
            setattr(model, "provider", provider)
            return model

        elif model_type == "custom_openai":
            url, headers, ca_certs_path, api_key = get_custom_config(model_config)

            # Check for proxy configuration
            proxy_file_path = os.environ.get("CODE_PUPPY_PROXIES")
            proxy = None
            if proxy_file_path:
                proxy = get_random_proxy_from_file(proxy_file_path)

            # Only pass proxy to client if it's valid
            client_args = {"headers": headers, "verify": ca_certs_path}
            if proxy is not None:
                client_args["proxy"] = proxy
            client = _maybe_create_rate_limited_client(client_args, model_config)
            provider_args = dict(
                base_url=url,
                http_client=client,
            )
            if api_key:
                provider_args["api_key"] = api_key
            provider = OpenAIProvider(**provider_args)

            model = OpenAIModel(model_name=model_config["name"], provider=provider)
            setattr(model, "provider", provider)
            return model
        elif model_type == "openrouter":
            api_key = None
            if "api_key" in model_config:
                if model_config["api_key"].startswith("$"):
                    api_key = os.environ.get(model_config["api_key"][1:])
                else:
                    api_key = model_config["api_key"]
            provider = OpenRouterProvider(api_key=api_key)
            model_name = model_config.get("name")
            model = OpenAIModel(model_name, provider=provider)
            return model
        else:
            raise ValueError(f"Unsupported model type: {model_type}")
