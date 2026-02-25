"""
Comprehensive tests for the models_dev_parser module.

Covers:
- ProviderInfo dataclass validation and properties
- ModelInfo dataclass validation and properties
- ModelsDevRegistry initialization, data loading, and searching
- API fetching and fallback mechanisms
- Model parsing and filtering
- Code Puppy configuration conversion
- Edge cases and error handling
"""

import json
from unittest.mock import MagicMock, mock_open, patch

import httpx
import pytest

from code_puppy.models_dev_parser import (
    ModelInfo,
    ModelsDevRegistry,
    ProviderInfo,
    convert_to_code_puppy_config,
)


class TestProviderInfo:
    """Tests for ProviderInfo dataclass."""

    def test_provider_creation_valid(self):
        """Test creating a valid provider."""
        provider = ProviderInfo(
            id="anthropic",
            name="Anthropic",
            env=["ANTHROPIC_API_KEY"],
            api="",
            npm=None,
            doc=None,
        )
        assert provider.id == "anthropic"
        assert provider.name == "Anthropic"
        assert provider.env == ["ANTHROPIC_API_KEY"]
        assert provider.model_count == 0

    def test_provider_creation_with_models(self):
        """Test provider with initial models."""
        models_dict = {"claude-3-sonnet": {"name": "Claude 3 Sonnet"}}
        provider = ProviderInfo(
            id="anthropic",
            name="Anthropic",
            env=["ANTHROPIC_API_KEY"],
            api="",
            models=models_dict,
        )
        assert provider.model_count == 1

    def test_provider_validation_empty_id(self):
        """Test validation fails with empty provider ID."""
        with pytest.raises(ValueError, match="Provider ID cannot be empty"):
            ProviderInfo(
                id="",
                name="Anthropic",
                env=["ANTHROPIC_API_KEY"],
                api="",
            )

    def test_provider_validation_empty_name(self):
        """Test validation fails with empty name."""
        with pytest.raises(ValueError, match="Provider name cannot be empty"):
            ProviderInfo(
                id="anthropic",
                name="",
                env=["ANTHROPIC_API_KEY"],
                api="",
            )

    def test_provider_with_npm_and_doc(self):
        """Test provider with optional npm and doc fields."""
        provider = ProviderInfo(
            id="ollama",
            name="Ollama",
            env=["OLLAMA_API_BASE"],
            api="http://localhost:11434",
            npm="@ollama/sdk",
            doc="https://ollama.ai",
        )
        assert provider.npm == "@ollama/sdk"
        assert provider.doc == "https://ollama.ai"


class TestModelInfo:
    """Tests for ModelInfo dataclass."""

    def test_model_creation_minimal(self):
        """Test creating model with minimal required fields."""
        model = ModelInfo(
            provider_id="anthropic",
            model_id="claude-3-sonnet",
            name="Claude 3 Sonnet",
        )
        assert model.provider_id == "anthropic"
        assert model.model_id == "claude-3-sonnet"
        assert model.name == "Claude 3 Sonnet"
        assert model.context_length == 0
        assert model.max_output == 0

    def test_model_full_id_property(self):
        """Test full_id property returns correct format."""
        model = ModelInfo(
            provider_id="anthropic",
            model_id="claude-3-sonnet",
            name="Claude 3 Sonnet",
        )
        assert model.full_id == "anthropic::claude-3-sonnet"

    def test_model_has_vision_with_image_modality(self):
        """Test has_vision property when image modality is present."""
        model = ModelInfo(
            provider_id="openai",
            model_id="gpt-4-vision",
            name="GPT-4 Vision",
            input_modalities=["text", "image"],
        )
        assert model.has_vision is True

    def test_model_has_vision_without_image_modality(self):
        """Test has_vision property when image modality is absent."""
        model = ModelInfo(
            provider_id="openai",
            model_id="gpt-4",
            name="GPT-4",
            input_modalities=["text"],
        )
        assert model.has_vision is False

    def test_model_is_multimodal_multiple_input_modalities(self):
        """Test is_multimodal with multiple input modalities."""
        model = ModelInfo(
            provider_id="openai",
            model_id="gpt-4-vision",
            name="GPT-4 Vision",
            input_modalities=["text", "image"],
        )
        assert model.is_multimodal is True

    def test_model_is_multimodal_multiple_output_modalities(self):
        """Test is_multimodal with multiple output modalities."""
        model = ModelInfo(
            provider_id="openai",
            model_id="gpt-4",
            name="GPT-4",
            output_modalities=["text", "image"],
        )
        assert model.is_multimodal is True

    def test_model_is_not_multimodal(self):
        """Test is_multimodal when model has single modality."""
        model = ModelInfo(
            provider_id="openai",
            model_id="gpt-4",
            name="GPT-4",
            input_modalities=["text"],
            output_modalities=["text"],
        )
        assert model.is_multimodal is False

    def test_model_supports_capability_true(self):
        """Test supports_capability when capability is True."""
        model = ModelInfo(
            provider_id="anthropic",
            model_id="claude-3-opus",
            name="Claude 3 Opus",
            tool_call=True,
        )
        assert model.supports_capability("tool_call") is True

    def test_model_supports_capability_false(self):
        """Test supports_capability when capability is False."""
        model = ModelInfo(
            provider_id="openai",
            model_id="gpt-3.5-turbo",
            name="GPT-3.5 Turbo",
            tool_call=False,
        )
        assert model.supports_capability("tool_call") is False

    def test_model_supports_capability_nonexistent(self):
        """Test supports_capability with nonexistent attribute."""
        model = ModelInfo(
            provider_id="openai",
            model_id="gpt-4",
            name="GPT-4",
        )
        assert model.supports_capability("nonexistent") is False

    def test_model_validation_empty_provider_id(self):
        """Test validation fails with empty provider_id."""
        with pytest.raises(ValueError, match="Provider ID cannot be empty"):
            ModelInfo(
                provider_id="",
                model_id="claude-3",
                name="Claude 3",
            )

    def test_model_validation_empty_model_id(self):
        """Test validation fails with empty model_id."""
        with pytest.raises(ValueError, match="Model ID cannot be empty"):
            ModelInfo(
                provider_id="anthropic",
                model_id="",
                name="Claude 3",
            )

    def test_model_validation_empty_name(self):
        """Test validation fails with empty name."""
        with pytest.raises(ValueError, match="Model name cannot be empty"):
            ModelInfo(
                provider_id="anthropic",
                model_id="claude-3",
                name="",
            )

    def test_model_validation_negative_context_length(self):
        """Test validation fails with negative context_length."""
        with pytest.raises(ValueError, match="Context length cannot be negative"):
            ModelInfo(
                provider_id="anthropic",
                model_id="claude-3",
                name="Claude 3",
                context_length=-100,
            )

    def test_model_validation_negative_max_output(self):
        """Test validation fails with negative max_output."""
        with pytest.raises(ValueError, match="Max output cannot be negative"):
            ModelInfo(
                provider_id="anthropic",
                model_id="claude-3",
                name="Claude 3",
                max_output=-50,
            )

    def test_model_with_all_capabilities(self):
        """Test model with all capabilities enabled."""
        model = ModelInfo(
            provider_id="anthropic",
            model_id="claude-3-opus",
            name="Claude 3 Opus",
            attachment=True,
            reasoning=True,
            tool_call=True,
            temperature=True,
            structured_output=True,
        )
        assert model.attachment is True
        assert model.reasoning is True
        assert model.tool_call is True
        assert model.temperature is True
        assert model.structured_output is True

    def test_model_with_cost_data(self):
        """Test model with cost information."""
        model = ModelInfo(
            provider_id="anthropic",
            model_id="claude-3-sonnet",
            name="Claude 3 Sonnet",
            cost_input=0.003,
            cost_output=0.015,
            cost_cache_read=0.00075,
        )
        assert model.cost_input == 0.003
        assert model.cost_output == 0.015
        assert model.cost_cache_read == 0.00075

    def test_model_with_metadata(self):
        """Test model with knowledge and date metadata."""
        model = ModelInfo(
            provider_id="openai",
            model_id="gpt-4",
            name="GPT-4",
            knowledge="April 2024",
            release_date="2023-03-14",
            last_updated="2024-04-15",
            open_weights=False,
        )
        assert model.knowledge == "April 2024"
        assert model.release_date == "2023-03-14"
        assert model.last_updated == "2024-04-15"
        assert model.open_weights is False


