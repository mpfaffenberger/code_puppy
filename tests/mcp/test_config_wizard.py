"""
Comprehensive tests for code_puppy/mcp_/config_wizard.py

Tests cover:
- Helper functions (prompt_ask, confirm_ask)
- MCPConfigWizard class initialization and all methods
- Configuration flows for all server types (SSE, HTTP, Stdio)
- Input validation and error handling
- Connection testing
- Confirmation and summary display
- run_add_wizard() entry point
"""

from unittest.mock import Mock, patch

import pytest

from code_puppy.mcp_.config_wizard import (
    MCPConfigWizard,
    confirm_ask,
    prompt_ask,
    run_add_wizard,
)
from code_puppy.mcp_.managed_server import ServerConfig


class TestPromptAsk:
    """Tests for the prompt_ask helper function."""

    @patch("code_puppy.mcp_.config_wizard.emit_prompt")
    def test_prompt_ask_basic(self, mock_emit_prompt):
        """Test basic prompt with user input."""
        mock_emit_prompt.return_value = "test-input"
        result = prompt_ask("Enter value")
        assert result == "test-input"
        mock_emit_prompt.assert_called_once_with("Enter value: ")

    @patch("code_puppy.mcp_.config_wizard.emit_prompt")
    def test_prompt_ask_with_default(self, mock_emit_prompt):
        """Test prompt with default value when no input provided."""
        mock_emit_prompt.return_value = ""
        result = prompt_ask("Enter value", default="default-val")
        assert result == "default-val"

    @patch("code_puppy.mcp_.config_wizard.emit_prompt")
    def test_prompt_ask_override_default(self, mock_emit_prompt):
        """Test user input overrides default value."""
        mock_emit_prompt.return_value = "user-input"
        result = prompt_ask("Enter value", default="default-val")
        assert result == "user-input"

    @patch("code_puppy.mcp_.config_wizard.emit_prompt")
    def test_prompt_ask_with_choices(self, mock_emit_prompt):
        """Test prompt with choices validation."""
        mock_emit_prompt.return_value = "yes"
        result = prompt_ask("Proceed?", choices=["yes", "no"])
        assert result == "yes"

    @patch("code_puppy.mcp_.config_wizard.emit_prompt")
    @patch("code_puppy.mcp_.config_wizard.emit_error")
    def test_prompt_ask_invalid_choice(self, mock_emit_error, mock_emit_prompt):
        """Test invalid choice returns None and emits error."""
        mock_emit_prompt.return_value = "invalid"
        result = prompt_ask("Proceed?", choices=["yes", "no"])
        assert result is None
        mock_emit_error.assert_called_once()

    @patch("code_puppy.mcp_.config_wizard.emit_prompt")
    @patch("code_puppy.mcp_.config_wizard.emit_error")
    def test_prompt_ask_exception(self, mock_emit_error, mock_emit_prompt):
        """Test exception handling in prompt_ask."""
        mock_emit_prompt.side_effect = Exception("Input error")
        result = prompt_ask("Enter value")
        assert result is None
        mock_emit_error.assert_called_once()

    @patch("code_puppy.mcp_.config_wizard.emit_prompt")
    def test_prompt_ask_whitespace_stripping(self, mock_emit_prompt):
        """Test that whitespace is stripped from input."""
        mock_emit_prompt.return_value = "  test  "
        result = prompt_ask("Enter value")
        assert result == "test"

    @patch("code_puppy.mcp_.config_wizard.emit_prompt")
    def test_prompt_ask_with_choices_format(self, mock_emit_prompt):
        """Test choice formatting in prompt text."""
        mock_emit_prompt.return_value = "sse"
        prompt_ask("Type", choices=["sse", "http"])
        call_args = mock_emit_prompt.call_args[0][0]
        assert "(sse/http)" in call_args


