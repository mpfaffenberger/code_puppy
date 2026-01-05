"""Authentication utilities for Azure and Microsoft Graph."""

import os
from enum import Enum
from typing import Literal

from azure.identity import (
    AzureCliCredential,
    ClientSecretCredential,
    DefaultAzureCredential,
    DeviceCodeCredential,
)


class AuthMode(str, Enum):
    """Authentication mode."""

    APP = "app"
    DEVICE = "device"


def get_auth_mode() -> AuthMode:
    """Determine authentication mode from environment."""
    mode = os.getenv("AUTH_MODE", "app").lower()
    return AuthMode.APP if mode == "app" else AuthMode.DEVICE


def build_app_credential(tenant_id: str) -> ClientSecretCredential | AzureCliCredential | DefaultAzureCredential:
    """Build app credential for headless authentication."""
    client_id = os.getenv("AZURE_CLIENT_ID")
    client_secret = os.getenv("AZURE_CLIENT_SECRET")

    # Prefer client secret if available
    if client_id and client_secret:
        return ClientSecretCredential(
            tenant_id=tenant_id, client_id=client_id, client_secret=client_secret
        )

    # Fallback to Azure CLI credential
    try:
        credential = AzureCliCredential(tenant_id=tenant_id)
        # Test the credential
        credential.get_token("https://management.azure.com/.default")
        return credential
    except Exception:
        # Final fallback to default credential
        return DefaultAzureCredential(tenant_id=tenant_id)


def build_device_code_credential(tenant_id: str) -> DeviceCodeCredential:
    """Build device code credential for interactive authentication."""
    client_id = os.getenv("AZURE_CLIENT_ID")
    if not client_id:
        msg = "AZURE_CLIENT_ID environment variable is required for device code flow"
        raise ValueError(msg)

    return DeviceCodeCredential(
        tenant_id=tenant_id,
        client_id=client_id,
    )


def build_tenant_credential(
    tenant_id: str,
    auth_mode: AuthMode | None = None,
) -> ClientSecretCredential | AzureCliCredential | DefaultAzureCredential | DeviceCodeCredential:
    """Build credential for a tenant based on auth mode."""
    if auth_mode is None:
        auth_mode = get_auth_mode()

    if auth_mode == AuthMode.DEVICE:
        return build_device_code_credential(tenant_id)
    return build_app_credential(tenant_id)