class TestModelsDevRegistryAPIFetching:
    """Tests for API fetching and data loading."""

    @patch("code_puppy.models_dev_parser.httpx.Client")
    def test_fetch_from_api_success(
        self,
        mock_client_class,
    ):
        """Test successful API fetch."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        api_data = {
            "anthropic": {
                "name": "Anthropic",
                "env": ["ANTHROPIC_API_KEY"],
                "api": "",
                "models": {
                    "claude-3-opus": {
                        "name": "Claude 3 Opus",
                        "cost": {"input": 0.015, "output": 0.075},
                    }
                },
            }
        }

        response = MagicMock()
        response.json.return_value = api_data
        mock_client.get.return_value = response

        registry = ModelsDevRegistry()
        assert registry.data_source == "live:models.dev"
        assert len(registry.providers) == 1
        assert "anthropic" in registry.providers

    @patch("code_puppy.models_dev_parser.httpx.Client")
    def test_fetch_from_api_timeout(
        self,
        mock_client_class,
    ):
        """Test API timeout falls back to bundled JSON."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.get.side_effect = httpx.TimeoutException(
            "Request timeout",
        )

        # Mock the bundled JSON file
        bundled_data = {
            "openai": {
                "name": "OpenAI",
                "env": ["OPENAI_API_KEY"],
                "api": "https://api.openai.com/v1",
                "models": {},
            }
        }

        with patch(
            "builtins.open",
            mock_open(read_data=json.dumps(bundled_data)),
        ):
            with patch("pathlib.Path.exists", return_value=True):
                registry = ModelsDevRegistry()
                assert "bundled:" in registry.data_source

    @patch("code_puppy.models_dev_parser.httpx.Client")
    def test_fetch_from_api_http_error(
        self,
        mock_client_class,
    ):
        """Test API HTTP error falls back to bundled JSON."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        response = MagicMock()
        response.status_code = 500
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server error",
            request=MagicMock(),
            response=response,
        )
        mock_client.get.return_value = response

        bundled_data = {
            "openai": {"name": "OpenAI", "env": [], "api": "", "models": {}}
        }

        with patch(
            "builtins.open",
            mock_open(read_data=json.dumps(bundled_data)),
        ):
            with patch("pathlib.Path.exists", return_value=True):
                registry = ModelsDevRegistry()
                assert "bundled:" in registry.data_source

    @patch("code_puppy.models_dev_parser.httpx.Client")
    def test_fetch_from_api_general_exception(
        self,
        mock_client_class,
    ):
        """Test general exception during API fetch falls back to bundled."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.get.side_effect = RuntimeError("Connection failed")

        bundled_data = {
            "openai": {"name": "OpenAI", "env": [], "api": "", "models": {}}
        }

        with patch(
            "builtins.open",
            mock_open(read_data=json.dumps(bundled_data)),
        ):
            with patch("pathlib.Path.exists", return_value=True):
                registry = ModelsDevRegistry()
                assert "bundled:" in registry.data_source