class TestConfirmAsk:
    """Tests for the confirm_ask helper function."""

    @patch("code_puppy.mcp_.config_wizard.emit_prompt")
    def test_confirm_ask_yes(self, mock_emit_prompt):
        """Test confirm_ask with yes response."""
        mock_emit_prompt.return_value = "y"
        assert confirm_ask("Proceed?") is True

    @patch("code_puppy.mcp_.config_wizard.emit_prompt")
    def test_confirm_ask_no(self, mock_emit_prompt):
        """Test confirm_ask with no response."""
        mock_emit_prompt.return_value = "n"
        assert confirm_ask("Proceed?") is False

    @patch("code_puppy.mcp_.config_wizard.emit_prompt")
    def test_confirm_ask_yes_variants(self, mock_emit_prompt):
        """Test various yes responses."""
        for response in ["y", "Y", "yes", "YES", "true", "1"]:
            mock_emit_prompt.return_value = response
            assert confirm_ask("Proceed?") is True

    @patch("code_puppy.mcp_.config_wizard.emit_prompt")
    def test_confirm_ask_no_variants(self, mock_emit_prompt):
        """Test various no responses."""
        for response in ["n", "N", "no", "NO", "false", "0"]:
            mock_emit_prompt.return_value = response
            assert confirm_ask("Proceed?") is False

    @patch("code_puppy.mcp_.config_wizard.emit_prompt")
    def test_confirm_ask_empty_with_default_true(self, mock_emit_prompt):
        """Test empty input returns default value (true)."""
        mock_emit_prompt.return_value = ""
        assert confirm_ask("Proceed?", default=True) is True

    @patch("code_puppy.mcp_.config_wizard.emit_prompt")
    def test_confirm_ask_empty_with_default_false(self, mock_emit_prompt):
        """Test empty input returns default value (false)."""
        mock_emit_prompt.return_value = ""
        assert confirm_ask("Proceed?", default=False) is False

    @patch("code_puppy.mcp_.config_wizard.emit_prompt")
    def test_confirm_ask_invalid_response(self, mock_emit_prompt):
        """Test invalid response returns default value."""
        mock_emit_prompt.return_value = "maybe"
        assert confirm_ask("Proceed?", default=True) is True
        assert confirm_ask("Proceed?", default=False) is False

    @patch("code_puppy.mcp_.config_wizard.emit_prompt")
    @patch("code_puppy.mcp_.config_wizard.emit_error")
    def test_confirm_ask_exception(self, mock_emit_error, mock_emit_prompt):
        """Test exception handling in confirm_ask."""
        mock_emit_prompt.side_effect = Exception("Input error")
        result = confirm_ask("Proceed?", default=True)
        assert result is True
        mock_emit_error.assert_called_once()


class TestMCPConfigWizardInit:
    """Tests for MCPConfigWizard initialization."""

    @patch("code_puppy.mcp_.config_wizard.get_mcp_manager")
    def test_wizard_init(self, mock_get_manager):
        """Test wizard initialization."""
        mock_manager = Mock()
        mock_get_manager.return_value = mock_manager
        wizard = MCPConfigWizard()
        assert wizard.manager is mock_manager
        mock_get_manager.assert_called_once()


class TestValidationMethods:
    """Tests for validation methods."""

    @pytest.fixture
    def wizard(self):
        """Create wizard instance for testing."""
        with patch("code_puppy.mcp_.config_wizard.get_mcp_manager"):
            return MCPConfigWizard()

    @pytest.mark.parametrize(
        "name,valid",
        [
            ("valid-server", True),
            ("valid_server", True),
            ("ValidServer123", True),
            ("server-with-many-parts", True),
            ("invalid server", False),
            ("invalid-server!", False),
            ("invalid.server", False),
            ("invalid@server", False),
            ("", False),
            ("a", True),
            ("123", True),
        ],
    )
    def test_validate_name(self, wizard, name, valid):
        """Test name validation with various inputs."""
        assert wizard.validate_name(name) == valid

    @pytest.mark.parametrize(
        "url,valid",
        [
            ("http://localhost:8080", True),
            ("https://example.com", True),
            ("http://192.168.1.1:3000", True),
            ("https://api.example.com/path", True),
            ("ftp://example.com", False),
            ("localhost:8080", False),
            ("example.com", False),
            ("/local/path", False),
            ("", False),
            ("http://", False),
        ],
    )
    def test_validate_url(self, wizard, url, valid):
        """Test URL validation with various inputs."""
        assert wizard.validate_url(url) == valid

    @patch("shutil.which")
    @patch("os.path.isfile")
    def test_validate_command_in_path(self, mock_isfile, mock_which, wizard):
        """Test command validation for commands in PATH."""
        mock_which.return_value = "/usr/bin/python"
        assert wizard.validate_command("python") is True

    @patch("shutil.which")
    @patch("os.path.isfile")
    def test_validate_command_not_in_path(self, mock_isfile, mock_which, wizard):
        """Test command validation for commands not in PATH."""
        mock_which.return_value = None
        assert wizard.validate_command("nonexistent-command") is False

    @patch("shutil.which")
    @patch("os.path.isfile")
    def test_validate_command_with_path(self, mock_isfile, mock_which, wizard):
        """Test command validation for full paths."""
        mock_isfile.return_value = True
        assert wizard.validate_command("/usr/bin/python") is True

    @patch("shutil.which")
    @patch("os.path.isfile")
    def test_validate_command_with_invalid_path(self, mock_isfile, mock_which, wizard):
        """Test command validation for non-existent paths."""
        mock_isfile.return_value = False
        assert wizard.validate_command("/nonexistent/path") is False


