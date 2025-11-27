"""
Models development API parser for Code Puppy.

This module provides functionality to parse and work with the models.dev API,
including provider and model information, search capabilities, and conversion to Code Puppy
configuration format.

The parser fetches data from the live models.dev API first, falling back to a bundled
JSON file if the API is unavailable.

The parser supports filtering by cost, context length, capabilities, and provides
comprehensive type safety throughout the implementation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from code_puppy.messaging import emit_error, emit_info, emit_warning

# Live API endpoint for models.dev
MODELS_DEV_API_URL = "https://models.dev/api.json"

# Bundled fallback JSON file (relative to this module)
BUNDLED_JSON_FILENAME = "models_dev_api.json"


@dataclass(slots=True)
class ProviderInfo:
    """Information about a model provider."""

    id: str
    name: str
    env: List[str]
    api: str
    npm: Optional[str] = None
    doc: Optional[str] = None
    models: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate provider data after initialization."""
        if not self.id:
            raise ValueError("Provider ID cannot be empty")
        if not self.name:
            raise ValueError("Provider name cannot be empty")

    @property
    def model_count(self) -> int:
        """Get the number of models for this provider."""
        return len(self.models)


@dataclass(slots=True)
class ModelInfo:
    """Information about a specific model."""

    provider_id: str
    model_id: str
    name: str
    attachment: bool = False
    reasoning: bool = False
    tool_call: bool = False
    temperature: bool = False
    structured_output: bool = False
    cost_input: Optional[float] = None
    cost_output: Optional[float] = None
    cost_cache_read: Optional[float] = None
    context_length: int = 0
    max_output: int = 0
    input_modalities: List[str] = field(default_factory=list)
    output_modalities: List[str] = field(default_factory=list)
    knowledge: Optional[str] = None
    release_date: Optional[str] = None
    last_updated: Optional[str] = None
    open_weights: bool = False

    def __post_init__(self) -> None:
        """Validate model data after initialization."""
        if not self.provider_id:
            raise ValueError("Provider ID cannot be empty")
        if not self.model_id:
            raise ValueError("Model ID cannot be empty")
        if not self.name:
            raise ValueError("Model name cannot be empty")
        if self.context_length < 0:
            raise ValueError("Context length cannot be negative")
        if self.max_output < 0:
            raise ValueError("Max output cannot be negative")

    @property
    def full_id(self) -> str:
        """Get the full identifier: provider_id::model_id."""
        return f"{self.provider_id}::{self.model_id}"

    @property
    def has_vision(self) -> bool:
        """Check if the model supports vision capabilities."""
        return "image" in self.input_modalities

    @property
    def is_multimodal(self) -> bool:
        """Check if the model supports multiple modalities."""
        return len(self.input_modalities) > 1 or len(self.output_modalities) > 1

    def supports_capability(self, capability: str) -> bool:
        """Check if model supports a specific capability."""
        return getattr(self, capability, False) is True