class TestModelsDevRegistryDataLoading:
    """Tests for data loading and parsing."""

    def test_load_data_with_explicit_json_path(self):
        """Test loading data from explicit JSON path."""
        data = {
            "anthropic": {
                "name": "Anthropic",
                "env": ["ANTHROPIC_API_KEY"],
                "api": "",
                "models": {
                    "claude-3-opus": {
                        "name": "Claude 3 Opus",
                        "cost": {"input": 0.015, "output": 0.075},
                        "limit": {"context": 200000, "output": 4096},
                    }
                },
            }
        }

        with patch(
            "builtins.open",
            mock_open(read_data=json.dumps(data)),
        ):
            with patch("pathlib.Path.exists", return_value=True):
                registry = ModelsDevRegistry(json_path="/tmp/models.json")
                assert "file:" in registry.data_source
                assert len(registry.providers) == 1
                assert "anthropic" in registry.providers
                assert len(registry.models) == 1

    def test_load_data_file_not_found(self):
        """Test FileNotFoundError when json_path doesn't exist."""
        with patch("pathlib.Path.exists", return_value=False):
            with pytest.raises(FileNotFoundError):
                ModelsDevRegistry(json_path="/nonexistent/models.json")

    def test_load_data_invalid_json(self):
        """Test JSONDecodeError with invalid JSON."""
        with patch(
            "builtins.open",
            mock_open(read_data="{invalid json}"),
        ):
            with patch("pathlib.Path.exists", return_value=True):
                with pytest.raises(json.JSONDecodeError):
                    ModelsDevRegistry(json_path="/tmp/models.json")

    def test_load_data_top_level_not_object(self):
        """Test ValueError when top-level JSON is not an object."""
        with patch(
            "builtins.open",
            mock_open(read_data=json.dumps(["not", "an", "object"])),
        ):
            with patch("pathlib.Path.exists", return_value=True):
                with pytest.raises(
                    ValueError, match="Top-level JSON must be an object"
                ):
                    ModelsDevRegistry(json_path="/tmp/models.json")

    def test_load_data_malformed_provider(self):
        """Test that malformed provider is skipped gracefully."""
        data = {
            "valid_provider": {
                "name": "Valid Provider",
                "env": ["API_KEY"],
                "api": "",
                "models": {},
            },
            "missing_name": {
                "env": ["API_KEY"],  # Missing 'name'
                "api": "",
                "models": {},
            },
        }

        with patch(
            "builtins.open",
            mock_open(read_data=json.dumps(data)),
        ):
            with patch("pathlib.Path.exists", return_value=True):
                registry = ModelsDevRegistry(json_path="/tmp/models.json")
                assert len(registry.providers) == 1
                assert "valid_provider" in registry.providers

    def test_load_data_malformed_model(self):
        """Test that malformed model is skipped gracefully."""
        data = {
            "anthropic": {
                "name": "Anthropic",
                "env": ["ANTHROPIC_API_KEY"],
                "api": "",
                "models": {
                    "claude-3-opus": {
                        "name": "Claude 3 Opus",
                    },
                    "missing-name": {
                        # Missing 'name' field
                    },
                },
            }
        }

        with patch(
            "builtins.open",
            mock_open(read_data=json.dumps(data)),
        ):
            with patch("pathlib.Path.exists", return_value=True):
                registry = ModelsDevRegistry(json_path="/tmp/models.json")
                assert len(registry.models) == 1
                assert "anthropic::claude-3-opus" in registry.models