class TestPromptServerName:
    """Tests for prompt_server_name method."""

    @pytest.fixture
    def wizard(self):
        """Create wizard with mocked manager."""
        mock_manager = Mock()
        mock_manager.registry.get_by_name.return_value = None
        with patch(
            "code_puppy.mcp_.config_wizard.get_mcp_manager", return_value=mock_manager
        ):
            return MCPConfigWizard()

    @patch("code_puppy.mcp_.config_wizard.prompt_ask")
    def test_prompt_server_name_valid(self, mock_prompt, wizard):
        """Test prompting for valid server name."""
        mock_prompt.return_value = "my-server"
        result = wizard.prompt_server_name()
        assert result == "my-server"

    @patch("code_puppy.mcp_.config_wizard.prompt_ask")
    @patch("code_puppy.mcp_.config_wizard.confirm_ask")
    @patch("code_puppy.mcp_.config_wizard.emit_error")
    def test_prompt_server_name_invalid_format(
        self, mock_emit_error, mock_confirm, mock_prompt, wizard
    ):
        """Test invalid name format returns None on cancel."""
        # First invalid name, then cancel
        mock_prompt.side_effect = ["invalid!name", None]
        mock_confirm.return_value = True  # Cancel after invalid
        result = wizard.prompt_server_name()
        assert result is None
        mock_emit_error.assert_called()

    @patch("code_puppy.mcp_.config_wizard.prompt_ask")
    @patch("code_puppy.mcp_.config_wizard.confirm_ask")
    @patch("code_puppy.mcp_.config_wizard.emit_error")
    def test_prompt_server_name_exists(
        self, mock_emit_error, mock_confirm, mock_prompt, wizard
    ):
        """Test name uniqueness check."""
        wizard.manager.registry.get_by_name.return_value = Mock()  # Server exists
        # First server exists, then cancel
        mock_prompt.side_effect = ["existing-server", None]
        mock_confirm.return_value = True  # Cancel after duplicate
        result = wizard.prompt_server_name()
        assert result is None
        mock_emit_error.assert_called()

    @patch("code_puppy.mcp_.config_wizard.prompt_ask")
    @patch("code_puppy.mcp_.config_wizard.confirm_ask")
    def test_prompt_server_name_cancel(self, mock_confirm, mock_prompt, wizard):
        """Test cancellation during name prompt."""
        mock_prompt.return_value = None
        mock_confirm.return_value = True  # User confirms cancel
        result = wizard.prompt_server_name()
        assert result is None

    @patch("code_puppy.mcp_.config_wizard.prompt_ask")
    @patch("code_puppy.mcp_.config_wizard.confirm_ask")
    @patch("code_puppy.mcp_.config_wizard.emit_error")
    def test_prompt_server_name_retry_after_invalid(
        self, mock_emit_error, mock_confirm, mock_prompt, wizard
    ):
        """Test retry after invalid name format."""
        # First attempt invalid, second attempt valid
        mock_prompt.side_effect = ["invalid!name", "valid-server"]
        mock_confirm.return_value = False  # Don't cancel
        result = wizard.prompt_server_name()
        assert result == "valid-server"


class TestPromptServerType:
    """Tests for prompt_server_type method."""

    @pytest.fixture
    def wizard(self):
        """Create wizard instance."""
        with patch("code_puppy.mcp_.config_wizard.get_mcp_manager"):
            return MCPConfigWizard()

    @patch("code_puppy.mcp_.config_wizard.emit_info")
    @patch("code_puppy.mcp_.config_wizard.prompt_ask")
    def test_prompt_server_type_sse(self, mock_prompt, mock_info, wizard):
        """Test selecting SSE server type."""
        mock_prompt.return_value = "sse"
        result = wizard.prompt_server_type()
        assert result == "sse"

    @patch("code_puppy.mcp_.config_wizard.emit_info")
    @patch("code_puppy.mcp_.config_wizard.prompt_ask")
    def test_prompt_server_type_http(self, mock_prompt, mock_info, wizard):
        """Test selecting HTTP server type."""
        mock_prompt.return_value = "http"
        result = wizard.prompt_server_type()
        assert result == "http"

    @patch("code_puppy.mcp_.config_wizard.emit_info")
    @patch("code_puppy.mcp_.config_wizard.prompt_ask")
    def test_prompt_server_type_stdio(self, mock_prompt, mock_info, wizard):
        """Test selecting Stdio server type."""
        mock_prompt.return_value = "stdio"
        result = wizard.prompt_server_type()
        assert result == "stdio"

    @patch("code_puppy.mcp_.config_wizard.emit_info")
    @patch("code_puppy.mcp_.config_wizard.emit_error")
    @patch("code_puppy.mcp_.config_wizard.prompt_ask")
    def test_prompt_server_type_invalid(
        self, mock_prompt, mock_error, mock_info, wizard
    ):
        """Test invalid type selection."""
        mock_prompt.side_effect = ["invalid", "stdio"]
        result = wizard.prompt_server_type()
        assert result == "stdio"
        mock_error.assert_called()


