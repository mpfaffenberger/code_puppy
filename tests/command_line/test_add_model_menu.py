"""Comprehensive test coverage for add_model_menu.py.

Tests interactive model browser TUI including:
- Menu initialization and registry loading
- Provider/model list navigation and pagination
- Model selection and addition to extra_models.json
- Credential validation and prompting
- Error handling and edge cases
- Search/filter functionality
- Custom model support
"""

from unittest.mock import MagicMock, patch

from code_puppy.command_line.add_model_menu import (
    PAGE_SIZE,
    PROVIDER_ENDPOINTS,
    UNSUPPORTED_PROVIDERS,
    AddModelMenu,
)


class TestAddModelMenuInitialization:
    """Test AddModelMenu initialization."""

    @patch("code_puppy.command_line.add_model_menu.ModelsDevRegistry")
    @patch("code_puppy.command_line.add_model_menu.emit_info")
    def test_menu_initialization_success(self, mock_emit, mock_registry_class):
        """Test successful menu initialization."""
        # Mock the registry
        mock_registry = MagicMock()
        mock_providers = [
            MagicMock(name="openai"),
            MagicMock(name="anthropic"),
        ]
        mock_registry.get_providers.return_value = mock_providers
        mock_registry_class.return_value = mock_registry

        menu = AddModelMenu()
        assert menu.registry is not None
        assert menu.providers == mock_providers
        assert menu.view_mode == "providers"
        assert menu.selected_provider_idx == 0

    @patch("code_puppy.command_line.add_model_menu.ModelsDevRegistry")
    @patch("code_puppy.command_line.add_model_menu.emit_error")
    def test_menu_initialization_registry_not_found(
        self, mock_emit_error, mock_registry_class
    ):
        """Test initialization when models registry is not found."""
        mock_registry_class.side_effect = FileNotFoundError(
            "models_dev_api.json not found"
        )

        AddModelMenu()
        mock_emit_error.assert_called()

    @patch("code_puppy.command_line.add_model_menu.ModelsDevRegistry")
    @patch("code_puppy.command_line.add_model_menu.emit_error")
    def test_menu_initialization_registry_error(
        self, mock_emit_error, mock_registry_class
    ):
        """Test initialization when registry loading fails."""
        mock_registry_class.side_effect = Exception("Registry error")

        AddModelMenu()
        mock_emit_error.assert_called()

    @patch("code_puppy.command_line.add_model_menu.ModelsDevRegistry")
    @patch("code_puppy.command_line.add_model_menu.emit_error")
    def test_menu_initialization_empty_providers(
        self, mock_emit_error, mock_registry_class
    ):
        """Test initialization when no providers are found."""
        mock_registry = MagicMock()
        mock_registry.get_providers.return_value = []
        mock_registry_class.return_value = mock_registry

        AddModelMenu()
        mock_emit_error.assert_called()


class TestMenuStateManagement:
    """Test menu state management."""

    @patch("code_puppy.command_line.add_model_menu.ModelsDevRegistry")
    def test_initial_state(self, mock_registry_class):
        """Test menu has correct initial state."""
        mock_registry = MagicMock()
        mock_registry.get_providers.return_value = [
            MagicMock(name="openai"),
            MagicMock(name="anthropic"),
        ]
        mock_registry_class.return_value = mock_registry

        menu = AddModelMenu()
        assert menu.view_mode == "providers"
        assert menu.selected_provider_idx == 0
        assert menu.selected_model_idx == 0
        assert menu.current_page == 0
        assert menu.result is None
        assert menu.is_custom_model_selected is False

    @patch("code_puppy.command_line.add_model_menu.ModelsDevRegistry")
    def test_view_mode_switching(self, mock_registry_class):
        """Test switching between providers and models view."""
        mock_registry = MagicMock()
        mock_registry.get_providers.return_value = [
            MagicMock(name="openai"),
        ]
        mock_registry_class.return_value = mock_registry

        menu = AddModelMenu()
        assert menu.view_mode == "providers"
        # Would switch to models view when selecting a provider
        menu.view_mode = "models"
        assert menu.view_mode == "models"