class TestModelsDevRegistryParsing:
    """Tests for provider and model parsing."""

    def test_parse_provider_minimal(self):
        """Test parsing provider with minimal required fields."""
        data = {
            "anthropic": {
                "name": "Anthropic",
                "env": ["ANTHROPIC_API_KEY"],
                "api": "",
                "models": {},
            }
        }

        with patch(
            "builtins.open",
            mock_open(read_data=json.dumps(data)),
        ):
            with patch("pathlib.Path.exists", return_value=True):
                registry = ModelsDevRegistry(json_path="/tmp/models.json")
                provider = registry.get_provider("anthropic")
                assert provider is not None
                assert provider.id == "anthropic"
                assert provider.name == "Anthropic"
                assert provider.api == ""

    def test_parse_provider_with_npm_and_doc(self):
        """Test parsing provider with npm and doc fields."""
        data = {
            "ollama": {
                "name": "Ollama",
                "env": ["OLLAMA_API_BASE"],
                "api": "http://localhost:11434",
                "npm": "@ollama/sdk",
                "doc": "https://ollama.ai",
                "models": {},
            }
        }

        with patch(
            "builtins.open",
            mock_open(read_data=json.dumps(data)),
        ):
            with patch("pathlib.Path.exists", return_value=True):
                registry = ModelsDevRegistry(json_path="/tmp/models.json")
                provider = registry.get_provider("ollama")
                assert provider.npm == "@ollama/sdk"
                assert provider.doc == "https://ollama.ai"

    def test_parse_model_with_nested_cost(self):
        """Test parsing model with nested cost structure."""
        data = {
            "anthropic": {
                "name": "Anthropic",
                "env": ["ANTHROPIC_API_KEY"],
                "api": "",
                "models": {
                    "claude-3-opus": {
                        "name": "Claude 3 Opus",
                        "cost": {
                            "input": 0.015,
                            "output": 0.075,
                            "cache_read": 0.00375,
                        },
                    }
                },
            }
        }

        with patch(
            "builtins.open",
            mock_open(read_data=json.dumps(data)),
        ):
            with patch("pathlib.Path.exists", return_value=True):
                registry = ModelsDevRegistry(json_path="/tmp/models.json")
                model = registry.get_model("anthropic", "claude-3-opus")
                assert model.cost_input == 0.015
                assert model.cost_output == 0.075
                assert model.cost_cache_read == 0.00375

    def test_parse_model_with_nested_limits(self):
        """Test parsing model with nested limit structure."""
        data = {
            "anthropic": {
                "name": "Anthropic",
                "env": ["ANTHROPIC_API_KEY"],
                "api": "",
                "models": {
                    "claude-3-opus": {
                        "name": "Claude 3 Opus",
                        "limit": {
                            "context": 200000,
                            "output": 4096,
                        },
                    }
                },
            }
        }

        with patch(
            "builtins.open",
            mock_open(read_data=json.dumps(data)),
        ):
            with patch("pathlib.Path.exists", return_value=True):
                registry = ModelsDevRegistry(json_path="/tmp/models.json")
                model = registry.get_model("anthropic", "claude-3-opus")
                assert model.context_length == 200000
                assert model.max_output == 4096

    def test_parse_model_with_modalities(self):
        """Test parsing model with input/output modalities."""
        data = {
            "openai": {
                "name": "OpenAI",
                "env": ["OPENAI_API_KEY"],
                "api": "https://api.openai.com/v1",
                "models": {
                    "gpt-4-vision": {
                        "name": "GPT-4 Vision",
                        "modalities": {
                            "input": ["text", "image"],
                            "output": ["text"],
                        },
                    }
                },
            }
        }

        with patch(
            "builtins.open",
            mock_open(read_data=json.dumps(data)),
        ):
            with patch("pathlib.Path.exists", return_value=True):
                registry = ModelsDevRegistry(json_path="/tmp/models.json")
                model = registry.get_model("openai", "gpt-4-vision")
                assert model.input_modalities == ["text", "image"]
                assert model.output_modalities == ["text"]

    def test_parse_model_capabilities(self):
        """Test parsing model with various capabilities."""
        data = {
            "anthropic": {
                "name": "Anthropic",
                "env": ["ANTHROPIC_API_KEY"],
                "api": "",
                "models": {
                    "claude-3-opus": {
                        "name": "Claude 3 Opus",
                        "attachment": True,
                        "reasoning": True,
                        "tool_call": True,
                        "temperature": True,
                        "structured_output": True,
                    }
                },
            }
        }

        with patch(
            "builtins.open",
            mock_open(read_data=json.dumps(data)),
        ):
            with patch("pathlib.Path.exists", return_value=True):
                registry = ModelsDevRegistry(json_path="/tmp/models.json")
                model = registry.get_model("anthropic", "claude-3-opus")
                assert model.attachment is True
                assert model.reasoning is True
                assert model.tool_call is True
                assert model.temperature is True
                assert model.structured_output is True

    def test_parse_model_metadata(self):
        """Test parsing model with metadata fields."""
        data = {
            "openai": {
                "name": "OpenAI",
                "env": ["OPENAI_API_KEY"],
                "api": "https://api.openai.com/v1",
                "models": {
                    "gpt-4": {
                        "name": "GPT-4",
                        "knowledge": "April 2024",
                        "release_date": "2023-03-14",
                        "last_updated": "2024-04-15",
                        "open_weights": False,
                    }
                },
            }
        }

        with patch(
            "builtins.open",
            mock_open(read_data=json.dumps(data)),
        ):
            with patch("pathlib.Path.exists", return_value=True):
                registry = ModelsDevRegistry(json_path="/tmp/models.json")
                model = registry.get_model("openai", "gpt-4")
                assert model.knowledge == "April 2024"
                assert model.release_date == "2023-03-14"
                assert model.last_updated == "2024-04-15"
                assert model.open_weights is False


class TestModelsDevRegistryQuerying:
    """Tests for registry querying and retrieval methods."""

    @pytest.fixture
    def sample_registry(self):
        """Fixture providing a populated registry for testing."""
        data = {
            "anthropic": {
                "name": "Anthropic",
                "env": ["ANTHROPIC_API_KEY"],
                "api": "",
                "models": {
                    "claude-3-opus": {
                        "name": "Claude 3 Opus",
                        "cost": {"input": 0.015, "output": 0.075},
                        "tool_call": True,
                    },
                    "claude-3-sonnet": {
                        "name": "Claude 3 Sonnet",
                        "cost": {"input": 0.003, "output": 0.015},
                    },
                },
            },
            "openai": {
                "name": "OpenAI",
                "env": ["OPENAI_API_KEY"],
                "api": "https://api.openai.com/v1",
                "models": {
                    "gpt-4": {
                        "name": "GPT-4",
                        "cost": {"input": 0.03, "output": 0.06},
                        "limit": {"context": 8000},
                        "modalities": {"input": ["text"], "output": ["text"]},
                    },
                    "gpt-4-vision": {
                        "name": "GPT-4 Vision",
                        "cost": {"input": 0.01, "output": 0.03},
                        "limit": {"context": 128000},
                        "modalities": {"input": ["text", "image"], "output": ["text"]},
                    },
                },
            },
        }

        with patch(
            "builtins.open",
            mock_open(read_data=json.dumps(data)),
        ):
            with patch("pathlib.Path.exists", return_value=True):
                return ModelsDevRegistry(json_path="/tmp/models.json")

    def test_get_providers(self, sample_registry):
        """Test getting all providers sorted by name."""
        providers = sample_registry.get_providers()
        assert len(providers) == 2
        assert providers[0].name == "Anthropic"
        assert providers[1].name == "OpenAI"

    def test_get_provider_exists(self, sample_registry):
        """Test getting a specific provider that exists."""
        provider = sample_registry.get_provider("anthropic")
        assert provider is not None
        assert provider.name == "Anthropic"

    def test_get_provider_not_exists(self, sample_registry):
        """Test getting a provider that doesn't exist."""
        provider = sample_registry.get_provider("nonexistent")
        assert provider is None

    def test_get_models_all(self, sample_registry):
        """Test getting all models."""
        models = sample_registry.get_models()
        assert len(models) == 4
        # Should be sorted by name
        assert models[0].name == "Claude 3 Opus"

    def test_get_models_by_provider(self, sample_registry):
        """Test getting models filtered by provider."""
        models = sample_registry.get_models(provider_id="anthropic")
        assert len(models) == 2
        assert all(m.provider_id == "anthropic" for m in models)

    def test_get_models_by_provider_empty(self, sample_registry):
        """Test getting models for provider with no models."""
        # Create a provider without models
        empty_provider_data = {
            "empty_provider": {
                "name": "Empty Provider",
                "env": ["API_KEY"],
                "api": "",
                "models": {},
            }
        }

        with patch(
            "builtins.open",
            mock_open(read_data=json.dumps(empty_provider_data)),
        ):
            with patch("pathlib.Path.exists", return_value=True):
                registry = ModelsDevRegistry(json_path="/tmp/models.json")
                models = registry.get_models(provider_id="empty_provider")
                assert len(models) == 0

    def test_get_model_exists(self, sample_registry):
        """Test getting a specific model that exists."""
        model = sample_registry.get_model("anthropic", "claude-3-opus")
        assert model is not None
        assert model.name == "Claude 3 Opus"
        assert model.cost_input == 0.015

    def test_get_model_not_exists(self, sample_registry):
        """Test getting a model that doesn't exist."""
        model = sample_registry.get_model("anthropic", "nonexistent")
        assert model is None


