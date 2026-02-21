"""Tests for ACP Gateway configuration."""

import os
from unittest.mock import patch

from code_puppy.plugins.acp_gateway.config import ACPConfig


class TestACPConfigDefaults:
    """Test default configuration values."""

    @patch.dict(os.environ, {}, clear=True)
    def test_default_enabled(self):
        cfg = ACPConfig.from_env()
        assert cfg.enabled is True

    @patch.dict(os.environ, {}, clear=True)
    def test_default_host(self):
        cfg = ACPConfig.from_env()
        assert cfg.host == "0.0.0.0"

    @patch.dict(os.environ, {}, clear=True)
    def test_default_port(self):
        cfg = ACPConfig.from_env()
        assert cfg.port == 9001

    @patch.dict(os.environ, {}, clear=True)
    def test_default_auth_required(self):
        cfg = ACPConfig.from_env()
        assert cfg.auth_required is False

    @patch.dict(os.environ, {}, clear=True)
    def test_default_auth_token(self):
        cfg = ACPConfig.from_env()
        assert cfg.auth_token == ""


class TestACPConfigEnvironmentOverrides:
    """Test environment variable overrides."""

    @patch.dict(os.environ, {"ACP_ENABLED": "false"})
    def test_enabled_false(self):
        cfg = ACPConfig.from_env()
        assert cfg.enabled is False

    @patch.dict(os.environ, {"ACP_ENABLED": "0"})
    def test_enabled_zero(self):
        cfg = ACPConfig.from_env()
        assert cfg.enabled is False

    @patch.dict(os.environ, {"ACP_ENABLED": "no"})
    def test_enabled_no(self):
        cfg = ACPConfig.from_env()
        assert cfg.enabled is False

    @patch.dict(os.environ, {"ACP_ENABLED": "true"})
    def test_enabled_true_explicit(self):
        cfg = ACPConfig.from_env()
        assert cfg.enabled is True

    @patch.dict(os.environ, {"ACP_ENABLED": "1"})
    def test_enabled_one(self):
        cfg = ACPConfig.from_env()
        assert cfg.enabled is True

    @patch.dict(os.environ, {"ACP_ENABLED": "yes"})
    def test_enabled_yes(self):
        cfg = ACPConfig.from_env()
        assert cfg.enabled is True

    @patch.dict(os.environ, {"ACP_ENABLED": "TRUE"})
    def test_enabled_case_insensitive(self):
        cfg = ACPConfig.from_env()
        assert cfg.enabled is True

    @patch.dict(os.environ, {"ACP_HOST": "127.0.0.1"})
    def test_custom_host(self):
        cfg = ACPConfig.from_env()
        assert cfg.host == "127.0.0.1"

    @patch.dict(os.environ, {"ACP_PORT": "8080"})
    def test_custom_port(self):
        cfg = ACPConfig.from_env()
        assert cfg.port == 8080

    @patch.dict(
        os.environ,
        {"ACP_ENABLED": "true", "ACP_HOST": "localhost", "ACP_PORT": "3000"},
    )
    def test_all_overrides(self):
        cfg = ACPConfig.from_env()
        assert cfg.enabled is True
        assert cfg.host == "localhost"
        assert cfg.port == 3000

    @patch.dict(os.environ, {"ACP_AUTH_REQUIRED": "true"})
    def test_auth_required_true(self):
        cfg = ACPConfig.from_env()
        assert cfg.auth_required is True

    @patch.dict(os.environ, {"ACP_AUTH_REQUIRED": "1"})
    def test_auth_required_one(self):
        cfg = ACPConfig.from_env()
        assert cfg.auth_required is True

    @patch.dict(os.environ, {"ACP_AUTH_REQUIRED": "false"})
    def test_auth_required_false(self):
        cfg = ACPConfig.from_env()
        assert cfg.auth_required is False

    @patch.dict(os.environ, {"ACP_AUTH_TOKEN": "my-secret-token"})
    def test_auth_token(self):
        cfg = ACPConfig.from_env()
        assert cfg.auth_token == "my-secret-token"

    @patch.dict(
        os.environ,
        {"ACP_AUTH_REQUIRED": "true", "ACP_AUTH_TOKEN": "secret"},
    )
    def test_auth_config_together(self):
        cfg = ACPConfig.from_env()
        assert cfg.auth_required is True
        assert cfg.auth_token == "secret"


class TestACPConfigImmutability:
    """Test that config is frozen."""

    def test_frozen(self):
        cfg = ACPConfig(
            enabled=True, transport="http", host="0.0.0.0", port=9001,
            auth_required=False, auth_token="",
        )
        import pytest

        with pytest.raises(AttributeError):
            cfg.enabled = False  # type: ignore[misc]

    def test_equality(self):
        a = ACPConfig(
            enabled=True, transport="http", host="0.0.0.0", port=9001,
            auth_required=False, auth_token="",
        )
        b = ACPConfig(
            enabled=True, transport="http", host="0.0.0.0", port=9001,
            auth_required=False, auth_token="",
        )
        assert a == b

    def test_inequality(self):
        a = ACPConfig(
            enabled=True, transport="http", host="0.0.0.0", port=9001,
            auth_required=False, auth_token="",
        )
        b = ACPConfig(
            enabled=False, transport="http", host="0.0.0.0", port=9001,
            auth_required=False, auth_token="",
        )
        assert a != b

    def test_auth_inequality(self):
        a = ACPConfig(
            enabled=True, transport="http", host="0.0.0.0", port=9001,
            auth_required=False, auth_token="",
        )
        b = ACPConfig(
            enabled=True, transport="http", host="0.0.0.0", port=9001,
            auth_required=True, auth_token="secret",
        )
        assert a != b