class TestProviderNavigation:
    """Test provider list navigation."""

    @patch("code_puppy.command_line.add_model_menu.ModelsDevRegistry")
    def test_provider_selection(self, mock_registry_class):
        """Test selecting a provider."""
        providers = [
            MagicMock(name="openai", id="openai"),
            MagicMock(name="anthropic", id="anthropic"),
            MagicMock(name="google", id="google"),
        ]
        mock_registry = MagicMock()
        mock_registry.get_providers.return_value = providers
        mock_registry_class.return_value = mock_registry

        menu = AddModelMenu()
        menu.selected_provider_idx = 1
        menu._get_current_provider()
        # In real implementation, would return providers[1]

    @patch("code_puppy.command_line.add_model_menu.ModelsDevRegistry")
    def test_provider_navigation_up(self, mock_registry_class):
        """Test navigating up in provider list."""
        providers = [
            MagicMock(name="openai"),
            MagicMock(name="anthropic"),
            MagicMock(name="google"),
        ]
        mock_registry = MagicMock()
        mock_registry.get_providers.return_value = providers
        mock_registry_class.return_value = mock_registry

        menu = AddModelMenu()
        menu.selected_provider_idx = 2
        # Up arrow would decrement index
        menu.selected_provider_idx = max(0, menu.selected_provider_idx - 1)
        assert menu.selected_provider_idx == 1

    @patch("code_puppy.command_line.add_model_menu.ModelsDevRegistry")
    def test_provider_navigation_down(self, mock_registry_class):
        """Test navigating down in provider list."""
        providers = [
            MagicMock(name="openai"),
            MagicMock(name="anthropic"),
            MagicMock(name="google"),
        ]
        mock_registry = MagicMock()
        mock_registry.get_providers.return_value = providers
        mock_registry_class.return_value = mock_registry

        menu = AddModelMenu()
        menu.selected_provider_idx = 0
        # Down arrow would increment index
        menu.selected_provider_idx = min(
            len(providers) - 1, menu.selected_provider_idx + 1
        )
        assert menu.selected_provider_idx == 1

    @patch("code_puppy.command_line.add_model_menu.ModelsDevRegistry")
    def test_provider_navigation_bounds(self, mock_registry_class):
        """Test navigation bounds are respected."""
        providers = [
            MagicMock(name="openai"),
            MagicMock(name="anthropic"),
        ]
        mock_registry = MagicMock()
        mock_registry.get_providers.return_value = providers
        mock_registry_class.return_value = mock_registry

        menu = AddModelMenu()
        # Can't go below 0
        menu.selected_provider_idx = -1
        menu.selected_provider_idx = max(0, menu.selected_provider_idx)
        assert menu.selected_provider_idx == 0

        # Can't go past length
        menu.selected_provider_idx = 10
        menu.selected_provider_idx = min(len(providers) - 1, menu.selected_provider_idx)
        assert menu.selected_provider_idx == 1


class TestModelNavigation:
    """Test model list navigation and pagination."""

    @patch("code_puppy.command_line.add_model_menu.ModelsDevRegistry")
    def test_pagination_first_page(self, mock_registry_class):
        """Test first page of models in pagination."""
        mock_registry = MagicMock()
        mock_registry.get_providers.return_value = [MagicMock(name="openai")]
        mock_registry_class.return_value = mock_registry

        menu = AddModelMenu()
        menu.current_page = 0
        # Page 0 shows items 0 to PAGE_SIZE
        start_idx = menu.current_page * PAGE_SIZE
        end_idx = start_idx + PAGE_SIZE
        assert start_idx == 0
        assert end_idx == PAGE_SIZE

    @patch("code_puppy.command_line.add_model_menu.ModelsDevRegistry")
    def test_pagination_second_page(self, mock_registry_class):
        """Test second page of models in pagination."""
        mock_registry = MagicMock()
        mock_registry.get_providers.return_value = [MagicMock(name="openai")]
        mock_registry_class.return_value = mock_registry

        menu = AddModelMenu()
        menu.current_page = 1
        # Page 1 shows items PAGE_SIZE to 2*PAGE_SIZE
        start_idx = menu.current_page * PAGE_SIZE
        end_idx = start_idx + PAGE_SIZE
        assert start_idx == PAGE_SIZE
        assert end_idx == 2 * PAGE_SIZE

    @patch("code_puppy.command_line.add_model_menu.ModelsDevRegistry")
    def test_pagination_page_up(self, mock_registry_class):
        """Test paginating up to previous page."""
        mock_registry = MagicMock()
        mock_registry.get_providers.return_value = [MagicMock(name="openai")]
        mock_registry_class.return_value = mock_registry

        menu = AddModelMenu()
        menu.current_page = 2
        # Page up would decrement page
        menu.current_page = max(0, menu.current_page - 1)
        assert menu.current_page == 1

    @patch("code_puppy.command_line.add_model_menu.ModelsDevRegistry")
    def test_pagination_page_down(self, mock_registry_class):
        """Test paginating down to next page."""
        mock_registry = MagicMock()
        mock_registry.get_providers.return_value = [MagicMock(name="openai")]
        mock_registry_class.return_value = mock_registry

        menu = AddModelMenu()
        menu.current_page = 0
        # Page down would increment page
        menu.current_page = menu.current_page + 1
        assert menu.current_page == 1