class TestModelsDevRegistrySearch:
    """Tests for model searching and filtering."""

    @pytest.fixture
    def sample_registry(self):
        """Fixture providing a populated registry for testing."""
        data = {
            "anthropic": {
                "name": "Anthropic",
                "env": ["ANTHROPIC_API_KEY"],
                "api": "",
                "models": {
                    "claude-3-opus": {
                        "name": "Claude 3 Opus",
                        "cost": {"input": 0.015, "output": 0.075},
                        "tool_call": True,
                        "reasoning": True,
                    },
                    "claude-3-sonnet": {
                        "name": "Claude 3 Sonnet",
                        "cost": {"input": 0.003, "output": 0.015},
                    },
                },
            },
            "openai": {
                "name": "OpenAI",
                "env": ["OPENAI_API_KEY"],
                "api": "https://api.openai.com/v1",
                "models": {
                    "gpt-4-vision": {
                        "name": "GPT-4 Vision",
                        "modalities": {"input": ["text", "image"]},
                        "tool_call": True,
                    },
                },
            },
        }

        with patch(
            "builtins.open",
            mock_open(read_data=json.dumps(data)),
        ):
            with patch("pathlib.Path.exists", return_value=True):
                return ModelsDevRegistry(json_path="/tmp/models.json")

    def test_search_models_by_query_name(self, sample_registry):
        """Test searching models by name query."""
        results = sample_registry.search_models(query="claude")
        assert len(results) == 2
        assert all("claude" in m.name.lower() for m in results)

    def test_search_models_by_query_model_id(self, sample_registry):
        """Test searching models by model_id."""
        results = sample_registry.search_models(query="gpt")
        assert len(results) == 1
        assert results[0].model_id == "gpt-4-vision"

    def test_search_models_case_insensitive(self, sample_registry):
        """Test search is case-insensitive."""
        results_lower = sample_registry.search_models(query="claude")
        results_upper = sample_registry.search_models(query="CLAUDE")
        assert len(results_lower) == len(results_upper)

    def test_search_models_no_results(self, sample_registry):
        """Test search with no matching results."""
        results = sample_registry.search_models(query="nonexistent")
        assert len(results) == 0

    def test_search_models_by_capability(self, sample_registry):
        """Test filtering models by capability."""
        results = sample_registry.search_models(capability_filters={"tool_call": True})
        assert len(results) == 2
        assert all(m.tool_call is True for m in results)

    def test_search_models_by_multiple_capabilities(self, sample_registry):
        """Test filtering by multiple capabilities."""
        results = sample_registry.search_models(
            capability_filters={"tool_call": True, "reasoning": True}
        )
        assert len(results) == 1
        assert results[0].model_id == "claude-3-opus"

    def test_search_models_capability_false_filter(self, sample_registry):
        """Test filtering for models without a capability."""
        results = sample_registry.search_models(capability_filters={"reasoning": False})
        # Should include sonnet and gpt-4-vision
        assert len(results) >= 2

    def test_search_models_combined_query_and_capability(self, sample_registry):
        """Test combining query and capability filters."""
        results = sample_registry.search_models(
            query="claude", capability_filters={"tool_call": True}
        )
        assert len(results) == 1
        assert results[0].model_id == "claude-3-opus"

    def test_filter_by_cost_input(self, sample_registry):
        """Test filtering models by input cost."""
        all_models = sample_registry.get_models()
        filtered = sample_registry.filter_by_cost(all_models, max_input_cost=0.01)
        assert len(filtered) >= 1
        assert all(m.cost_input <= 0.01 for m in filtered if m.cost_input)

    def test_filter_by_cost_output(self, sample_registry):
        """Test filtering models by output cost."""
        all_models = sample_registry.get_models()
        filtered = sample_registry.filter_by_cost(all_models, max_output_cost=0.05)
        assert all(m.cost_output <= 0.05 for m in filtered if m.cost_output)

    def test_filter_by_cost_both(self, sample_registry):
        """Test filtering models by both input and output cost."""
        all_models = sample_registry.get_models()
        filtered = sample_registry.filter_by_cost(
            all_models, max_input_cost=0.01, max_output_cost=0.05
        )
        assert all(m.cost_input <= 0.01 for m in filtered if m.cost_input)
        assert all(m.cost_output <= 0.05 for m in filtered if m.cost_output)

    def test_filter_by_cost_none_values(self, sample_registry):
        """Test filtering handles None cost values correctly."""
        # Create model with missing cost data
        data = {
            "test_provider": {
                "name": "Test",
                "env": ["API_KEY"],
                "api": "",
                "models": {
                    "test-model": {
                        "name": "Test Model",
                        # No cost data
                    }
                },
            }
        }

        with patch(
            "builtins.open",
            mock_open(read_data=json.dumps(data)),
        ):
            with patch("pathlib.Path.exists", return_value=True):
                registry = ModelsDevRegistry(json_path="/tmp/models.json")
                all_models = registry.get_models()
                filtered = registry.filter_by_cost(all_models, max_input_cost=0.01)
                # Model with None cost_input should be excluded
                assert len(filtered) == 0

    def test_filter_by_context(self, sample_registry):
        """Test filtering models by context length."""
        # Add model with large context
        data = {
            "anthropic": {
                "name": "Anthropic",
                "env": ["ANTHROPIC_API_KEY"],
                "api": "",
                "models": {
                    "claude-3-opus": {
                        "name": "Claude 3 Opus",
                        "limit": {"context": 200000},
                    },
                    "claude-3-sonnet": {
                        "name": "Claude 3 Sonnet",
                        "limit": {"context": 200000},
                    },
                },
            }
        }

        with patch(
            "builtins.open",
            mock_open(read_data=json.dumps(data)),
        ):
            with patch("pathlib.Path.exists", return_value=True):
                registry = ModelsDevRegistry(json_path="/tmp/models.json")
                all_models = registry.get_models()
                filtered = registry.filter_by_context(
                    all_models, min_context_length=100000
                )
                assert len(filtered) == 2
                assert all(m.context_length >= 100000 for m in filtered)

    def test_filter_by_context_no_matches(self, sample_registry):
        """Test context filter with no matching models."""
        all_models = sample_registry.get_models()
        filtered = sample_registry.filter_by_context(
            all_models, min_context_length=1000000
        )
        assert len(filtered) == 0


