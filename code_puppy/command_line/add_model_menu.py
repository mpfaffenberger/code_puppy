"""Interactive browser for adding models from the models.dev catalog.

Two chained termflow menus (providers -> models, both searchable with a
details preview) followed by TextInput flows for credentials and custom
model entry. All persistence goes through ``extra_models.json`` via
:mod:`code_puppy.atomic_json`.

The heavy UI machinery of the previous prompt_toolkit implementation is
gone; what remains is the business logic (config building, credential
handling) plus thin widget wiring. Every builder takes ``**overrides``
mapping onto termflow builder setters so tests drive the flow headlessly
with scripted keys.
"""

import os
from typing import Callable, List, Optional, Tuple

from code_puppy import atomic_json
from code_puppy.config import (
    EXTRA_MODELS_FILE,
    MAX_OUTPUT_TOKENS_SETTING,
    set_config_value,
)
from code_puppy.i18n import t
from code_puppy.messaging import emit_error, emit_info, emit_warning
from code_puppy.models_dev_parser import ModelInfo, ModelsDevRegistry, ProviderInfo
from code_puppy.provider_credentials import (
    credential_display,
    save_credential,
)
from code_puppy.tools.command_runner import set_awaiting_user_input


class _ExtraModelsNotADict(Exception):
    """Sentinel: extra_models.json parsed to something other than a dict."""


# Hardcoded OpenAI-compatible endpoints for providers that have dedicated SDKs
# but actually work fine with custom_openai. These are fallbacks when provider.api is not set.
PROVIDER_ENDPOINTS = {
    "xai": "https://api.x.ai/v1",
    "cohere": "https://api.cohere.com/compatibility/v1",  # Cohere's OpenAI-compatible endpoint
    "groq": "https://api.groq.com/openai/v1",
    "mistral": "https://api.mistral.ai/v1",
    "togetherai": "https://api.together.xyz/v1",
    "perplexity": "https://api.perplexity.ai",
    "deepinfra": "https://api.deepinfra.com/v1/openai",
    "aihubmix": "https://aihubmix.com/v1",
}

# Providers that require custom SDK implementations we don't support yet.
UNSUPPORTED_PROVIDERS = {
    "amazon-bedrock": "Use /bedrock-setup to configure (aws_bedrock plugin)",
    "google-vertex": "Requires GCP service account authentication",
    "google-vertex-anthropic": "Requires GCP service account authentication",
    "cloudflare-workers-ai": "Requires account ID in URL path",
    "vercel": "Vercel AI Gateway - not yet supported",
    "v0": "Vercel v0 - not yet supported",
    "ollama-cloud": "Requires user-specific Ollama instance URL",
}

PROVIDER_IDENTITY_MAPPING = {
    "openai": "openai",
    "anthropic": "anthropic",
    "google": "google",
    "google-vertex": "google",
    "mistral": "mistral",
    "groq": "groq",
    "together-ai": "together_ai",
    "fireworks": "fireworks",
    "deepseek": "deepseek",
    "openrouter": "openrouter",
    "cerebras": "cerebras",
    "cohere": "cohere",
    "perplexity": "perplexity",
    "minimax": "minimax",
    "azure-openai": "azure_openai",
    "xai": "xai",
}

ENV_VAR_HINTS = {
    "OPENAI_API_KEY": "Get your API key from https://platform.openai.com/api-keys",
    "ANTHROPIC_API_KEY": "Get your API key from https://console.anthropic.com/",
    "GEMINI_API_KEY": "Get your API key from https://aistudio.google.com/apikey",
    "GOOGLE_API_KEY": "Get your API key from https://aistudio.google.com/apikey",
    "AZURE_API_KEY": "Get your API key from Azure Portal > Your OpenAI Resource > Keys",
    "AZURE_RESOURCE_NAME": "Your Azure OpenAI resource name (not the full URL)",
    "GROQ_API_KEY": "Get your API key from https://console.groq.com/keys",
    "MISTRAL_API_KEY": "Get your API key from https://console.mistral.ai/",
    "COHERE_API_KEY": "Get your API key from https://dashboard.cohere.com/api-keys",
    "DEEPSEEK_API_KEY": "Get your API key from https://platform.deepseek.com/",
    "TOGETHER_API_KEY": "Get your API key from https://api.together.xyz/settings/api-keys",
    "FIREWORKS_API_KEY": "Get your API key from https://fireworks.ai/api-keys",
    "OPENROUTER_API_KEY": "Get your API key from https://openrouter.ai/keys",
    "PERPLEXITY_API_KEY": "Get your API key from https://www.perplexity.ai/settings/api",
    "CEREBRAS_API_KEY": "Get your API key from https://cloud.cerebras.ai/",
    "HUGGINGFACE_API_KEY": "Get your API key from https://huggingface.co/settings/tokens",
    "XAI_API_KEY": "Get your API key from https://console.x.ai/",
}