class ModelsDevRegistry:
    """Registry for managing models and providers from models.dev API.

    Fetches data from the live models.dev API first, falling back to a bundled
    JSON file if the API is unavailable.
    """

    def __init__(self, json_path: str | Path | None = None) -> None:
        """
        Initialize the registry by fetching from models.dev API or loading bundled JSON.

        Args:
            json_path: Optional path to a local JSON file (for testing/offline use).
                      If None, will try live API first, then bundled fallback.

        Raises:
            FileNotFoundError: If no data source is available
            json.JSONDecodeError: If the data contains invalid JSON
            ValueError: If required fields are missing or malformed
        """
        self.json_path = Path(json_path) if json_path else None
        self.providers: Dict[str, ProviderInfo] = {}
        self.models: Dict[str, ModelInfo] = {}
        self.provider_models: Dict[
            str, List[str]
        ] = {}  # Maps provider_id to list of model IDs
        self.data_source: str = "unknown"  # Track where data came from
        self._load_data()

    def _fetch_from_api(self) -> Optional[Dict[str, Any]]:
        """Fetch data from the live models.dev API.

        Returns:
            Parsed JSON data if successful, None otherwise.
        """
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(MODELS_DEV_API_URL)
                response.raise_for_status()
                data = response.json()
                if isinstance(data, dict) and len(data) > 0:
                    return data
                return None
        except httpx.TimeoutException:
            emit_warning("models.dev API timed out, using bundled fallback")
            return None
        except httpx.HTTPStatusError as e:
            emit_warning(
                f"models.dev API returned {e.response.status_code}, using bundled fallback"
            )
            return None
        except Exception as e:
            emit_warning(
                f"Failed to fetch from models.dev API: {e}, using bundled fallback"
            )
            return None

    def _get_bundled_json_path(self) -> Path:
        """Get the path to the bundled JSON file."""
        return Path(__file__).parent / BUNDLED_JSON_FILENAME

    def _load_data(self) -> None:
        """Load data from API or fallback sources, populating internal data structures."""
        data: Optional[Dict[str, Any]] = None

        # If explicit json_path provided, use that directly (for testing)
        if self.json_path:
            if not self.json_path.exists():
                raise FileNotFoundError(f"Models API file not found: {self.json_path}")
            try:
                with open(self.json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.data_source = f"file:{self.json_path}"
            except json.JSONDecodeError as e:
                emit_error(f"Invalid JSON in {self.json_path}: {e}")
                raise
        else:
            # Try live API first
            data = self._fetch_from_api()
            if data:
                self.data_source = "live:models.dev"
                emit_info("📡 Fetched latest models from models.dev")
            else:
                # Fall back to bundled JSON
                bundled_path = self._get_bundled_json_path()
                if bundled_path.exists():
                    try:
                        with open(bundled_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        self.data_source = f"bundled:{bundled_path.name}"
                        emit_info(
                            "📦 Using bundled models database (models.dev unavailable)"
                        )
                    except json.JSONDecodeError as e:
                        emit_error(f"Invalid JSON in bundled file {bundled_path}: {e}")
                        raise
                else:
                    raise FileNotFoundError(
                        f"No data source available: models.dev API failed and bundled file not found at {bundled_path}"
                    )

        if not isinstance(data, dict):
            raise ValueError("Top-level JSON must be an object")

        # Parse flat structure: {provider_id: {id, name, env, api, npm, doc, models: {model_id: {...}}}}
        for provider_id, provider_data in data.items():
            try:
                provider = self._parse_provider(provider_id, provider_data)
                self.providers[provider_id] = provider
                self.provider_models[provider_id] = []

                # Parse models nested under the provider
                models_data = provider_data.get("models", {})
                if isinstance(models_data, dict):
                    for model_id, model_data in models_data.items():
                        try:
                            model = self._parse_model(provider_id, model_id, model_data)
                            model_key = model.full_id
                            self.models[model_key] = model
                            self.provider_models[provider_id].append(model_id)
                        except Exception as e:
                            emit_warning(
                                f"Skipping malformed model {provider_id}::{model_id}: {e}"
                            )
                            continue

            except Exception as e:
                emit_warning(f"Skipping malformed provider {provider_id}: {e}")
                continue

        emit_info(
            f"Loaded {len(self.providers)} providers and {len(self.models)} models"
        )

    def _parse_provider(self, provider_id: str, data: Dict[str, Any]) -> ProviderInfo:
        """Parse provider data from JSON."""
        # Only name and env are truly required - api is optional for SDK-based providers
        # like Anthropic, OpenAI, Azure that don't need a custom API URL
        required_fields = ["name", "env"]
        missing_fields = [f for f in required_fields if f not in data]
        if missing_fields:
            raise ValueError(f"Missing required fields: {missing_fields}")

        return ProviderInfo(
            id=provider_id,
            name=data["name"],
            env=data["env"],
            api=data.get("api", ""),  # Optional - empty string for SDK-based providers
            npm=data.get("npm"),
            doc=data.get("doc"),
            models=data.get("models", {}),
        )

    def _parse_model(
        self, provider_id: str, model_id: str, data: Dict[str, Any]
    ) -> ModelInfo:
        """Parse model data from JSON."""
        if not data.get("name"):
            raise ValueError("Missing required field: name")

        # Extract cost data from nested dict
        cost_data = data.get("cost", {})
        cost_input = cost_data.get("input")
        cost_output = cost_data.get("output")
        cost_cache_read = cost_data.get("cache_read")

        # Extract limit data from nested dict
        limit_data = data.get("limit", {})
        context_length = limit_data.get("context", 0)
        max_output = limit_data.get("output", 0)

        # Extract modalities from nested dict
        modalities = data.get("modalities", {})
        input_mods = modalities.get("input", [])
        output_mods = modalities.get("output", [])

        return ModelInfo(
            provider_id=provider_id,
            model_id=model_id,
            name=data["name"],
            attachment=data.get("attachment", False),
            reasoning=data.get("reasoning", False),
            tool_call=data.get("tool_call", False),
            temperature=data.get("temperature", True),
            structured_output=data.get("structured_output", False),
            cost_input=cost_input,
            cost_output=cost_output,
            cost_cache_read=cost_cache_read,
            context_length=context_length,
            max_output=max_output,
            input_modalities=input_mods,
            output_modalities=output_mods,
            knowledge=data.get("knowledge"),
            release_date=data.get("release_date"),
            last_updated=data.get("last_updated"),
            open_weights=data.get("open_weights", False),
        )

    def get_providers(self) -> List[ProviderInfo]:
        """
        Get all providers, sorted by name.

        Returns:
            List of ProviderInfo objects sorted by name
        """
        return sorted(self.providers.values(), key=lambda p: p.name.lower())

    def get_provider(self, provider_id: str) -> Optional[ProviderInfo]:
        """
        Get a specific provider by ID.

        Args:
            provider_id: The provider identifier

        Returns:
            ProviderInfo if found, None otherwise
        """
        return self.providers.get(provider_id)

    def get_models(self, provider_id: Optional[str] = None) -> List[ModelInfo]:
        """
        Get models, optionally filtered by provider.

        Args:
            provider_id: Optional provider ID to filter by

        Returns:
            List of ModelInfo objects sorted by name
        """
        if provider_id:
            model_ids = self.provider_models.get(provider_id, [])
            models = [
                self.models[f"{provider_id}::{model_id}"]
                for model_id in model_ids
                if f"{provider_id}::{model_id}" in self.models
            ]
        else:
            models = list(self.models.values())

        return sorted(models, key=lambda m: m.name.lower())

    def get_model(self, provider_id: str, model_id: str) -> Optional[ModelInfo]:
        """
        Get a specific model.

        Args:
            provider_id: The provider identifier
            model_id: The model identifier

        Returns:
            ModelInfo if found, None otherwise
        """
        full_id = f"{provider_id}::{model_id}"
        return self.models.get(full_id)

    def search_models(
        self,
        query: Optional[str] = None,
        capability_filters: Optional[Dict[str, Any]] = None,
    ) -> List[ModelInfo]:
        """
        Search models by name/query and filter by capabilities.

        Args:
            query: Optional search string (case-insensitive)
            capability_filters: Optional capability filters (e.g., {"vision": True})

        Returns:
            List of matching ModelInfo objects
        """
        models = list(self.models.values())

        # Filter by query
        if query:
            query_lower = query.lower()
            models = [
                m
                for m in models
                if query_lower in m.name.lower() or query_lower in m.model_id.lower()
            ]

        # Filter by capabilities
        if capability_filters:
            for capability, required in capability_filters.items():
                if isinstance(required, bool):
                    models = [
                        m
                        for m in models
                        if m.supports_capability(capability) == required
                    ]
                else:
                    # Handle other capability filter types if needed
                    models = [
                        m for m in models if getattr(m, capability, None) == required
                    ]

        return sorted(models, key=lambda m: m.name.lower())

    def filter_by_cost(
        self,
        models: List[ModelInfo],
        max_input_cost: Optional[float] = None,
        max_output_cost: Optional[float] = None,
    ) -> List[ModelInfo]:
        """
        Filter models by cost constraints.

        Args:
            models: List of models to filter
            max_input_cost: Maximum input cost per token (optional)
            max_output_cost: Maximum output cost per token (optional)

        Returns:
            Filtered list of models within cost constraints
        """
        filtered_models = models

        if max_input_cost is not None:
            filtered_models = [
                m
                for m in filtered_models
                if m.cost_input is not None and m.cost_input <= max_input_cost
            ]

        if max_output_cost is not None:
            filtered_models = [
                m
                for m in filtered_models
                if m.cost_output is not None and m.cost_output <= max_output_cost
            ]

        return filtered_models

    def filter_by_context(
        self, models: List[ModelInfo], min_context_length: int
    ) -> List[ModelInfo]:
        """
        Filter models by minimum context length.

        Args:
            models: List of models to filter
            min_context_length: Minimum context length requirement

        Returns:
            Filtered list of models meeting context requirement
        """
        return [m for m in models if m.context_length >= min_context_length]


# Provider type mapping for Code Puppy configuration
PROVIDER_TYPE_MAP = {
    "anthropic": "anthropic",
    "openai": "openai",
    "google": "gemini",
    "deepseek": "deepseek",
    "ollama": "ollama",
    "groq": "groq",
    "cohere": "cohere",
    "mistral": "mistral",
}


def convert_to_code_puppy_config(
    model: ModelInfo, provider: ProviderInfo
) -> Dict[str, Any]:
    """
    Convert a model and provider to Code Puppy configuration format.

    Args:
        model: ModelInfo object
        provider: ProviderInfo object

    Returns:
        Dictionary in Code Puppy configuration format

    Raises:
        ValueError: If required configuration fields are missing
    """
    # Determine provider type
    provider_type = PROVIDER_TYPE_MAP.get(provider.id, provider.id)

    # Basic configuration
    config = {
        "type": provider_type,
        "model": model.model_id,
        "enabled": True,
        "provider_id": provider.id,
        "env_vars": provider.env,
    }

    # Add optional fields if available
    if provider.api:
        config["api_url"] = provider.api
    if provider.npm:
        config["npm_package"] = provider.npm

    # Add cost information
    if model.cost_input is not None:
        config["input_cost_per_token"] = model.cost_input
    if model.cost_output is not None:
        config["output_cost_per_token"] = model.cost_output
    if model.cost_cache_read is not None:
        config["cache_read_cost_per_token"] = model.cost_cache_read

    # Add limits
    if model.context_length > 0:
        config["max_tokens"] = model.context_length
    if model.max_output > 0:
        config["max_output_tokens"] = model.max_output

    # Add capabilities
    capabilities = {
        "attachment": model.attachment,
        "reasoning": model.reasoning,
        "tool_call": model.tool_call,
        "temperature": model.temperature,
        "structured_output": model.structured_output,
    }
    config["capabilities"] = capabilities

    # Add modalities
    if model.input_modalities:
        config["input_modalities"] = model.input_modalities
    if model.output_modalities:
        config["output_modalities"] = model.output_modalities

    # Add metadata
    metadata = {}
    if model.knowledge:
        metadata["knowledge"] = model.knowledge
    if model.release_date:
        metadata["release_date"] = model.release_date
    if model.last_updated:
        metadata["last_updated"] = model.last_updated
    metadata["open_weights"] = model.open_weights

    if metadata:
        config["metadata"] = metadata

    return config


# Example usage
if __name__ == "__main__":
    # This is for testing purposes
    try:
        registry = ModelsDevRegistry()

        # Example: Get all providers
        providers = registry.get_providers()
        emit_info(f"Loaded {len(providers)} providers")

        # Example: Search for vision models
        vision_models = registry.search_models()
        vision_models = [m for m in vision_models if m.has_vision]
        emit_info(f"Found {len(vision_models)} vision models")

        # Example: Filter by cost
        affordable_models = registry.filter_by_cost(
            registry.get_models(), max_input_cost=0.001
        )
        emit_info(f"Found {len(affordable_models)} affordable models")

        # Example: Convert to Code Puppy config
        if providers and registry.get_models():
            provider = providers[0]
            models = registry.get_models(provider.id)
            if models:
                config = convert_to_code_puppy_config(models[0], provider)
                emit_info(f"Example config created for {models[0].name}")

        # Show data source
        emit_info(f"Data source: {registry.data_source}")

    except FileNotFoundError as e:
        emit_error(f"No data source available: {e}")
    except Exception as e:
        emit_error(f"Error loading models: {e}")