class TestConvertToCodePuppyConfig:
    """Tests for Code Puppy configuration conversion."""

    @pytest.fixture
    def sample_data(self):
        """Create sample provider and model for testing."""
        provider = ProviderInfo(
            id="anthropic",
            name="Anthropic",
            env=["ANTHROPIC_API_KEY"],
            api="",
        )
        model = ModelInfo(
            provider_id="anthropic",
            model_id="claude-3-opus",
            name="Claude 3 Opus",
            cost_input=0.015,
            cost_output=0.075,
            cost_cache_read=0.00375,
            context_length=200000,
            max_output=4096,
            attachment=True,
            reasoning=True,
            tool_call=True,
            temperature=True,
            structured_output=False,
            input_modalities=["text"],
            output_modalities=["text"],
            knowledge="April 2024",
            release_date="2023-03-14",
            last_updated="2024-04-15",
            open_weights=False,
        )
        return provider, model

    def test_convert_basic(self, sample_data):
        """Test basic conversion to Code Puppy config."""
        provider, model = sample_data
        config = convert_to_code_puppy_config(model, provider)

        assert config["type"] == "anthropic"
        assert config["model"] == "claude-3-opus"
        assert config["enabled"] is True
        assert config["provider_id"] == "anthropic"
        assert "ANTHROPIC_API_KEY" in config["env_vars"]

    def test_convert_with_api_url(self):
        """Test conversion includes API URL when present."""
        provider = ProviderInfo(
            id="ollama",
            name="Ollama",
            env=["OLLAMA_API_BASE"],
            api="http://localhost:11434",
        )
        model = ModelInfo(
            provider_id="ollama",
            model_id="mistral",
            name="Mistral",
        )
        config = convert_to_code_puppy_config(model, provider)
        assert config["api_url"] == "http://localhost:11434"

    def test_convert_with_npm_package(self):
        """Test conversion includes npm package when present."""
        provider = ProviderInfo(
            id="ollama",
            name="Ollama",
            env=["OLLAMA_API_BASE"],
            api="",
            npm="@ollama/sdk",
        )
        model = ModelInfo(
            provider_id="ollama",
            model_id="mistral",
            name="Mistral",
        )
        config = convert_to_code_puppy_config(model, provider)
        assert config["npm_package"] == "@ollama/sdk"

    def test_convert_cost_information(self, sample_data):
        """Test conversion includes cost information."""
        provider, model = sample_data
        config = convert_to_code_puppy_config(model, provider)

        assert config["input_cost_per_token"] == 0.015
        assert config["output_cost_per_token"] == 0.075
        assert config["cache_read_cost_per_token"] == 0.00375

    def test_convert_cost_partial(self):
        """Test conversion with partial cost information."""
        provider = ProviderInfo(
            id="anthropic",
            name="Anthropic",
            env=["ANTHROPIC_API_KEY"],
            api="",
        )
        model = ModelInfo(
            provider_id="anthropic",
            model_id="claude-3-sonnet",
            name="Claude 3 Sonnet",
            cost_input=0.003,
            cost_output=0.015,
            # No cache_read cost
        )
        config = convert_to_code_puppy_config(model, provider)

        assert config["input_cost_per_token"] == 0.003
        assert config["output_cost_per_token"] == 0.015
        assert "cache_read_cost_per_token" not in config

    def test_convert_limits(self, sample_data):
        """Test conversion includes token limits."""
        provider, model = sample_data
        config = convert_to_code_puppy_config(model, provider)

        assert config["max_tokens"] == 200000
        assert config["max_output_tokens"] == 4096

    def test_convert_capabilities(self, sample_data):
        """Test conversion includes capabilities."""
        provider, model = sample_data
        config = convert_to_code_puppy_config(model, provider)

        capabilities = config["capabilities"]
        assert capabilities["attachment"] is True
        assert capabilities["reasoning"] is True
        assert capabilities["tool_call"] is True
        assert capabilities["temperature"] is True
        assert capabilities["structured_output"] is False

    def test_convert_modalities(self, sample_data):
        """Test conversion includes input/output modalities."""
        provider, model = sample_data
        config = convert_to_code_puppy_config(model, provider)

        assert config["input_modalities"] == ["text"]
        assert config["output_modalities"] == ["text"]

    def test_convert_metadata(self, sample_data):
        """Test conversion includes metadata."""
        provider, model = sample_data
        config = convert_to_code_puppy_config(model, provider)

        metadata = config["metadata"]
        assert metadata["knowledge"] == "April 2024"
        assert metadata["release_date"] == "2023-03-14"
        assert metadata["last_updated"] == "2024-04-15"
        assert metadata["open_weights"] is False

    def test_convert_provider_type_mapping(self):
        """Test provider type mapping is applied correctly."""
        test_cases = [
            ("anthropic", "anthropic"),
            ("openai", "openai"),
            ("google", "gemini"),
            ("deepseek", "deepseek"),
            ("ollama", "ollama"),
            ("groq", "groq"),
        ]

        for provider_id, expected_type in test_cases:
            provider = ProviderInfo(
                id=provider_id,
                name=provider_id.title(),
                env=["API_KEY"],
                api="",
            )
            model = ModelInfo(
                provider_id=provider_id,
                model_id="test",
                name="Test Model",
            )
            config = convert_to_code_puppy_config(model, provider)
            assert config["type"] == expected_type

    def test_convert_unmapped_provider_type(self):
        """Test unmapped provider defaults to provider_id."""
        provider = ProviderInfo(
            id="custom_provider",
            name="Custom Provider",
            env=["API_KEY"],
            api="",
        )
        model = ModelInfo(
            provider_id="custom_provider",
            model_id="test",
            name="Test Model",
        )
        config = convert_to_code_puppy_config(model, provider)
        assert config["type"] == "custom_provider"

    def test_convert_minimal_metadata(self):
        """Test conversion with minimal metadata."""
        provider = ProviderInfo(
            id="test",
            name="Test",
            env=["API_KEY"],
            api="",
        )
        model = ModelInfo(
            provider_id="test",
            model_id="test",
            name="Test",
            open_weights=True,
        )
        config = convert_to_code_puppy_config(model, provider)
        metadata = config["metadata"]
        assert metadata["open_weights"] is True
        assert len(metadata) == 1  # Only open_weights


