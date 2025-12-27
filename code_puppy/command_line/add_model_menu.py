"""Interactive terminal UI for browsing and adding models from models_dev_api.json.

Provides a beautiful split-panel interface for browsing providers and models
with live preview of model details and one-click addition to extra_models.json.
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import List, Optional

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Dimension, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame

from code_puppy.config import EXTRA_MODELS_FILE, set_config_value
from code_puppy.messaging import emit_error, emit_info, emit_warning
from code_puppy.models_dev_parser import ModelInfo, ModelsDevRegistry, ProviderInfo
from code_puppy.tools.command_runner import set_awaiting_user_input

PAGE_SIZE = 15  # Items per page

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
# These use non-OpenAI-compatible APIs or require special authentication (AWS SigV4, GCP, etc.)
UNSUPPORTED_PROVIDERS = {
    "amazon-bedrock": "Requires AWS SigV4 authentication",
    "google-vertex": "Requires GCP service account authentication",
    "google-vertex-anthropic": "Requires GCP service account authentication",
    "cloudflare-workers-ai": "Requires account ID in URL path",
    "vercel": "Vercel AI Gateway - not yet supported",
    "v0": "Vercel v0 - not yet supported",
    "ollama-cloud": "Requires user-specific Ollama instance URL",
}


class AddModelMenu:
    """Interactive TUI for browsing and adding models."""

    def __init__(self):
        """Initialize the model browser menu."""
        self.registry: Optional[ModelsDevRegistry] = None
        self.providers: List[ProviderInfo] = []
        self.current_provider: Optional[ProviderInfo] = None
        self.current_models: List[ModelInfo] = []

        # State management
        self.view_mode = "providers"  # "providers" or "models"
        self.selected_provider_idx = 0
        self.selected_model_idx = 0
        self.current_page = 0
        self.result = None  # Track if user added a model

        # Pending model for credential prompting
        self.pending_model: Optional[ModelInfo] = None
        self.pending_provider: Optional[ProviderInfo] = None

        # Custom model support
        self.is_custom_model_selected = False
        self.custom_model_name: Optional[str] = None

        # Initialize registry
        self._initialize_registry()

    def _initialize_registry(self):
        """Initialize the ModelsDevRegistry with error handling.

        Fetches from live models.dev API first, falls back to bundled JSON.
        """
        try:
            self.registry = (
                ModelsDevRegistry()
            )  # Will try API first, then bundled fallback
            self.providers = self.registry.get_providers()
            if not self.providers:
                emit_error("No providers found in models database")
        except FileNotFoundError as e:
            emit_error(f"Models database unavailable: {e}")
        except Exception as e:
            emit_error(f"Error loading models registry: {e}")

    def _get_current_provider(self) -> Optional[ProviderInfo]:
        """Get the currently selected provider."""
        if 0 <= self.selected_provider_idx < len(self.providers):
            return self.providers[self.selected_provider_idx]
        return None

    def _get_current_model(self) -> Optional[ModelInfo]:
        """Get the currently selected model.

        Returns None if "Custom model" option is selected (which is at index len(current_models)).
        """
        if self.view_mode == "models" and self.current_provider:
            # Check if custom model option is selected (it's the last item)
            if self.selected_model_idx == len(self.current_models):
                return None  # Custom model selected
            if 0 <= self.selected_model_idx < len(self.current_models):
                return self.current_models[self.selected_model_idx]
        return None

    def _is_custom_model_selected(self) -> bool:
        """Check if the custom model option is currently selected."""
        if self.view_mode == "models" and self.current_provider:
            return self.selected_model_idx == len(self.current_models)
        return False

    def _render_provider_list(self) -> List:
        """Render the provider list panel."""
        lines = []

        lines.append(("", " Providers"))
        lines.append(("", "\n\n"))

        if not self.providers:
            lines.append(("fg:yellow", "  No providers available."))
            lines.append(("", "\n\n"))
            self._render_navigation_hints(lines)
            return lines

        # Show providers for current page
        total_pages = (len(self.providers) + PAGE_SIZE - 1) // PAGE_SIZE
        start_idx = self.current_page * PAGE_SIZE
        end_idx = min(start_idx + PAGE_SIZE, len(self.providers))

        for i in range(start_idx, end_idx):
            provider = self.providers[i]
            is_selected = i == self.selected_provider_idx
            is_unsupported = provider.id in UNSUPPORTED_PROVIDERS

            # Format: "> Provider Name (X models)" or "  Provider Name (X models)"
            prefix = " > " if is_selected else "   "
            suffix = " ⚠️" if is_unsupported else ""
            label = f"{prefix}{provider.name} ({provider.model_count} models){suffix}"

            # Use dimmed color for unsupported providers
            if is_unsupported:
                lines.append(("fg:ansibrightblack dim", label))
            elif is_selected:
                lines.append(("fg:ansibrightblack", label))
            else:
                lines.append(("fg:ansibrightblack", label))

            lines.append(("", "\n"))

        lines.append(("", "\n"))
        lines.append(
            ("fg:ansibrightblack", f" Page {self.current_page + 1}/{total_pages}")
        )
        lines.append(("", "\n"))

        self._render_navigation_hints(lines)
        return lines

    def _render_model_list(self) -> List:
        """Render the model list panel."""
        lines = []

        if not self.current_provider:
            lines.append(("fg:yellow", "  No provider selected."))
            lines.append(("", "\n\n"))
            self._render_navigation_hints(lines)
            return lines

        lines.append(("", f" {self.current_provider.name} Models"))
        lines.append(("", "\n\n"))

        # Total items = models + 1 for custom model option
        total_items = len(self.current_models) + 1
        total_pages = (total_items + PAGE_SIZE - 1) // PAGE_SIZE
        start_idx = self.current_page * PAGE_SIZE
        end_idx = min(start_idx + PAGE_SIZE, total_items)

        # Render models from the current page
        for i in range(start_idx, end_idx):
            # Check if this is the custom model option (last item)
            if i == len(self.current_models):
                is_selected = i == self.selected_model_idx
                if is_selected:
                    lines.append(("fg:ansicyan bold", " > ✨ Custom model..."))
                else:
                    lines.append(("fg:ansicyan", "   ✨ Custom model..."))
                lines.append(("", "\n"))
                continue

            model = self.current_models[i]
            is_selected = i == self.selected_model_idx

            # Create capability icons
            icons = []
            if model.has_vision:
                icons.append("👁")
            if model.tool_call:
                icons.append("🔧")
            if model.reasoning:
                icons.append("🧠")

            icon_str = " ".join(icons) + " " if icons else ""

            if is_selected:
                lines.append(("fg:ansibrightblack", f" > {icon_str}{model.name}"))
            else:
                lines.append(("fg:ansibrightblack", f"   {icon_str}{model.name}"))

            lines.append(("", "\n"))

        lines.append(("", "\n"))
        lines.append(
            ("fg:ansibrightblack", f" Page {self.current_page + 1}/{total_pages}")
        )
        lines.append(("", "\n"))

        self._render_navigation_hints(lines)
        return lines

    def _render_navigation_hints(self, lines: List):
        """Render navigation hints at the bottom of the list panel."""
        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", "  ↑/↓ "))
        lines.append(("", "Navigate  "))
        lines.append(("fg:ansibrightblack", "←/→ "))
        lines.append(("", "Page\n"))
        if self.view_mode == "providers":
            lines.append(("fg:green", "  Enter  "))
            lines.append(("", "Select\n"))
        else:
            lines.append(("fg:green", "  Enter  "))
            lines.append(("", "Add Model\n"))
            lines.append(("fg:ansibrightblack", "  Esc/Back  "))
            lines.append(("", "Back\n"))
        lines.append(("fg:ansibrightred", "  Ctrl+C "))
        lines.append(("", "Cancel"))

    def _render_model_details(self) -> List:
        """Render the model details panel."""
        lines = []

        lines.append(("dim cyan", " MODEL DETAILS"))
        lines.append(("", "\n\n"))

        if self.view_mode == "providers":
            provider = self._get_current_provider()
            if not provider:
                lines.append(("fg:yellow", "  No provider selected."))
                return lines

            lines.append(("bold", f"  {provider.name}"))
            lines.append(("", "\n"))
            lines.append(("fg:ansibrightblack", f"  ID: {provider.id}"))
            lines.append(("", "\n"))
            lines.append(("fg:ansibrightblack", f"  Models: {provider.model_count}"))
            lines.append(("", "\n"))
            lines.append(("fg:ansibrightblack", f"  API: {provider.api}"))
            lines.append(("", "\n"))

            # Show unsupported warning if applicable
            if provider.id in UNSUPPORTED_PROVIDERS:
                lines.append(("", "\n"))
                lines.append(("fg:ansired bold", "  ⚠️  UNSUPPORTED PROVIDER"))
                lines.append(("", "\n"))
                lines.append(("fg:ansired", f"  {UNSUPPORTED_PROVIDERS[provider.id]}"))
                lines.append(("", "\n"))
                lines.append(
                    (
                        "fg:ansibrightblack",
                        "  Models from this provider cannot be added.",
                    )
                )
                lines.append(("", "\n"))

            if provider.env:
                lines.append(("", "\n"))
                lines.append(("bold", "  Environment Variables:"))
                lines.append(("", "\n"))
                for env_var in provider.env:
                    lines.append(("fg:ansibrightblack", f"    • {env_var}"))
                    lines.append(("", "\n"))

            if provider.doc:
                lines.append(("", "\n"))
                lines.append(("bold", "  Documentation:"))
                lines.append(("", "\n"))
                lines.append(("fg:ansibrightblack", f"    {provider.doc}"))
                lines.append(("", "\n"))

        else:  # models view
            model = self._get_current_model()
            provider = self.current_provider

            if not provider:
                lines.append(("fg:yellow", "  No model selected."))
                return lines

            # Handle custom model option
            if self._is_custom_model_selected():
                lines.append(("bold", "  ✨ Custom Model"))
                lines.append(("", "\n\n"))
                lines.append(("fg:ansicyan", "  Add a model not listed in models.dev"))
                lines.append(("", "\n\n"))
                lines.append(("bold", "  How it works:"))
                lines.append(("", "\n"))
                lines.append(("fg:ansibrightblack", "  1. Press Enter to select"))
                lines.append(("", "\n"))
                lines.append(("fg:ansibrightblack", "  2. Enter the model ID/name"))
                lines.append(("", "\n"))
                lines.append(
                    ("fg:ansibrightblack", f"  3. Uses {provider.name}'s API endpoint")
                )
                lines.append(("", "\n\n"))
                lines.append(("bold", "  Use cases:"))
                lines.append(("", "\n"))
                lines.append(("fg:ansibrightblack", "  • Newly released models"))
                lines.append(("", "\n"))
                lines.append(("fg:ansibrightblack", "  • Fine-tuned models"))
                lines.append(("", "\n"))
                lines.append(("fg:ansibrightblack", "  • Preview/beta models"))
                lines.append(("", "\n"))
                lines.append(("fg:ansibrightblack", "  • Custom deployments"))
                lines.append(("", "\n\n"))
                if provider.env:
                    lines.append(("bold", "  Required credentials:"))
                    lines.append(("", "\n"))
                    for env_var in provider.env:
                        lines.append(("fg:ansibrightblack", f"    • {env_var}"))
                        lines.append(("", "\n"))
                return lines

            if not model:
                lines.append(("fg:yellow", "  No model selected."))
                return lines

            lines.append(("bold", f"  {provider.name} - {model.name}"))
            lines.append(("", "\n\n"))

            # BIG WARNING for models without tool calling
            if not model.tool_call:
                lines.append(("fg:ansiyellow bold", "  ⚠️  NO TOOL CALLING SUPPORT"))
                lines.append(("", "\n"))
                lines.append(
                    ("fg:ansiyellow", "  This model cannot use tools (file ops,")
                )
                lines.append(("", "\n"))
                lines.append(
                    ("fg:ansiyellow", "  shell commands, etc). It will be very")
                )
                lines.append(("", "\n"))
                lines.append(("fg:ansiyellow", "  limited for coding tasks!"))
                lines.append(("", "\n\n"))

            # Capabilities
            lines.append(("bold", "  Capabilities:"))
            lines.append(("", "\n"))

            capabilities = [
                ("Vision", model.has_vision),
                ("Tool Calling", model.tool_call),
                ("Reasoning", model.reasoning),
                ("Temperature", model.temperature),
                ("Structured Output", model.structured_output),
                ("Attachments", model.attachment),
            ]

            for cap_name, has_cap in capabilities:
                if has_cap:
                    lines.append(("fg:green", f"    ✓ {cap_name}"))
                else:
                    lines.append(("fg:ansibrightblack", f"    ✗ {cap_name}"))
                lines.append(("", "\n"))

            # Pricing
            lines.append(("", "\n"))
            lines.append(("bold", "  Pricing:"))
            lines.append(("", "\n"))

            if model.cost_input is not None or model.cost_output is not None:
                if model.cost_input is not None:
                    lines.append(
                        (
                            "fg:ansibrightblack",
                            f"    Input: ${model.cost_input:.6f}/token",
                        )
                    )
                    lines.append(("", "\n"))
                if model.cost_output is not None:
                    lines.append(
                        (
                            "fg:ansibrightblack",
                            f"    Output: ${model.cost_output:.6f}/token",
                        )
                    )
                    lines.append(("", "\n"))
                if model.cost_cache_read is not None:
                    lines.append(
                        (
                            "fg:ansibrightblack",
                            f"    Cache Read: ${model.cost_cache_read:.6f}/token",
                        )
                    )
                    lines.append(("", "\n"))
            else:
                lines.append(("fg:ansibrightblack", "    Pricing not available"))
                lines.append(("", "\n"))

            # Limits
            lines.append(("", "\n"))
            lines.append(("bold", "  Limits:"))
            lines.append(("", "\n"))

            if model.context_length > 0:
                lines.append(
                    (
                        "fg:ansibrightblack",
                        f"    Context: {model.context_length:,} tokens",
                    )
                )
                lines.append(("", "\n"))
            if model.max_output > 0:
                lines.append(
                    (
                        "fg:ansibrightblack",
                        f"    Max Output: {model.max_output:,} tokens",
                    )
                )
                lines.append(("", "\n"))

            # Modalities
            if model.input_modalities or model.output_modalities:
                lines.append(("", "\n"))
                lines.append(("bold", "  Modalities:"))
                lines.append(("", "\n"))

                if model.input_modalities:
                    lines.append(
                        (
                            "fg:ansibrightblack",
                            f"    Input: {', '.join(model.input_modalities)}",
                        )
                    )
                    lines.append(("", "\n"))
                if model.output_modalities:
                    lines.append(
                        (
                            "fg:ansibrightblack",
                            f"    Output: {', '.join(model.output_modalities)}",
                        )
                    )
                    lines.append(("", "\n"))

            # Metadata
            lines.append(("", "\n"))
            lines.append(("bold", "  Metadata:"))
            lines.append(("", "\n"))

            lines.append(("fg:ansibrightblack", f"    Model ID: {model.model_id}"))
            lines.append(("", "\n"))
            lines.append(("fg:ansibrightblack", f"    Full ID: {model.full_id}"))
            lines.append(("", "\n"))

            if model.knowledge:
                lines.append(
                    ("fg:ansibrightblack", f"    Knowledge: {model.knowledge}")
                )
                lines.append(("", "\n"))

            if model.release_date:
                lines.append(
                    ("fg:ansibrightblack", f"    Released: {model.release_date}")
                )
                lines.append(("", "\n"))

            lines.append(
                ("fg:ansibrightblack", f"    Open Weights: {model.open_weights}")
            )
            lines.append(("", "\n"))

        return lines

    def _add_model_to_extra_config(
        self, model: ModelInfo, provider: ProviderInfo
    ) -> bool:
        """Add a model to the extra_models.json configuration file.

        The extra_models.json format is a dictionary where:
        - Keys are user-friendly model names (e.g., "provider-model-name")
        - Values contain type, name, custom_endpoint (if needed), and context_length
        """
        try:
            # Load existing extra models (dictionary format)
            extra_models_path = Path(EXTRA_MODELS_FILE)
            extra_models: dict = {}

            if extra_models_path.exists():
                try:
                    with open(extra_models_path, "r", encoding="utf-8") as f:
                        extra_models = json.load(f)
                        if not isinstance(extra_models, dict):
                            emit_error(
                                "extra_models.json must be a dictionary, not a list"
                            )
                            return False
                except json.JSONDecodeError as e:
                    emit_error(f"Error parsing extra_models.json: {e}")
                    return False

            # Create a unique key for this model (provider-modelname format)
            model_key = f"{provider.id}-{model.model_id}".replace("/", "-").replace(
                ":", "-"
            )

            # Check for duplicates
            if model_key in extra_models:
                emit_info(f"Model {model_key} is already in extra_models.json")
                return True  # Not an error, just already exists

            # Convert to Code Puppy config format (dictionary value)
            config = self._build_model_config(model, provider)
            extra_models[model_key] = config

            # Ensure directory exists
            extra_models_path.parent.mkdir(parents=True, exist_ok=True)

            # Save updated configuration
            with open(extra_models_path, "w", encoding="utf-8") as f:
                json.dump(extra_models, f, indent=4, ensure_ascii=False)

            emit_info(f"Added {model_key} to extra_models.json")
            return True

        except Exception as e:
            emit_error(f"Error adding model to extra_models.json: {e}")
            return False

    def _build_model_config(self, model: ModelInfo, provider: ProviderInfo) -> dict:
        """Build a Code Puppy compatible model configuration.

        Format matches models.json structure:
        {
            "type": "openai" | "anthropic" | "gemini" | "custom_openai" | etc.,
            "name": "actual-model-id",
            "custom_endpoint": {"url": "...", "api_key": "$ENV_VAR"},  # if needed
            "context_length": 200000
        }
        """
        # Map provider IDs to Code Puppy types
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

        # Determine the model type
        model_type = type_mapping.get(provider.id, "custom_openai")

        # Special case: kimi-for-coding provider uses "kimi-for-coding" as the model name
        # instead of the model_id from models.dev (which is "kimi-k2-thinking")
        if provider.id == "kimi-for-coding":
            model_name = "kimi-for-coding"
        else:
            model_name = model.model_id

        config: dict = {
            "type": model_type,
            "name": model_name,
        }

        # Add custom endpoint for non-standard providers
        if model_type == "custom_openai":
            # Get the API URL - prefer provider.api, fall back to hardcoded endpoints
            api_url = provider.api
            if not api_url or api_url == "N/A":
                api_url = PROVIDER_ENDPOINTS.get(provider.id)

            if api_url:
                # Determine the API key environment variable
                api_key_env = f"${provider.env[0]}" if provider.env else "$API_KEY"
                config["custom_endpoint"] = {"url": api_url, "api_key": api_key_env}

        # Special handling for minimax: uses custom_anthropic but needs custom_endpoint
        # and the URL needs /v1 stripped (comes as https://api.minimax.io/anthropic/v1)
        if provider.id == "minimax" and provider.api:
            api_url = provider.api
            # Strip /v1 suffix if present
            if api_url.endswith("/v1"):
                api_url = api_url[:-3]
            api_key_env = f"${provider.env[0]}" if provider.env else "$API_KEY"
            config["custom_endpoint"] = {"url": api_url, "api_key": api_key_env}

        # Add context length if available
        if model.context_length and model.context_length > 0:
            config["context_length"] = model.context_length

        # Add supported settings based on model type
        if model_type == "anthropic":
            config["supported_settings"] = [
                "temperature",
                "extended_thinking",
                "budget_tokens",
            ]
        elif model_type == "openai" and "gpt-5" in model.model_id:
            # GPT-5 models have special settings
            if "codex" in model.model_id:
                config["supported_settings"] = ["reasoning_effort"]
            else:
                config["supported_settings"] = ["reasoning_effort", "verbosity"]
        else:
            # Default settings for most models (no top_p)
            config["supported_settings"] = ["temperature", "seed"]

        return config

    def update_display(self):
        """Update the display based on current state."""
        if self.view_mode == "providers":
            self.menu_control.text = self._render_provider_list()
        else:
            self.menu_control.text = self._render_model_list()

        self.preview_control.text = self._render_model_details()

    def _enter_provider(self):
        """Enter the selected provider to view its models."""
        provider = self._get_current_provider()
        if not provider or not self.registry:
            return

        self.current_provider = provider
        self.current_models = self.registry.get_models(provider.id)
        self.view_mode = "models"
        self.selected_model_idx = 0
        self.current_page = 0
        self.update_display()

    def _go_back_to_providers(self):
        """Go back to providers view."""
        self.view_mode = "providers"
        self.current_provider = None
        self.current_models = []
        self.selected_model_idx = 0
        self.current_page = 0
        self.update_display()

    def _add_current_model(self):
        """Add the currently selected model to extra_models.json."""
        provider = self.current_provider

        if not provider:
            return

        # Block unsupported providers
        if provider.id in UNSUPPORTED_PROVIDERS:
            self.result = "unsupported"
            return

        # Check if custom model option is selected
        if self._is_custom_model_selected():
            self.is_custom_model_selected = True
            self.pending_provider = provider
            self.result = (
                "pending_custom_model"  # Signal to prompt for custom model name
            )
            return

        model = self._get_current_model()
        if model:
            # Store model/provider for credential prompting after TUI exits
            self.pending_model = model
            self.pending_provider = provider
            self.result = "pending_credentials"  # Signal to prompt for credentials

    def _get_missing_env_vars(self, provider: ProviderInfo) -> List[str]:
        """Check which required env vars are missing for a provider."""
        missing = []
        for env_var in provider.env:
            if not os.environ.get(env_var):
                missing.append(env_var)
        return missing

    def _prompt_for_credentials(self, provider: ProviderInfo) -> bool:
        """Prompt user for missing credentials and save them.

        Returns:
            True if all credentials were provided (or none needed), False if user cancelled
        """
        missing_vars = self._get_missing_env_vars(provider)

        if not missing_vars:
            emit_info(
                f"✅ All required credentials for {provider.name} are already set!"
            )
            return True

        emit_info(f"\n🔑 {provider.name} requires the following credentials:\n")

        for env_var in missing_vars:
            # Show helpful hints based on common env var patterns
            hint = self._get_env_var_hint(env_var)
            if hint:
                emit_info(f"  {hint}")

            try:
                # Use regular input - simpler and works in threaded context
                value = input(f"  Enter {env_var} (or press Enter to skip): ").strip()

                if not value:
                    emit_warning(
                        f"Skipped {env_var} - you can set it later with /set {env_var}=<value>"
                    )
                    continue

                # Save to config
                set_config_value(env_var, value)
                # Also set in current environment so it's immediately available
                os.environ[env_var] = value
                emit_info(f"✅ Saved {env_var} to config")

            except (KeyboardInterrupt, EOFError):
                emit_info("")  # Clean newline
                emit_warning("Credential input cancelled")
                return False

        return True

    def _create_custom_model_info(
        self, model_name: str, context_length: int = 128000
    ) -> ModelInfo:
        """Create a ModelInfo object for a custom model.

        Since we don't know the model's capabilities, we assume reasonable defaults.
        """
        provider_id = self.pending_provider.id if self.pending_provider else "custom"
        return ModelInfo(
            provider_id=provider_id,
            model_id=model_name,
            name=model_name,
            tool_call=True,  # Assume true for usability
            temperature=True,
            context_length=context_length,
            max_output=min(
                16384, context_length // 4
            ),  # Reasonable default based on context
            input_modalities=["text"],
            output_modalities=["text"],
        )

    def _prompt_for_custom_model(self) -> Optional[tuple[str, int]]:
        """Prompt user for custom model details.

        Returns:
            Tuple of (model_name, context_length) if provided, None if cancelled
        """
        provider = self.pending_provider
        if not provider:
            return None

        emit_info(f"\n✨ Adding custom model for {provider.name}\n")
        emit_info("  Enter the model ID exactly as the provider expects it.")
        emit_info(
            "  Examples: gpt-4-turbo-preview, claude-3-opus-20240229, gemini-1.5-pro-latest\n"
        )

        try:
            model_name = input("  Model ID: ").strip()

            if not model_name:
                emit_warning("No model name provided, cancelled.")
                return None

            # Ask for context size
            emit_info("\n  Enter the context window size (in tokens).")
            emit_info("  Common sizes: 8192, 32768, 128000, 200000, 1000000\n")

            context_input = input("  Context size [128000]: ").strip()

            if not context_input:
                context_length = 128000  # Default
            else:
                # Handle k/K suffix (e.g., "128k" -> 128000)
                context_input_lower = context_input.lower().replace(",", "")
                if context_input_lower.endswith("k"):
                    try:
                        context_length = int(float(context_input_lower[:-1]) * 1000)
                    except ValueError:
                        emit_warning("Invalid context size, using default 128000")
                        context_length = 128000
                elif context_input_lower.endswith("m"):
                    try:
                        context_length = int(float(context_input_lower[:-1]) * 1000000)
                    except ValueError:
                        emit_warning("Invalid context size, using default 128000")
                        context_length = 128000
                else:
                    try:
                        context_length = int(context_input)
                    except ValueError:
                        emit_warning("Invalid context size, using default 128000")
                        context_length = 128000

            return (model_name, context_length)

        except (KeyboardInterrupt, EOFError):
            emit_info("")  # Clean newline
            emit_warning("Custom model input cancelled")
            return None

    def _get_env_var_hint(self, env_var: str) -> str:
        """Get a helpful hint for common environment variables."""
        hints = {
            "OPENAI_API_KEY": "💡 Get your API key from https://platform.openai.com/api-keys",
            "ANTHROPIC_API_KEY": "💡 Get your API key from https://console.anthropic.com/",
            "GEMINI_API_KEY": "💡 Get your API key from https://aistudio.google.com/apikey",
            "GOOGLE_API_KEY": "💡 Get your API key from https://aistudio.google.com/apikey",
            "AZURE_API_KEY": "💡 Get your API key from Azure Portal > Your OpenAI Resource > Keys",
            "AZURE_RESOURCE_NAME": "💡 Your Azure OpenAI resource name (not the full URL)",
            "GROQ_API_KEY": "💡 Get your API key from https://console.groq.com/keys",
            "MISTRAL_API_KEY": "💡 Get your API key from https://console.mistral.ai/",
            "COHERE_API_KEY": "💡 Get your API key from https://dashboard.cohere.com/api-keys",
            "DEEPSEEK_API_KEY": "💡 Get your API key from https://platform.deepseek.com/",
            "TOGETHER_API_KEY": "💡 Get your API key from https://api.together.xyz/settings/api-keys",
            "FIREWORKS_API_KEY": "💡 Get your API key from https://fireworks.ai/api-keys",
            "OPENROUTER_API_KEY": "💡 Get your API key from https://openrouter.ai/keys",
            "PERPLEXITY_API_KEY": "💡 Get your API key from https://www.perplexity.ai/settings/api",
            "CEREBRAS_API_KEY": "💡 Get your API key from https://cloud.cerebras.ai/",
            "HUGGINGFACE_API_KEY": "💡 Get your API key from https://huggingface.co/settings/tokens",
            "XAI_API_KEY": "💡 Get your API key from https://console.x.ai/",
        }
        return hints.get(env_var, "")

    def run(self) -> bool:
        """Run the interactive model browser (synchronous).

        Returns:
            True if a model was added, False otherwise
        """
        if not self.registry or not self.providers:
            emit_warning("No models data available.")
            return False

        # Build UI
        self.menu_control = FormattedTextControl(text="")
        self.preview_control = FormattedTextControl(text="")

        menu_window = Window(
            content=self.menu_control, wrap_lines=True, width=Dimension(weight=30)
        )
        preview_window = Window(
            content=self.preview_control, wrap_lines=True, width=Dimension(weight=70)
        )

        menu_frame = Frame(menu_window, width=Dimension(weight=30), title="Browse")
        preview_frame = Frame(
            preview_window, width=Dimension(weight=70), title="Details"
        )

        root_container = VSplit([menu_frame, preview_frame])

        # Key bindings
        kb = KeyBindings()

        @kb.add("up")
        def _(event):
            if self.view_mode == "providers":
                if self.selected_provider_idx > 0:
                    self.selected_provider_idx -= 1
                    self.current_page = self.selected_provider_idx // PAGE_SIZE
            else:  # models view
                if self.selected_model_idx > 0:
                    self.selected_model_idx -= 1
                    self.current_page = self.selected_model_idx // PAGE_SIZE
            self.update_display()

        @kb.add("down")
        def _(event):
            if self.view_mode == "providers":
                if self.selected_provider_idx < len(self.providers) - 1:
                    self.selected_provider_idx += 1
                    self.current_page = self.selected_provider_idx // PAGE_SIZE
            else:  # models view - include custom model option at the end
                # Max index is len(current_models) which is the "Custom model" option
                if self.selected_model_idx < len(self.current_models):
                    self.selected_model_idx += 1
                    self.current_page = self.selected_model_idx // PAGE_SIZE
            self.update_display()

        @kb.add("left")
        def _(event):
            """Previous page."""
            if self.current_page > 0:
                self.current_page -= 1
                # Update selected index to first item on new page
                if self.view_mode == "providers":
                    self.selected_provider_idx = self.current_page * PAGE_SIZE
                else:
                    self.selected_model_idx = self.current_page * PAGE_SIZE
                self.update_display()

        @kb.add("right")
        def _(event):
            """Next page."""
            if self.view_mode == "providers":
                total_items = len(self.providers)
            else:
                total_items = len(self.current_models) + 1  # +1 for custom model option

            total_pages = (total_items + PAGE_SIZE - 1) // PAGE_SIZE
            if self.current_page < total_pages - 1:
                self.current_page += 1
                # Update selected index to first item on new page
                if self.view_mode == "providers":
                    self.selected_provider_idx = self.current_page * PAGE_SIZE
                else:
                    self.selected_model_idx = self.current_page * PAGE_SIZE
                self.update_display()

        @kb.add("enter")
        def _(event):
            if self.view_mode == "providers":
                self._enter_provider()
            elif self.view_mode == "models":
                # Enter adds the model when viewing models
                self._add_current_model()
                event.app.exit()

        @kb.add("escape")
        def _(event):
            if self.view_mode == "models":
                self._go_back_to_providers()

        @kb.add("backspace")
        def _(event):
            if self.view_mode == "models":
                self._go_back_to_providers()

        @kb.add("c-c")
        def _(event):
            event.app.exit()

        layout = Layout(root_container)
        app = Application(
            layout=layout,
            key_bindings=kb,
            full_screen=False,
            mouse_support=False,
        )

        set_awaiting_user_input(True)

        # Enter alternate screen buffer once for entire session
        sys.stdout.write("\033[?1049h")  # Enter alternate buffer
        sys.stdout.write("\033[2J\033[H")  # Clear and home
        sys.stdout.flush()
        time.sleep(0.05)

        try:
            # Initial display
            self.update_display()

            # Just clear the current buffer (don't switch buffers)
            sys.stdout.write("\033[2J\033[H")  # Clear screen within current buffer
            sys.stdout.flush()

            # Run application in a background thread to avoid event loop conflicts
            # This is needed because code_puppy runs in an async context
            app.run(in_thread=True)

        finally:
            # Exit alternate screen buffer once at end
            sys.stdout.write("\033[?1049l")  # Exit alternate buffer
            sys.stdout.flush()
            # Reset awaiting input flag
            set_awaiting_user_input(False)

        # Handle unsupported provider
        if self.result == "unsupported" and self.current_provider:
            reason = UNSUPPORTED_PROVIDERS.get(
                self.current_provider.id, "Not supported"
            )
            emit_error(f"Cannot add model from {self.current_provider.name}: {reason}")
            return False

        # Handle custom model flow after TUI exits
        if self.result == "pending_custom_model" and self.pending_provider:
            # Prompt for custom model details (name and context size)
            custom_model_result = self._prompt_for_custom_model()
            if not custom_model_result:
                return False

            model_name, context_length = custom_model_result

            # Create a ModelInfo for the custom model
            self.pending_model = self._create_custom_model_info(
                model_name, context_length
            )

            # Prompt for any missing credentials
            if self._prompt_for_credentials(self.pending_provider):
                # Now add the model to config
                if self._add_model_to_extra_config(
                    self.pending_model, self.pending_provider
                ):
                    self.result = "added"
                    return True
            return False

        # Handle pending credential flow after TUI exits
        if (
            self.result == "pending_credentials"
            and self.pending_model
            and self.pending_provider
        ):
            # Warn about non-tool-calling models
            if not self.pending_model.tool_call:
                emit_warning(
                    f"⚠️  {self.pending_model.name} does NOT support tool calling!\n"
                    f"   This model won't be able to edit files, run commands, or use any tools.\n"
                    f"   It will be very limited for coding tasks."
                )
                try:
                    confirm = (
                        input("\n  Are you sure you want to add this model? (y/N): ")
                        .strip()
                        .lower()
                    )
                    if confirm not in ("y", "yes"):
                        emit_info("Model addition cancelled.")
                        return False
                except (KeyboardInterrupt, EOFError):
                    emit_info("")
                    return False

            # Prompt for any missing credentials
            if self._prompt_for_credentials(self.pending_provider):
                # Now add the model to config
                if self._add_model_to_extra_config(
                    self.pending_model, self.pending_provider
                ):
                    self.result = "added"
                    return True
            return False

        return self.result == "added"


def interactive_model_picker() -> bool:
    """Show interactive terminal UI to browse and add models.

    Returns:
        True if a model was added, False otherwise
    """
    menu = AddModelMenu()
    return menu.run()