class TestPromptSSEConfig:
    """Tests for prompt_sse_config method."""

    @pytest.fixture
    def wizard(self):
        """Create wizard instance."""
        with patch("code_puppy.mcp_.config_wizard.get_mcp_manager"):
            return MCPConfigWizard()

    @patch("code_puppy.mcp_.config_wizard.prompt_ask")
    @patch("code_puppy.mcp_.config_wizard.confirm_ask")
    @patch("code_puppy.mcp_.config_wizard.emit_info")
    def test_prompt_sse_config_basic(
        self, mock_info, mock_confirm, mock_prompt, wizard
    ):
        """Test basic SSE configuration."""
        mock_prompt.side_effect = ["http://localhost:8080", "30"]
        mock_confirm.return_value = False
        config = wizard.prompt_sse_config()
        assert config["type"] == "sse"
        assert config["url"] == "http://localhost:8080"
        assert config["timeout"] == 30

    @patch("code_puppy.mcp_.config_wizard.prompt_ask")
    @patch("code_puppy.mcp_.config_wizard.confirm_ask")
    @patch("code_puppy.mcp_.config_wizard.emit_info")
    def test_prompt_sse_config_with_headers(
        self, mock_info, mock_confirm, mock_prompt, wizard
    ):
        """Test SSE configuration with custom headers."""
        mock_prompt.side_effect = ["http://localhost:8080", "30"]
        mock_confirm.side_effect = [True, False]  # Add headers, don't add more
        with patch.object(wizard, "prompt_headers", return_value={"Auth": "token"}):
            config = wizard.prompt_sse_config()
        assert config["headers"] == {"Auth": "token"}

    @patch("code_puppy.mcp_.config_wizard.prompt_ask")
    @patch("code_puppy.mcp_.config_wizard.confirm_ask")
    @patch("code_puppy.mcp_.config_wizard.emit_info")
    def test_prompt_sse_config_invalid_timeout(
        self, mock_info, mock_confirm, mock_prompt, wizard
    ):
        """Test SSE configuration with invalid timeout."""
        mock_prompt.side_effect = ["http://localhost:8080", "invalid"]
        mock_confirm.return_value = False
        config = wizard.prompt_sse_config()
        assert config["timeout"] == 30  # Should use default


class TestPromptHTTPConfig:
    """Tests for prompt_http_config method."""

    @pytest.fixture
    def wizard(self):
        """Create wizard instance."""
        with patch("code_puppy.mcp_.config_wizard.get_mcp_manager"):
            return MCPConfigWizard()

    @patch("code_puppy.mcp_.config_wizard.prompt_ask")
    @patch("code_puppy.mcp_.config_wizard.confirm_ask")
    @patch("code_puppy.mcp_.config_wizard.emit_info")
    def test_prompt_http_config_basic(
        self, mock_info, mock_confirm, mock_prompt, wizard
    ):
        """Test basic HTTP configuration."""
        mock_prompt.side_effect = ["https://api.example.com", "60"]
        mock_confirm.return_value = False
        config = wizard.prompt_http_config()
        assert config["type"] == "http"
        assert config["url"] == "https://api.example.com"
        assert config["timeout"] == 60