class TestModelsDevRegistryUncoveredPaths:
    """Tests for uncovered code paths to reach 90%+ coverage."""

    @patch("code_puppy.models_dev_parser.httpx.Client")
    def test_fetch_from_api_returns_empty_dict(
        self,
        mock_client_class,
    ):
        """Test API returns empty dict falls back to bundled."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        response = MagicMock()
        response.json.return_value = {}  # Empty dict
        mock_client.get.return_value = response

        bundled_data = {
            "openai": {"name": "OpenAI", "env": [], "api": "", "models": {}}
        }

        with patch(
            "builtins.open",
            mock_open(read_data=json.dumps(bundled_data)),
        ):
            with patch("pathlib.Path.exists", return_value=True):
                registry = ModelsDevRegistry()
                assert "bundled:" in registry.data_source

    def test_load_data_bundled_json_decode_error(
        self,
    ):
        """Test JSONDecodeError when loading bundled fallback file."""
        with patch("code_puppy.models_dev_parser.httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            mock_client.get.side_effect = httpx.TimeoutException("Timeout")

            # Create a scenario where bundled file has invalid JSON
            with patch(
                "builtins.open",
                mock_open(read_data="{invalid json}"),
            ):
                with patch("pathlib.Path.exists", return_value=True):
                    with pytest.raises(json.JSONDecodeError):
                        ModelsDevRegistry()

    def test_search_models_non_boolean_capability_filter(self):
        """Test search with non-boolean capability filters."""
        data = {
            "anthropic": {
                "name": "Anthropic",
                "env": ["ANTHROPIC_API_KEY"],
                "api": "",
                "models": {
                    "claude-3-opus": {
                        "name": "Claude 3 Opus",
                        "knowledge": "April 2024",
                    },
                    "claude-3-sonnet": {
                        "name": "Claude 3 Sonnet",
                        "knowledge": "April 2024",
                    },
                },
            }
        }

        with patch(
            "builtins.open",
            mock_open(read_data=json.dumps(data)),
        ):
            with patch("pathlib.Path.exists", return_value=True):
                registry = ModelsDevRegistry(json_path="/tmp/models.json")
                # Filter by non-boolean attribute (string value)
                results = registry.search_models(
                    capability_filters={"knowledge": "April 2024"}
                )
                assert len(results) == 2


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_registry_empty_json(self):
        """Test registry with empty JSON object."""
        data = {}

        with patch(
            "builtins.open",
            mock_open(read_data=json.dumps(data)),
        ):
            with patch("pathlib.Path.exists", return_value=True):
                registry = ModelsDevRegistry(json_path="/tmp/models.json")
                assert len(registry.providers) == 0
                assert len(registry.models) == 0

    def test_registry_provider_with_non_dict_models(self):
        """Test provider where models is not a dict."""
        data = {
            "anthropic": {
                "name": "Anthropic",
                "env": ["ANTHROPIC_API_KEY"],
                "api": "",
                "models": "not a dict",  # Invalid: should be dict
            }
        }

        with patch(
            "builtins.open",
            mock_open(read_data=json.dumps(data)),
        ):
            with patch("pathlib.Path.exists", return_value=True):
                registry = ModelsDevRegistry(json_path="/tmp/models.json")
                # Provider should be loaded, but models skipped
                assert "anthropic" in registry.providers

    def test_model_with_zero_limits(self):
        """Test model with zero context and output limits."""
        model = ModelInfo(
            provider_id="test",
            model_id="test",
            name="Test",
            context_length=0,
            max_output=0,
        )
        assert model.context_length == 0
        assert model.max_output == 0

    def test_model_with_very_large_limits(self):
        """Test model with very large limits."""
        model = ModelInfo(
            provider_id="test",
            model_id="test",
            name="Test",
            context_length=10_000_000,
            max_output=1_000_000,
        )
        assert model.context_length == 10_000_000
        assert model.max_output == 1_000_000

    def test_provider_with_empty_env_list(self):
        """Test provider with empty env list."""
        provider = ProviderInfo(
            id="test",
            name="Test",
            env=[],  # Empty environment vars
            api="",
        )
        assert provider.env == []

    def test_search_models_empty_capability_filters(self):
        """Test search with empty capability filters dict."""
        data = {
            "test": {
                "name": "Test",
                "env": ["API_KEY"],
                "api": "",
                "models": {
                    "model1": {"name": "Model 1"},
                },
            }
        }

        with patch(
            "builtins.open",
            mock_open(read_data=json.dumps(data)),
        ):
            with patch("pathlib.Path.exists", return_value=True):
                registry = ModelsDevRegistry(json_path="/tmp/models.json")
                results = registry.search_models(capability_filters={})
                # Empty filters should return all models
                assert len(results) == 1

    def test_filter_by_cost_empty_list(self):
        """Test cost filter on empty model list."""
        data = {"test": {"name": "Test", "env": ["API_KEY"], "api": "", "models": {}}}

        with patch(
            "builtins.open",
            mock_open(read_data=json.dumps(data)),
        ):
            with patch("pathlib.Path.exists", return_value=True):
                registry = ModelsDevRegistry(json_path="/tmp/models.json")
                filtered = registry.filter_by_cost([], max_input_cost=0.01)
                assert len(filtered) == 0

    def test_filter_by_context_empty_list(self):
        """Test context filter on empty model list."""
        data = {"test": {"name": "Test", "env": ["API_KEY"], "api": "", "models": {}}}

        with patch(
            "builtins.open",
            mock_open(read_data=json.dumps(data)),
        ):
            with patch("pathlib.Path.exists", return_value=True):
                registry = ModelsDevRegistry(json_path="/tmp/models.json")
                filtered = registry.filter_by_context([], min_context_length=100000)
                assert len(filtered) == 0


class TestBundledFileNotFound:
    """Test when bundled fallback file doesn't exist."""

    @patch("code_puppy.models_dev_parser.httpx.Client")
    def test_no_api_no_bundled_raises_file_not_found(self, mock_client_class):
        """When API fails and bundled file missing, raise FileNotFoundError."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.get.side_effect = Exception("fail")

        with patch.object(
            ModelsDevRegistry,
            "_get_bundled_json_path",
            return_value=MagicMock(
                exists=MagicMock(return_value=False), __str__=lambda s: "/fake/path"
            ),
        ):
            with pytest.raises(FileNotFoundError, match="No data source available"):
                ModelsDevRegistry()


class TestMainBlock:
    """Test the __main__ block."""

    @patch("code_puppy.models_dev_parser.emit_error")
    @patch("code_puppy.models_dev_parser.emit_info")
    @patch("code_puppy.models_dev_parser.ModelsDevRegistry")
    def test_main_block_success(self, mock_registry_cls, mock_info, mock_error):
        """Test __main__ block with successful registry."""
        mock_registry = MagicMock()
        mock_registry.data_source = "test"
        mock_registry.get_providers.return_value = [
            ProviderInfo(id="test", name="Test", env=[], api="")
        ]
        model = ModelInfo(
            provider_id="test",
            model_id="m1",
            name="Model 1",
            input_modalities=["image", "text"],
        )
        mock_registry.get_models.return_value = [model]
        mock_registry.search_models.return_value = [model]
        mock_registry.filter_by_cost.return_value = [model]
        mock_registry_cls.return_value = mock_registry

        import runpy

        with patch.dict("sys.modules", {}, clear=False):
            runpy.run_module("code_puppy.models_dev_parser", run_name="__main__")

    @patch("code_puppy.models_dev_parser.emit_error")
    def test_main_block_file_not_found(self, mock_error):
        """Test __main__ block with FileNotFoundError."""
        import runpy

        with patch(
            "code_puppy.models_dev_parser.ModelsDevRegistry",
            side_effect=FileNotFoundError("no file"),
        ):
            runpy.run_module("code_puppy.models_dev_parser", run_name="__main__")

    @patch("code_puppy.models_dev_parser.emit_error")
    def test_main_block_generic_exception(self, mock_error):
        """Test __main__ block with generic exception."""
        import runpy

        with patch(
            "code_puppy.models_dev_parser.ModelsDevRegistry",
            side_effect=RuntimeError("boom"),
        ):
            runpy.run_module("code_puppy.models_dev_parser", run_name="__main__")
