"""Test authentication utilities."""

import os
from unittest.mock import MagicMock, patch

import pytest
from azure.identity import AzureCliCredential, ClientSecretCredential, DeviceCodeCredential

from cost_center.collectors.auth import (
    AuthMode,
    build_app_credential,
    build_device_code_credential,
    build_tenant_credential,
    get_auth_mode,
)


def test_get_auth_mode_default():
    """Test default authentication mode."""
    with patch.dict(os.environ, {}, clear=True):
        mode = get_auth_mode()
        assert mode == AuthMode.APP


def test_get_auth_mode_device():
    """Test device code authentication mode."""
    with patch.dict(os.environ, {"AUTH_MODE": "device"}):
        mode = get_auth_mode()
        assert mode == AuthMode.DEVICE


@patch.dict(os.environ, {"AZURE_CLIENT_ID": "test-id", "AZURE_CLIENT_SECRET": "test-secret"})
def test_build_app_credential_with_secret():
    """Test building app credential with client secret."""
    credential = build_app_credential("test-tenant")
    assert isinstance(credential, ClientSecretCredential)


@patch.dict(os.environ, {"AZURE_CLIENT_ID": "test-id"}, clear=True)
@patch("cost_center.collectors.auth.AzureCliCredential")
def test_build_app_credential_with_cli(mock_cli):
    """Test building app credential with Azure CLI."""
    mock_instance = MagicMock(spec=AzureCliCredential)
    mock_instance.get_token.return_value = MagicMock(token="test-token")
    mock_cli.return_value = mock_instance

    credential = build_app_credential("test-tenant")
    assert isinstance(credential, AzureCliCredential)


@patch.dict(os.environ, {"AZURE_CLIENT_ID": "test-id"})
def test_build_device_code_credential():
    """Test building device code credential."""
    credential = build_device_code_credential("test-tenant")
    assert isinstance(credential, DeviceCodeCredential)


def test_build_device_code_credential_missing_client_id():
    """Test error when client ID is missing for device code flow."""
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="AZURE_CLIENT_ID"):
            build_device_code_credential("test-tenant")


@patch.dict(os.environ, {"AUTH_MODE": "app", "AZURE_CLIENT_ID": "test-id", "AZURE_CLIENT_SECRET": "test-secret"})
def test_build_tenant_credential_app_mode():
    """Test building tenant credential in app mode."""
    credential = build_tenant_credential("test-tenant")
    assert isinstance(credential, ClientSecretCredential)


@patch.dict(os.environ, {"AUTH_MODE": "device", "AZURE_CLIENT_ID": "test-id"})
def test_build_tenant_credential_device_mode():
    """Test building tenant credential in device mode."""
    credential = build_tenant_credential("test-tenant")
    assert isinstance(credential, DeviceCodeCredential)