class TestPromptStdioConfig:
    """Tests for prompt_stdio_config method."""

    @pytest.fixture
    def wizard(self):
        """Create wizard instance."""
        with patch("code_puppy.mcp_.config_wizard.get_mcp_manager"):
            return MCPConfigWizard()

    @patch("code_puppy.mcp_.config_wizard.prompt_ask")
    @patch("code_puppy.mcp_.config_wizard.confirm_ask")
    @patch("code_puppy.mcp_.config_wizard.emit_info")
    @patch("code_puppy.mcp_.config_wizard.emit_warning")
    def test_prompt_stdio_config_basic(
        self, mock_warn, mock_info, mock_confirm, mock_prompt, wizard
    ):
        """Test basic Stdio configuration."""
        mock_prompt.side_effect = ["python server.py", "", "", "30"]
        mock_confirm.side_effect = [False, False]  # No cwd, no env
        config = wizard.prompt_stdio_config()
        assert config["type"] == "stdio"
        assert config["command"] == "python server.py"
        assert config["args"] == []
        assert config["timeout"] == 30

    @patch("code_puppy.mcp_.config_wizard.prompt_ask")
    @patch("code_puppy.mcp_.config_wizard.confirm_ask")
    @patch("code_puppy.mcp_.config_wizard.emit_info")
    @patch("code_puppy.mcp_.config_wizard.emit_warning")
    def test_prompt_stdio_config_with_args(
        self, mock_warn, mock_info, mock_confirm, mock_prompt, wizard
    ):
        """Test Stdio configuration with arguments."""
        mock_prompt.side_effect = ["python", "-m server", "", "30"]
        mock_confirm.side_effect = [False, False]  # No cwd, no env
        config = wizard.prompt_stdio_config()
        assert config["command"] == "python"
        assert config["args"] == ["-m", "server"]

    @patch("code_puppy.mcp_.config_wizard.prompt_ask")
    @patch("code_puppy.mcp_.config_wizard.confirm_ask")
    @patch("code_puppy.mcp_.config_wizard.emit_info")
    @patch("code_puppy.mcp_.config_wizard.emit_warning")
    def test_prompt_stdio_config_with_cwd(
        self, mock_warn, mock_info, mock_confirm, mock_prompt, wizard
    ):
        """Test Stdio configuration with working directory."""
        mock_prompt.side_effect = ["python server.py", "", "/tmp", "30"]
        mock_confirm.side_effect = [False, False]  # No env
        with patch("os.path.isdir", return_value=True):
            with patch("os.path.expanduser", return_value="/tmp"):
                config = wizard.prompt_stdio_config()
        assert config["cwd"] == "/tmp"

    @patch("code_puppy.mcp_.config_wizard.prompt_ask")
    @patch("code_puppy.mcp_.config_wizard.confirm_ask")
    @patch("code_puppy.mcp_.config_wizard.emit_info")
    @patch("code_puppy.mcp_.config_wizard.emit_warning")
    def test_prompt_stdio_config_invalid_cwd(
        self, mock_warn, mock_info, mock_confirm, mock_prompt, wizard
    ):
        """Test Stdio configuration with invalid working directory."""
        mock_prompt.side_effect = ["python server.py", "", "/nonexistent", "30"]
        mock_confirm.side_effect = [False, False]  # No env
        with patch("os.path.isdir", return_value=False):
            config = wizard.prompt_stdio_config()
        assert "cwd" not in config
        mock_warn.assert_called()

    @patch("code_puppy.mcp_.config_wizard.prompt_ask")
    @patch("code_puppy.mcp_.config_wizard.confirm_ask")
    @patch("code_puppy.mcp_.config_wizard.emit_info")
    @patch("code_puppy.mcp_.config_wizard.emit_warning")
    def test_prompt_stdio_config_with_env(
        self, mock_warn, mock_info, mock_confirm, mock_prompt, wizard
    ):
        """Test Stdio configuration with environment variables."""
        mock_prompt.side_effect = ["python server.py", "", "", "30"]
        mock_confirm.return_value = True  # Add env vars
        with patch.object(wizard, "prompt_env_vars", return_value={"DEBUG": "1"}):
            config = wizard.prompt_stdio_config()
        assert config["env"] == {"DEBUG": "1"}


class TestPromptURL:
    """Tests for prompt_url method."""

    @pytest.fixture
    def wizard(self):
        """Create wizard instance."""
        with patch("code_puppy.mcp_.config_wizard.get_mcp_manager"):
            return MCPConfigWizard()

    @patch("code_puppy.mcp_.config_wizard.prompt_ask")
    def test_prompt_url_valid(self, mock_prompt, wizard):
        """Test prompting for valid URL."""
        mock_prompt.return_value = "http://localhost:8080"
        result = wizard.prompt_url("HTTP")
        assert result == "http://localhost:8080"

    @patch("code_puppy.mcp_.config_wizard.prompt_ask")
    @patch("code_puppy.mcp_.config_wizard.emit_error")
    @patch("code_puppy.mcp_.config_wizard.confirm_ask")
    def test_prompt_url_invalid_then_valid(
        self, mock_confirm, mock_error, mock_prompt, wizard
    ):
        """Test retrying after invalid URL."""
        mock_prompt.side_effect = ["invalid", "http://localhost:8080"]
        result = wizard.prompt_url("HTTP")
        assert result == "http://localhost:8080"
        mock_error.assert_called()

    @patch("code_puppy.mcp_.config_wizard.prompt_ask")
    @patch("code_puppy.mcp_.config_wizard.confirm_ask")
    def test_prompt_url_cancel(self, mock_confirm, mock_prompt, wizard):
        """Test cancellation during URL prompt."""
        mock_prompt.return_value = None
        mock_confirm.return_value = True
        result = wizard.prompt_url("HTTP")
        assert result is None