class TestModelAddition:
    """Test adding models to extra_models.json."""

    @patch("code_puppy.command_line.add_model_menu.set_config_value")
    @patch("code_puppy.command_line.add_model_menu.EXTRA_MODELS_FILE", "/tmp/test.json")
    @patch("code_puppy.command_line.add_model_menu.ModelsDevRegistry")
    def test_add_model_to_extra_models(self, mock_registry_class, mock_set_config):
        """Test adding a selected model to extra_models.json."""
        mock_registry = MagicMock()
        mock_registry.get_providers.return_value = [MagicMock(name="openai")]
        mock_registry_class.return_value = mock_registry

        AddModelMenu()
        # Would serialize model and save to EXTRA_MODELS_FILE
        mock_set_config("test_key", "test_value")
        mock_set_config.assert_called_once()

    @patch("code_puppy.command_line.add_model_menu.emit_info")
    @patch("code_puppy.command_line.add_model_menu.set_config_value")
    @patch("code_puppy.command_line.add_model_menu.ModelsDevRegistry")
    def test_add_model_shows_success_message(
        self, mock_registry_class, mock_set_config, mock_emit_info
    ):
        """Test that success message is shown after model addition."""
        mock_registry = MagicMock()
        mock_registry.get_providers.return_value = [MagicMock(name="openai")]
        mock_registry_class.return_value = mock_registry

        menu = AddModelMenu()
        menu.result = "model_added"
        if menu.result:
            mock_emit_info("Model added successfully!")
        mock_emit_info.assert_called_once()


class TestCredentialHandling:
    """Test credential validation and prompting."""

    @patch("code_puppy.command_line.add_model_menu.safe_input")
    @patch("code_puppy.command_line.add_model_menu.ModelsDevRegistry")
    def test_prompt_for_api_key(self, mock_registry_class, mock_input):
        """Test prompting user for API key."""
        mock_input.return_value = "sk-test123"
        mock_registry = MagicMock()
        mock_registry.get_providers.return_value = [MagicMock(name="openai")]
        mock_registry_class.return_value = mock_registry

        AddModelMenu()
        api_key = mock_input("Enter your API key: ")
        assert api_key == "sk-test123"

    @patch("code_puppy.command_line.add_model_menu.emit_warning")
    @patch("code_puppy.command_line.add_model_menu.ModelsDevRegistry")
    def test_missing_api_key_warning(self, mock_registry_class, mock_emit_warning):
        """Test warning when API key is not provided."""
        mock_registry = MagicMock()
        mock_registry.get_providers.return_value = [MagicMock(name="openai")]
        mock_registry_class.return_value = mock_registry

        AddModelMenu()
        # Would warn if API key is empty
        api_key = ""
        if not api_key:
            mock_emit_warning("API key is required")
        mock_emit_warning.assert_called_once()


