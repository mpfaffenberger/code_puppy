"""Tests for the safety validator module."""

import os
from unittest.mock import MagicMock, patch

from code_puppy.plugins.walmart_specific.urls import Environment
from code_puppy.safety_validator import (
    SafetyValidationResponse,
    SafetyValidationResult,
    get_environment_from_config,
    validate_command_safety,
)


class TestEnvironmentDetection:
    """Test environment detection logic."""

    def test_default_environment_is_stage(self):
        """Test that default environment is STAGE."""
        with patch.dict(os.environ, {}, clear=True):
            assert get_environment_from_config() == Environment.STAGE

    def test_dev_environment_detection(self):
        """Test DEV environment detection."""
        with patch.dict(os.environ, {"CODE_PUPPY_ENV": "dev"}):
            assert get_environment_from_config() == Environment.DEV

        with patch.dict(os.environ, {"CODE_PUPPY_ENV": "development"}):
            assert get_environment_from_config() == Environment.DEV

    def test_stage_environment_detection(self):
        """Test STAGE environment detection."""
        with patch.dict(os.environ, {"CODE_PUPPY_ENV": "stg"}):
            assert get_environment_from_config() == Environment.STAGE

        with patch.dict(os.environ, {"CODE_PUPPY_ENV": "stage"}):
            assert get_environment_from_config() == Environment.STAGE

    def test_prod_environment_detection(self):
        """Test PROD environment detection."""
        with patch.dict(os.environ, {"CODE_PUPPY_ENV": "prod"}):
            assert get_environment_from_config() == Environment.PROD

        with patch.dict(os.environ, {"CODE_PUPPY_ENV": "production"}):
            assert get_environment_from_config() == Environment.PROD


class TestCommandValidation:
    """Test command safety validation."""

    def test_empty_command_rejected(self):
        """Test that empty commands are rejected."""
        result = validate_command_safety("")
        assert result.is_safe is False
        assert result.error == "Command is empty"

    def test_whitespace_command_rejected(self):
        """Test that whitespace-only commands are rejected."""
        result = validate_command_safety("   ")
        assert result.is_safe is False
        assert result.error == "Command is empty"

    @patch("code_puppy.safety_validator.create_requests_session")
    @patch("code_puppy.config.get_safety_permission_level")
    def test_dangerous_command_blocked(self, mock_permission, mock_session):
        """Test that dangerous commands are blocked."""
        mock_permission.return_value = "medium"  # Default permission level
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "is_dangerous": True,
            "risk_level": "critical",
            "reasoning": "This command will delete everything",
        }
        mock_session_instance = MagicMock()
        mock_session_instance.post.return_value = mock_response
        mock_session.return_value = mock_session_instance

        result = validate_command_safety("rm -rf *")

        assert result.is_safe is False
        assert result.risk_level == "critical"
        assert "delete everything" in result.reasoning
        assert result.should_block is True  # Critical > medium

    @patch("code_puppy.safety_validator.create_requests_session")
    @patch("code_puppy.config.get_safety_permission_level")
    def test_safe_command_allowed(self, mock_permission, mock_session):
        """Test that safe commands are allowed."""
        mock_permission.return_value = "medium"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "is_dangerous": False,
            "risk_level": "safe",
            "reasoning": "This command is safe",
        }
        mock_session_instance = MagicMock()
        mock_session_instance.post.return_value = mock_response
        mock_session.return_value = mock_session_instance

        result = validate_command_safety("echo hello")

        assert result.is_safe is True
        assert result.risk_level == "safe"
        assert result.error is None
        assert result.should_block is False  # Safe <= medium

    @patch("code_puppy.safety_validator.create_requests_session")
    def test_service_unavailable_allows_command(self, mock_session):
        """Test that service unavailability doesn't block commands (fail open)."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_session_instance = MagicMock()
        mock_session_instance.post.return_value = mock_response
        mock_session.return_value = mock_session_instance

        result = validate_command_safety("ls -la")

        # Should fail open (allow command)
        assert result.is_safe is True
        assert result.risk_level == "unknown"
        assert result.error is not None
        assert "500" in result.error

    @patch("code_puppy.safety_validator.create_requests_session")
    def test_timeout_allows_command(self, mock_session):
        """Test that timeouts don't block commands (fail open)."""
        mock_session_instance = MagicMock()
        mock_session_instance.post.side_effect = Exception("Connection timeout")
        mock_session.return_value = mock_session_instance

        result = validate_command_safety("npm test")

        # Should fail open (allow command)
        assert result.is_safe is True
        assert result.risk_level == "unknown"
        assert result.error == "Timeout"

    @patch("code_puppy.safety_validator.create_requests_session")
    def test_network_error_allows_command(self, mock_session):
        """Test that network errors don't block commands (fail open)."""
        mock_session_instance = MagicMock()
        mock_session_instance.post.side_effect = Exception("Network unreachable")
        mock_session.return_value = mock_session_instance

        result = validate_command_safety("git status")

        # Should fail open (allow command)
        assert result.is_safe is True
        assert result.risk_level == "unknown"
        assert result.error is not None

    @patch("code_puppy.safety_validator.create_requests_session")
    @patch("code_puppy.config.get_safety_permission_level")
    def test_context_passed_to_endpoint(self, mock_permission, mock_session):
        """Test that context is passed to the validation endpoint."""
        mock_permission.return_value = "medium"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "is_dangerous": False,
            "risk_level": "safe",
            "reasoning": "Safe command",
        }
        mock_session_instance = MagicMock()
        mock_session_instance.post.return_value = mock_response
        mock_session.return_value = mock_session_instance

        validate_command_safety("echo test", context="Running unit tests")

        # Verify the context was included in the request
        mock_session_instance.post.assert_called_once()
        call_args = mock_session_instance.post.call_args
        assert call_args[1]["json"]["context"] == "Running unit tests"