class TestPromptHeaders:
    """Tests for prompt_headers method."""

    @pytest.fixture
    def wizard(self):
        """Create wizard instance."""
        with patch("code_puppy.mcp_.config_wizard.get_mcp_manager"):
            return MCPConfigWizard()

    @patch("code_puppy.mcp_.config_wizard.prompt_ask")
    @patch("code_puppy.mcp_.config_wizard.confirm_ask")
    @patch("code_puppy.mcp_.config_wizard.emit_info")
    def test_prompt_headers_single(self, mock_info, mock_confirm, mock_prompt, wizard):
        """Test prompting for single header."""
        mock_prompt.side_effect = ["Authorization", "Bearer token123", ""]
        mock_confirm.return_value = False
        headers = wizard.prompt_headers()
        assert headers["Authorization"] == "Bearer token123"

    @patch("code_puppy.mcp_.config_wizard.prompt_ask")
    @patch("code_puppy.mcp_.config_wizard.confirm_ask")
    @patch("code_puppy.mcp_.config_wizard.emit_info")
    def test_prompt_headers_multiple(
        self, mock_info, mock_confirm, mock_prompt, wizard
    ):
        """Test prompting for multiple headers."""
        mock_prompt.side_effect = [
            "Authorization",
            "Bearer token",
            "Content-Type",
            "application/json",
            "",
        ]
        mock_confirm.side_effect = [True, False]
        headers = wizard.prompt_headers()
        assert len(headers) == 2
        assert headers["Authorization"] == "Bearer token"
        assert headers["Content-Type"] == "application/json"

    @patch("code_puppy.mcp_.config_wizard.prompt_ask")
    @patch("code_puppy.mcp_.config_wizard.confirm_ask")
    @patch("code_puppy.mcp_.config_wizard.emit_info")
    def test_prompt_headers_empty(self, mock_info, mock_confirm, mock_prompt, wizard):
        """Test prompt_headers when no headers added."""
        mock_prompt.return_value = ""
        headers = wizard.prompt_headers()
        assert headers == {}


class TestPromptEnvVars:
    """Tests for prompt_env_vars method."""

    @pytest.fixture
    def wizard(self):
        """Create wizard instance."""
        with patch("code_puppy.mcp_.config_wizard.get_mcp_manager"):
            return MCPConfigWizard()

    @patch("code_puppy.mcp_.config_wizard.prompt_ask")
    @patch("code_puppy.mcp_.config_wizard.confirm_ask")
    @patch("code_puppy.mcp_.config_wizard.emit_info")
    def test_prompt_env_vars_single(self, mock_info, mock_confirm, mock_prompt, wizard):
        """Test prompting for single environment variable."""
        mock_prompt.side_effect = ["DEBUG", "1", ""]
        mock_confirm.return_value = False
        env = wizard.prompt_env_vars()
        assert env["DEBUG"] == "1"

    @patch("code_puppy.mcp_.config_wizard.prompt_ask")
    @patch("code_puppy.mcp_.config_wizard.confirm_ask")
    @patch("code_puppy.mcp_.config_wizard.emit_info")
    def test_prompt_env_vars_multiple(
        self, mock_info, mock_confirm, mock_prompt, wizard
    ):
        """Test prompting for multiple environment variables."""
        mock_prompt.side_effect = [
            "DEBUG",
            "1",
            "LOG_LEVEL",
            "INFO",
            "",
        ]
        mock_confirm.side_effect = [True, False]
        env = wizard.prompt_env_vars()
        assert env["DEBUG"] == "1"
        assert env["LOG_LEVEL"] == "INFO"


class TestTestConnection:
    """Tests for test_connection method."""

    @pytest.fixture
    def wizard(self):
        """Create wizard with mocked manager."""
        mock_manager = Mock()
        with patch(
            "code_puppy.mcp_.config_wizard.get_mcp_manager", return_value=mock_manager
        ):
            return MCPConfigWizard()

    @patch("code_puppy.mcp_.config_wizard.emit_info")
    @patch("code_puppy.mcp_.config_wizard.emit_success")
    def test_test_connection_success(self, mock_success, mock_info, wizard):
        """Test successful connection test."""
        config = ServerConfig(
            id="test-1",
            name="test",
            type="http",
            enabled=True,
            config={"url": "http://localhost:8080"},
        )
        mock_managed = Mock()
        mock_managed.get_pydantic_server.return_value = Mock()
        wizard.manager.get_server.return_value = mock_managed
        wizard.manager.register_server.return_value = "test-1"

        result = wizard.test_connection(config)
        assert result is True
        mock_success.assert_called()

    @patch("code_puppy.mcp_.config_wizard.emit_info")
    @patch("code_puppy.mcp_.config_wizard.emit_error")
    def test_test_connection_failure(self, mock_error, mock_info, wizard):
        """Test failed connection test."""
        config = ServerConfig(
            id="test-1",
            name="test",
            type="http",
            enabled=True,
            config={"url": "http://localhost:8080"},
        )
        wizard.manager.get_server.return_value = None
        wizard.manager.register_server.side_effect = Exception("Config error")

        result = wizard.test_connection(config)
        assert result is False
        mock_error.assert_called()