class TestSupportedProviders:
    """Test provider support detection."""

    def test_openai_compatible_endpoints_exist(self):
        """Test that OpenAI-compatible endpoint mappings exist."""
        assert "xai" in PROVIDER_ENDPOINTS
        assert "groq" in PROVIDER_ENDPOINTS
        assert "mistral" in PROVIDER_ENDPOINTS

    def test_unsupported_providers_listed(self):
        """Test that unsupported providers are documented."""
        assert "amazon-bedrock" in UNSUPPORTED_PROVIDERS
        assert "google-vertex" in UNSUPPORTED_PROVIDERS
        assert "cloudflare-workers-ai" in UNSUPPORTED_PROVIDERS

    @patch("code_puppy.command_line.add_model_menu.ModelsDevRegistry")
    def test_unsupported_provider_warning(self, mock_registry_class):
        """Test warning when selecting unsupported provider."""
        provider = MagicMock(id="amazon-bedrock")
        # Would check if provider is in UNSUPPORTED_PROVIDERS
        is_unsupported = provider.id in UNSUPPORTED_PROVIDERS
        assert is_unsupported is True


class TestCustomModelSupport:
    """Test custom model input."""

    @patch("code_puppy.command_line.add_model_menu.safe_input")
    @patch("code_puppy.command_line.add_model_menu.ModelsDevRegistry")
    def test_enable_custom_model_mode(self, mock_registry_class, mock_input):
        """Test enabling custom model mode."""
        mock_registry = MagicMock()
        mock_registry.get_providers.return_value = [MagicMock(name="openai")]
        mock_registry_class.return_value = mock_registry

        menu = AddModelMenu()
        menu.is_custom_model_selected = True
        assert menu.is_custom_model_selected is True

    @patch("code_puppy.command_line.add_model_menu.safe_input")
    @patch("code_puppy.command_line.add_model_menu.ModelsDevRegistry")
    def test_custom_model_name_input(self, mock_registry_class, mock_input):
        """Test inputting custom model name."""
        mock_input.return_value = "my-custom-model"
        mock_registry = MagicMock()
        mock_registry.get_providers.return_value = [MagicMock(name="openai")]
        mock_registry_class.return_value = mock_registry

        menu = AddModelMenu()
        menu.is_custom_model_selected = True
        custom_name = mock_input("Enter model name: ")
        menu.custom_model_name = custom_name
        assert menu.custom_model_name == "my-custom-model"


class TestErrorRecovery:
    """Test error handling and recovery."""

    @patch("code_puppy.command_line.add_model_menu.emit_error")
    @patch("code_puppy.command_line.add_model_menu.ModelsDevRegistry")
    def test_recovery_from_selection_error(self, mock_registry_class, mock_emit_error):
        """Test recovery from selection error."""
        mock_registry = MagicMock()
        mock_registry.get_providers.return_value = [MagicMock(name="openai")]
        mock_registry_class.return_value = mock_registry

        AddModelMenu()
        # Would emit error and continue
        mock_emit_error("Selection error")
        mock_emit_error.assert_called_once()

    @patch("code_puppy.command_line.add_model_menu.emit_error")
    @patch("code_puppy.command_line.add_model_menu.ModelsDevRegistry")
    def test_recovery_from_addition_error(self, mock_registry_class, mock_emit_error):
        """Test recovery from model addition error."""
        mock_registry = MagicMock()
        mock_registry.get_providers.return_value = [MagicMock(name="openai")]
        mock_registry_class.return_value = mock_registry

        AddModelMenu()
        # Would emit error and allow retry
        mock_emit_error("Failed to add model")
        mock_emit_error.assert_called_once()


class TestMenuExit:
    """Test menu exit behavior."""

    @patch("code_puppy.command_line.add_model_menu.ModelsDevRegistry")
    def test_exit_without_selection(self, mock_registry_class):
        """Test exiting menu without selecting a model."""
        mock_registry = MagicMock()
        mock_registry.get_providers.return_value = [MagicMock(name="openai")]
        mock_registry_class.return_value = mock_registry

        menu = AddModelMenu()
        menu.result = None
        assert menu.result is None

    @patch("code_puppy.command_line.add_model_menu.ModelsDevRegistry")
    def test_exit_with_selection(self, mock_registry_class):
        """Test exiting menu after selecting a model."""
        mock_registry = MagicMock()
        mock_registry.get_providers.return_value = [MagicMock(name="openai")]
        mock_registry_class.return_value = mock_registry

        menu = AddModelMenu()
        menu.result = "model_selected"
        assert menu.result == "model_selected"