class TestPermissionLevelLogic:
    """Test permission level threshold logic."""

    def test_should_block_critical_with_medium_permission(self):
        """Test that critical commands are blocked with medium permission."""
        from code_puppy.safety_validator import should_block_command

        assert should_block_command("critical", "medium") is True

    def test_should_block_high_with_medium_permission(self):
        """Test that high commands are blocked with medium permission."""
        from code_puppy.safety_validator import should_block_command

        assert should_block_command("high", "medium") is True

    def test_should_allow_medium_with_medium_permission(self):
        """Test that medium commands are allowed with medium permission."""
        from code_puppy.safety_validator import should_block_command

        assert should_block_command("medium", "medium") is False

    def test_should_allow_low_with_medium_permission(self):
        """Test that low commands are allowed with medium permission."""
        from code_puppy.safety_validator import should_block_command

        assert should_block_command("low", "medium") is False

    def test_should_allow_safe_with_medium_permission(self):
        """Test that safe commands are allowed with medium permission."""
        from code_puppy.safety_validator import should_block_command

        assert should_block_command("safe", "medium") is False

    def test_should_block_low_with_safe_permission(self):
        """Test that low commands are blocked with safe permission."""
        from code_puppy.safety_validator import should_block_command

        assert should_block_command("low", "safe") is True

    def test_should_allow_anything_with_critical_permission(self):
        """Test that all commands are allowed with critical permission."""
        from code_puppy.safety_validator import should_block_command

        assert should_block_command("safe", "critical") is False
        assert should_block_command("low", "critical") is False
        assert should_block_command("medium", "critical") is False
        assert should_block_command("high", "critical") is False
        assert should_block_command("critical", "critical") is False

    def test_unknown_risk_level_blocks(self):
        """Test that unknown risk levels default to blocking."""
        from code_puppy.safety_validator import should_block_command

        assert should_block_command("unknown", "medium") is True

    @patch("code_puppy.safety_validator.create_requests_session")
    @patch("code_puppy.config.get_safety_permission_level")
    def test_risky_but_allowed_command(self, mock_permission, mock_session):
        """Test a command that's risky but within permission level."""
        mock_permission.return_value = "high"  # High permission level
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "is_dangerous": True,
            "risk_level": "medium",
            "reasoning": "This command is somewhat risky",
        }
        result = validate_command_safety("sudo something")

        assert result.is_safe is False  # Marked as dangerous
        assert result.risk_level == "medium"
        assert result.should_block is False  # But allowed due to high permission


class TestSafetyValidationModels:
    """Test Pydantic models for safety validation."""

    def test_safety_validation_response_model(self):
        """Test SafetyValidationResponse model."""
        response = SafetyValidationResponse(
            is_dangerous=True, risk_level="high", reasoning="Dangerous operation"
        )
        assert response.is_dangerous is True
        assert response.risk_level == "high"
        assert response.reasoning == "Dangerous operation"

    def test_safety_validation_result_model(self):
        """Test SafetyValidationResult model."""
        result = SafetyValidationResult(
            is_safe=False,
            risk_level="critical",
            reasoning="Command blocked",
            error="Too dangerous",
            should_block=True,
        )
        assert result.is_safe is False
        assert result.risk_level == "critical"
        assert result.reasoning == "Command blocked"
        assert result.error == "Too dangerous"
        assert result.should_block is True

    def test_safety_validation_result_optional_error(self):
        """Test that error field is optional."""
        result = SafetyValidationResult(
            is_safe=True, risk_level="safe", reasoning="All good", should_block=False
        )
        assert result.error is None
        assert result.should_block is False