class TestPromptConfirmation:
    """Tests for prompt_confirmation method."""

    @pytest.fixture
    def wizard(self):
        """Create wizard with mocked manager."""
        mock_manager = Mock()
        with patch(
            "code_puppy.mcp_.config_wizard.get_mcp_manager", return_value=mock_manager
        ):
            return MCPConfigWizard()

    @patch("code_puppy.mcp_.config_wizard.emit_info")
    @patch("code_puppy.mcp_.config_wizard.confirm_ask")
    def test_prompt_confirmation_accept(self, mock_confirm, mock_info, wizard):
        """Test confirming server configuration."""
        config = ServerConfig(
            id="test-1",
            name="test-server",
            type="stdio",
            enabled=True,
            config={"command": "echo hello"},
        )
        mock_confirm.side_effect = [False, True]  # Don't test, do save
        result = wizard.prompt_confirmation(config)
        assert result is True

    @patch("code_puppy.mcp_.config_wizard.emit_info")
    @patch("code_puppy.mcp_.config_wizard.confirm_ask")
    def test_prompt_confirmation_reject(self, mock_confirm, mock_info, wizard):
        """Test rejecting server configuration."""
        config = ServerConfig(
            id="test-1",
            name="test-server",
            type="stdio",
            enabled=True,
            config={"command": "echo hello"},
        )
        mock_confirm.return_value = False
        result = wizard.prompt_confirmation(config)
        assert result is False

    @patch("code_puppy.mcp_.config_wizard.emit_info")
    @patch("code_puppy.mcp_.config_wizard.confirm_ask")
    def test_prompt_confirmation_with_test(self, mock_confirm, mock_info, wizard):
        """Test confirmation with connection test."""
        config = ServerConfig(
            id="test-1",
            name="test-server",
            type="stdio",
            enabled=True,
            config={"command": "echo hello"},
        )
        mock_confirm.side_effect = [
            True,
            False,
            True,
        ]  # Test, test fails, don't continue, save
        with patch.object(wizard, "test_connection", return_value=False):
            result = wizard.prompt_confirmation(config)
        assert result is False


class TestRunWizard:
    """Tests for run_wizard method."""

    @pytest.fixture
    def wizard(self):
        """Create wizard with mocked manager."""
        mock_manager = Mock()
        mock_manager.registry.get_by_name.return_value = None
        with patch(
            "code_puppy.mcp_.config_wizard.get_mcp_manager", return_value=mock_manager
        ):
            return MCPConfigWizard()

    @patch("code_puppy.mcp_.config_wizard.emit_info")
    def test_run_wizard_stdio_flow(self, mock_info, wizard):
        """Test complete wizard flow for stdio server."""
        with patch.object(wizard, "prompt_server_name", return_value="test-server"):
            with patch.object(wizard, "prompt_server_type", return_value="stdio"):
                with patch.object(
                    wizard,
                    "prompt_stdio_config",
                    return_value={"type": "stdio", "command": "python"},
                ):
                    with patch.object(wizard, "prompt_confirmation", return_value=True):
                        result = wizard.run_wizard()

        assert result is not None
        assert result.name == "test-server"
        assert result.type == "stdio"

    @patch("code_puppy.mcp_.config_wizard.emit_info")
    def test_run_wizard_http_flow(self, mock_info, wizard):
        """Test complete wizard flow for HTTP server."""
        with patch.object(wizard, "prompt_server_name", return_value="api-server"):
            with patch.object(wizard, "prompt_server_type", return_value="http"):
                with patch.object(
                    wizard,
                    "prompt_http_config",
                    return_value={
                        "type": "http",
                        "url": "http://localhost:8080",
                    },
                ):
                    with patch.object(wizard, "prompt_confirmation", return_value=True):
                        result = wizard.run_wizard()

        assert result is not None
        assert result.name == "api-server"
        assert result.type == "http"

    @patch("code_puppy.mcp_.config_wizard.emit_info")
    def test_run_wizard_sse_flow(self, mock_info, wizard):
        """Test complete wizard flow for SSE server."""
        with patch.object(wizard, "prompt_server_name", return_value="stream-server"):
            with patch.object(wizard, "prompt_server_type", return_value="sse"):
                with patch.object(
                    wizard,
                    "prompt_sse_config",
                    return_value={
                        "type": "sse",
                        "url": "https://example.com/events",
                    },
                ):
                    with patch.object(wizard, "prompt_confirmation", return_value=True):
                        result = wizard.run_wizard()

        assert result is not None
        assert result.name == "stream-server"
        assert result.type == "sse"

    @patch("code_puppy.mcp_.config_wizard.emit_info")
    def test_run_wizard_cancel_at_name(self, mock_info, wizard):
        """Test cancellation during name prompt."""
        with patch.object(wizard, "prompt_server_name", return_value=None):
            result = wizard.run_wizard()
        assert result is None

    @patch("code_puppy.mcp_.config_wizard.emit_info")
    def test_run_wizard_cancel_at_type(self, mock_info, wizard):
        """Test cancellation during type prompt."""
        with patch.object(wizard, "prompt_server_name", return_value="test"):
            with patch.object(wizard, "prompt_server_type", return_value=None):
                result = wizard.run_wizard()
        assert result is None

    @patch("code_puppy.mcp_.config_wizard.emit_info")
    def test_run_wizard_cancel_at_config(self, mock_info, wizard):
        """Test cancellation during config prompt."""
        with patch.object(wizard, "prompt_server_name", return_value="test"):
            with patch.object(wizard, "prompt_server_type", return_value="stdio"):
                with patch.object(wizard, "prompt_stdio_config", return_value=None):
                    result = wizard.run_wizard()
        assert result is None

    @patch("code_puppy.mcp_.config_wizard.emit_info")
    def test_run_wizard_cancel_at_confirmation(self, mock_info, wizard):
        """Test cancellation during confirmation."""
        with patch.object(wizard, "prompt_server_name", return_value="test"):
            with patch.object(wizard, "prompt_server_type", return_value="stdio"):
                with patch.object(
                    wizard,
                    "prompt_stdio_config",
                    return_value={"type": "stdio", "command": "python"},
                ):
                    with patch.object(
                        wizard, "prompt_confirmation", return_value=False
                    ):
                        result = wizard.run_wizard()
        assert result is None


