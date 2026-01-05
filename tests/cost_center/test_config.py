"""Test configuration loader."""

import json
from pathlib import Path
from unittest.mock import mock_open, patch

import pytest

from cost_center.config.loader import load_config
from cost_center.collectors.types import AppConfig, TenantDefinition


def test_load_config_success():
    """Test loading valid configuration."""
    config_data = {
        "azureClientId": "test-client-id",
        "tenants": [
            {
                "name": "Test Tenant",
                "tenantId": "test-tenant-id",
                "subscriptions": ["sub-1", "sub-2"],
            }
        ],
    }

    with patch("builtins.open", mock_open(read_data=json.dumps(config_data))):
        with patch("pathlib.Path.exists", return_value=True):
            config = load_config("test.json")

    assert config.azure_client_id == "test-client-id"
    assert len(config.tenants) == 1
    assert config.tenants[0].name == "Test Tenant"
    assert len(config.tenants[0].subscriptions) == 2


def test_load_config_file_not_found():
    """Test error when configuration file doesn't exist."""
    with patch("pathlib.Path.exists", return_value=False):
        with pytest.raises(FileNotFoundError):
            load_config("nonexistent.json")


def test_load_config_multiple_tenants():
    """Test loading configuration with multiple tenants."""
    config_data = {
        "azureClientId": "test-client-id",
        "tenants": [
            {
                "name": "Tenant 1",
                "tenantId": "tenant-1",
                "subscriptions": ["sub-1"],
            },
            {
                "name": "Tenant 2",
                "tenantId": "tenant-2",
                "subscriptions": ["sub-2", "sub-3"],
                "githubOrg": "test-org",
            },
        ],
    }

    with patch("builtins.open", mock_open(read_data=json.dumps(config_data))):
        with patch("pathlib.Path.exists", return_value=True):
            config = load_config("test.json")

    assert len(config.tenants) == 2
    assert config.tenants[1].github_org == "test-org"