_CUSTOM_MODEL_VALUE = "__custom_model__"
_EDIT_CREDENTIALS = "__edit_credentials__"


def derive_provider_identity(provider: ProviderInfo) -> str:
    """Derive the persisted provider identity for imported models."""
    provider_id = (provider.id or "").strip()
    if not provider_id:
        return "unknown"
    return PROVIDER_IDENTITY_MAPPING.get(provider_id, provider_id.replace("-", "_"))


def parse_context_size(text: str, default: int = 128000) -> Optional[int]:
    """Parse a context size like ``128000``, ``128k`` or ``1M``.

    Empty text returns ``default``; unparseable text returns ``None`` so
    callers (TextInput validators) can reject it.
    """
    cleaned = text.strip().lower().replace(",", "")
    if not cleaned:
        return default
    multiplier = 1
    if cleaned.endswith("k"):
        multiplier, cleaned = 1000, cleaned[:-1]
    elif cleaned.endswith("m"):
        multiplier, cleaned = 1000000, cleaned[:-1]
    try:
        return int(float(cleaned) * multiplier)
    except ValueError:
        return None


def create_custom_model_info(
    provider_id: str, model_name: str, context_length: int = 128000
) -> ModelInfo:
    """ModelInfo for a model not listed in models.dev (assume sane defaults)."""
    return ModelInfo(
        provider_id=provider_id,
        model_id=model_name,
        name=model_name,
        tool_call=True,  # Assume true for usability
        temperature=True,
        context_length=context_length,
        max_output=min(16384, context_length // 4),
        input_modalities=["text"],
        output_modalities=["text"],
    )


def build_model_config(model: ModelInfo, provider: ProviderInfo) -> dict:
    """Build a Code Puppy compatible model configuration."""
    type_mapping = {
        "openai": "openai",
        "anthropic": "anthropic",
        "google": "gemini",
        "google-vertex": "gemini",
        "mistral": "custom_openai",
        "groq": "custom_openai",
        "together-ai": "custom_openai",
        "fireworks": "custom_openai",
        "deepseek": "custom_openai",
        "openrouter": "custom_openai",
        "cerebras": "cerebras",
        "cohere": "custom_openai",
        "perplexity": "custom_openai",
        "minimax": "custom_anthropic",
    }
    model_type = type_mapping.get(provider.id, "custom_openai")

    # Special case: kimi-for-coding uses a fixed model name.
    model_name = (
        "kimi-for-coding" if provider.id == "kimi-for-coding" else model.model_id
    )

    config: dict = {
        "type": model_type,
        "provider": derive_provider_identity(provider),
        "name": model_name,
    }

    if model_type == "custom_openai":
        api_url = provider.api
        if not api_url or api_url == "N/A":
            api_url = PROVIDER_ENDPOINTS.get(provider.id)
        if api_url:
            api_key_env = f"${provider.env[0]}" if provider.env else "$API_KEY"
            config["custom_endpoint"] = {"url": api_url, "api_key": api_key_env}

    # minimax: custom_anthropic but needs custom_endpoint with /v1 stripped.
    if provider.id == "minimax" and provider.api:
        api_url = provider.api
        if api_url.endswith("/v1"):
            api_url = api_url[:-3]
        api_key_env = f"${provider.env[0]}" if provider.env else "$API_KEY"
        config["custom_endpoint"] = {"url": api_url, "api_key": api_key_env}

    if model.context_length and model.context_length > 0:
        config["context_length"] = model.context_length
    # models.dev ``limit.output`` -> the default ``max_tokens`` for this model
    # (see config.get_model_max_output_tokens).
    if model.max_output and model.max_output > 0:
        config[MAX_OUTPUT_TOKENS_SETTING] = model.max_output

    if model_type == "anthropic":
        config["supported_settings"] = [
            "temperature",
            "extended_thinking",
            "budget_tokens",
        ]
    elif model_type == "openai":
        # Share OpenAI effort capabilities with config and settings menus.
        # Empty means fixed effort; None means an unrecognized model.
        from code_puppy.model_utils import get_openai_reasoning_effort_choices

        effort_choices = get_openai_reasoning_effort_choices(model.model_id)
        if effort_choices:
            config["supported_settings"] = [
                "temperature",
                "top_p",
                "reasoning_effort",
            ]
            # Verbosity is a GPT-5-family Responses/Chat option; codex
            # variants and o-series models don't support it.
            if "gpt-5" in model.model_id and "codex" not in model.model_id:
                config["supported_settings"].append("verbosity")
        else:
            config["supported_settings"] = ["temperature", "seed", "top_p"]
    else:
        config["supported_settings"] = ["temperature", "seed", "top_p"]

    return config


def extra_model_key(provider_id: str, model_id: str) -> str:
    """The ``extra_models.json`` key ``/add_model`` assigns to a catalog model."""
    return f"{provider_id}-{model_id}".replace("/", "-").replace(":", "-")


def add_model_to_extra_config(model: ModelInfo, provider: ProviderInfo) -> bool:
    """Add a model to extra_models.json (locked, atomic read-modify-write)."""
    model_key = extra_model_key(provider.id, model.model_id)
    already_present = False

    def _mutate(current):
        nonlocal already_present
        if not isinstance(current, dict):
            raise _ExtraModelsNotADict()
        if model_key in current:
            already_present = True
            return current
        current[model_key] = build_model_config(model, provider)
        return current

    try:
        atomic_json.mutate_json(EXTRA_MODELS_FILE, _mutate, default={})
    except _ExtraModelsNotADict:
        emit_error(t("model_menu.extra_models.invalid_format"))
        return False
    except atomic_json.JsonFileCorrupt as e:
        emit_error(t("model_menu.extra_models.parse_error", error=e))
        return False
    except Exception as e:
        emit_error(t("model_menu.extra_models.add_error", error=e))
        return False

    if already_present:
        emit_info(t("model_menu.extra_models.already_exists", model_key=model_key))
    else:
        emit_info(t("model_menu.extra_models.added", model_key=model_key))
    return True


def missing_env_vars(provider: ProviderInfo) -> List[str]:
    """Required env vars for ``provider`` that are not currently set."""
    return [env_var for env_var in provider.env if not os.environ.get(env_var)]


from code_puppy.command_line.add_model_details import (  # noqa: E402
    custom_model_details,
    model_details,
    provider_details,
)


# -- menus -------------------------------------------------------------------


def _edit_credentials_key(builder):
    """Bind Ctrl+E to exit the menu with an edit-credentials sentinel."""
    from termflow.tui import MenuItem
    from termflow.tui.menu import MenuResult

    def handler(_menu, item):
        return MenuResult(item=MenuItem("", value=(_EDIT_CREDENTIALS, item.value)))

    builder.on_key("ctrl-e", handler)
    return builder


def build_provider_menu(providers: List[ProviderInfo], **overrides):
    """Searchable provider list with a details preview pane."""
    from termflow.tui import MenuBuilder, MenuItem

    from code_puppy.command_line.tui_style import themed

    items = [
        MenuItem(f"{p.name} ({p.model_count})", value=p, description=p.id)
        for p in providers
    ]
    builder = themed(
        MenuBuilder("Add Model - Providers")
        .items(items)
        .searchable()
        .list_width(36)
        .alt_screen(False)
        .preview(lambda item: provider_details(item.value))
        .footer_hint("type filter - Enter open - Ctrl+E credentials - Esc cancel")
    )
    _edit_credentials_key(builder)
    for name, value in overrides.items():
        getattr(builder, name)(value)
    return builder.build()


def build_models_menu(provider: ProviderInfo, models: List[ModelInfo], **overrides):
    """Searchable model list for one provider, custom-model entry last."""
    from termflow.tui import MenuBuilder, MenuItem

    from code_puppy.command_line.tui_style import themed

    def preview(item):
        if item.value == _CUSTOM_MODEL_VALUE:
            return custom_model_details(provider)
        return model_details(item.value, provider)

    items = [MenuItem(m.name, value=m, description=m.model_id) for m in models]
    items.append(MenuItem("+ Custom model...", value=_CUSTOM_MODEL_VALUE))
    builder = themed(
        MenuBuilder(f"Add Model - {provider.name}")
        .items(items)
        .searchable()
        .list_width(36)
        .alt_screen(False)
        .preview(preview)
        .footer_hint("type filter - Enter add - Ctrl+E credentials - Esc back")
    )
    _edit_credentials_key(builder)
    for name, value in overrides.items():
        getattr(builder, name)(value)
    return builder.build()


# -- TextInput flows ---------------------------------------------------------


def _text_input(title: str, **kwargs):
    from termflow.tui import TextInputBuilder

    from code_puppy.command_line.tui_style import menu_style

    builder = TextInputBuilder(title).alt_screen(False)
    style = menu_style()
    if style is not None:
        builder.style(style)
    for name, value in kwargs.items():
        getattr(builder, name)(value)
    return builder


def _plugin_credential_flow(provider: ProviderInfo, env_var: str) -> bool:
    """Give plugins first crack at acquiring a missing credential.

    A plugin (e.g. an OAuth flow that exchanges a code for an API key) saves
    the credential itself and returns True via the ``provider_credential_flow``
    hook. Trust but verify: the env var must actually be set afterwards,
    otherwise we fall back to manual entry anyway.
    """
    from code_puppy.callbacks import on_provider_credential_flow

    handled = on_provider_credential_flow(provider_id=provider.id, env_var=env_var)
    return bool(handled and os.environ.get(env_var))


def prompt_for_credentials(provider: ProviderInfo, **overrides) -> bool:
    """Prompt for each missing credential. Empty skips; Esc cancels all.

    Plugins get first crack via the ``provider_credential_flow`` hook (e.g.
    browser OAuth); anything unhandled falls back to manual entry, which
    saves via config + os.environ so the key is immediately usable.
    """
    missing = missing_env_vars(provider)
    if not missing:
        emit_info(t("model_menu.credentials.all_set", provider=provider.name))
        return True
    for env_var in missing:
        if _plugin_credential_flow(provider, env_var):
            continue
        result = (
            _text_input(
                f"{provider.name}: {env_var}",
                prompt=f"{env_var}: ",
                placeholder=ENV_VAR_HINTS.get(env_var, "leave empty to skip"),
                mask="*",
                footer_hint="Enter save (empty skips) - Esc cancel",
                **overrides,
            )
            .build()
            .run()
        )
        if result.cancelled:
            emit_warning(t("model_menu.credentials.input_cancelled"))
            return False
        if not result.value:
            emit_warning(t("model_menu.credentials.skipped", env_var=env_var))
            continue
        set_config_value(env_var, result.value)
        os.environ[env_var] = result.value
        emit_info(t("model_menu.credentials.saved_to_config", env_var=env_var))
    return True


def edit_provider_credentials(provider: ProviderInfo, **overrides) -> bool:
    """Edit any credential for a provider (not just missing ones)."""
    if not provider.env:
        return True
    for env_var in provider.env:
        result = (
            _text_input(
                f"{provider.name}: {env_var} ({credential_display(env_var)})",
                prompt=f"{env_var}: ",
                placeholder=ENV_VAR_HINTS.get(env_var, "leave empty to keep current"),
                mask="*",
                footer_hint="Enter save (empty keeps current) - Esc cancel",
                **overrides,
            )
            .build()
            .run()
        )
        if result.cancelled:
            emit_warning(t("model_menu.credentials.edit_cancelled"))
            return False
        if result.value:
            save_credential(env_var, result.value)
            emit_info(t("model_menu.credentials.edit_saved", env_var=env_var))
    return True


def prompt_for_custom_model(
    provider: ProviderInfo, **overrides
) -> Optional[Tuple[str, int]]:
    """Prompt for a custom model id + context size. None when cancelled."""
    name_result = (
        _text_input(
            f"Custom model for {provider.name}",
            prompt="Model ID: ",
            placeholder="e.g. my-org/my-model",
            validator=lambda text: None if text.strip() else "a model id is required",
            **overrides,
        )
        .build()
        .run()
    )
    if name_result.cancelled or not name_result.value:
        emit_warning(t("model_menu.custom_model.no_name"))
        return None

    context_result = (
        _text_input(
            "Context window size",
            prompt="Context size: ",
            placeholder="128000 (also accepts 128k / 1m)",
            validator=lambda text: (
                None if parse_context_size(text) is not None else "not a number"
            ),
            **overrides,
        )
        .build()
        .run()
    )
    if context_result.cancelled:
        emit_warning(t("model_menu.custom_model.input_cancelled"))
        return None
    context_length = parse_context_size(context_result.value or "")
    return (name_result.value.strip(), context_length or 128000)


def confirm_no_tool_call(model: ModelInfo, **overrides) -> bool:
    """Explicit opt-in for models without tool calling."""
    from termflow.tui import MenuBuilder, MenuItem

    from code_puppy.command_line.tui_style import themed

    builder = themed(
        MenuBuilder(f"{model.name} has NO tool calling - add anyway?")
        .items(
            [
                MenuItem("No - pick something else", value=False),
                MenuItem("Yes - add it regardless", value=True),
            ]
        )
        .alt_screen(False)
        .footer_hint("Enter confirm - Esc cancel")
    )
    for name, value in overrides.items():
        getattr(builder, name)(value)
    result = builder.build().run()
    return bool(result.item and result.item.value is True and not result.cancelled)


# -- orchestration -----------------------------------------------------------


def _finalize_add(model: ModelInfo, provider: ProviderInfo, prompt_creds) -> bool:
    if not prompt_creds(provider):
        return False
    return add_model_to_extra_config(model, provider)


def run_add_model_flow(
    registry: Optional[ModelsDevRegistry] = None,
    provider_menu_factory: Callable = build_provider_menu,
    models_menu_factory: Callable = build_models_menu,
    custom_model_prompt: Callable = prompt_for_custom_model,
    credentials_prompt: Callable = prompt_for_credentials,
    credentials_editor: Callable = edit_provider_credentials,
    tool_call_confirm: Callable = confirm_no_tool_call,
) -> bool:
    """The provider -> model -> credentials flow. Returns True when added.

    Collaborators are injectable so tests can script every stage.
    """
    if registry is None:
        try:
            registry = ModelsDevRegistry()
        except FileNotFoundError as e:
            emit_error(t("model_menu.registry.unavailable", error=e))
            return False
        except Exception as e:
            emit_error(t("model_menu.registry.load_error", error=e))
            return False
    providers = registry.get_providers()
    if not providers:
        emit_error(t("model_menu.registry.no_providers"))
        return False

    while True:
        result = provider_menu_factory(providers).run()
        if result.cancelled or result.item is None:
            return False
        if isinstance(result.item.value, tuple):
            _, provider = result.item.value
            if provider.env and not credentials_editor(provider):
                return False
            continue
        provider = result.item.value

        back_to_providers = False
        while True:
            models = registry.get_models(provider.id)
            model_result = models_menu_factory(provider, models).run()
            if model_result.cancelled or model_result.item is None:
                back_to_providers = True
                break
            if isinstance(model_result.item.value, tuple):
                _, creds_provider = model_result.item.value
                if creds_provider.env and not credentials_editor(creds_provider):
                    return False
                continue

            if provider.id in UNSUPPORTED_PROVIDERS:
                emit_error(
                    t(
                        "model_menu.browser.unsupported_provider",
                        provider=provider.name,
                        reason=UNSUPPORTED_PROVIDERS[provider.id],
                    )
                )
                return False

            if model_result.item.value == _CUSTOM_MODEL_VALUE:
                custom = custom_model_prompt(provider)
                if not custom:
                    return False
                model = create_custom_model_info(provider.id, *custom)
                return _finalize_add(model, provider, credentials_prompt)

            model = model_result.item.value
            if not model.tool_call and not tool_call_confirm(model):
                emit_info(t("model_menu.browser.add_cancelled"))
                return False
            return _finalize_add(model, provider, credentials_prompt)

        if back_to_providers:
            continue  # reopen the provider list


def interactive_model_picker() -> bool:
    """Show the interactive model browser. True when a model was added."""
    from code_puppy.command_line.menu_session import menu_session

    set_awaiting_user_input(True)
    try:
        with menu_session():
            added = run_add_model_flow()
    finally:
        set_awaiting_user_input(False)
    if added:
        return True
    emit_info(t("model_menu.browser.exited"))
    return False