class TestRunAddWizard:
    """Tests for run_add_wizard entry point function."""

    @patch("code_puppy.mcp_.config_wizard.get_mcp_manager")
    @patch("code_puppy.mcp_.config_wizard.emit_warning")
    def test_run_add_wizard_cancelled(self, mock_warn, mock_get_manager):
        """Test run_add_wizard when user cancels."""
        mock_manager = Mock()
        mock_get_manager.return_value = mock_manager

        with patch.object(MCPConfigWizard, "run_wizard", return_value=None):
            result = run_add_wizard()

        assert result is False
        mock_warn.assert_called()

    @patch("code_puppy.mcp_.config_wizard.get_mcp_manager")
    @patch("code_puppy.mcp_.config_wizard.emit_success")
    @patch("code_puppy.mcp_.config_wizard.emit_info")
    @patch("builtins.open", create=True)
    @patch("os.path.exists", return_value=False)
    @patch("os.makedirs")
    @patch("json.dump")
    def test_run_add_wizard_success(
        self,
        mock_json_dump,
        mock_makedirs,
        mock_exists,
        mock_open,
        mock_info,
        mock_success,
        mock_get_manager,
    ):
        """Test successful wizard completion and registration."""
        config = ServerConfig(
            id="test-1",
            name="test-server",
            type="stdio",
            enabled=True,
            config={"command": "python"},
        )
        mock_manager = Mock()
        mock_manager.register_server.return_value = "test-1"
        mock_get_manager.return_value = mock_manager

        with patch.object(MCPConfigWizard, "run_wizard", return_value=config):
            with patch("code_puppy.config.MCP_SERVERS_FILE", "/tmp/mcp_servers.json"):
                with patch("pathlib.Path.replace"):
                    result = run_add_wizard()

        assert result is True
        mock_manager.register_server.assert_called_once_with(config)
        mock_success.assert_called()

    @patch("code_puppy.mcp_.config_wizard.get_mcp_manager")
    @patch("code_puppy.mcp_.config_wizard.emit_error")
    @patch("builtins.open", create=True)
    @patch("os.path.exists", return_value=False)
    @patch("os.makedirs")
    def test_run_add_wizard_registration_failure(
        self, mock_makedirs, mock_exists, mock_open, mock_error, mock_get_manager
    ):
        """Test wizard failure during registration."""
        config = ServerConfig(
            id="test-1",
            name="test-server",
            type="stdio",
            enabled=True,
            config={"command": "python"},
        )
        mock_manager = Mock()
        mock_manager.register_server.side_effect = Exception("Registration failed")
        mock_get_manager.return_value = mock_manager

        with patch.object(MCPConfigWizard, "run_wizard", return_value=config):
            with patch("code_puppy.config.MCP_SERVERS_FILE", "/tmp/mcp_servers.json"):
                result = run_add_wizard()

        assert result is False
        mock_error.assert_called()
