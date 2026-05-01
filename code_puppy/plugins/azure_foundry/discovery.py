"""Azure AI Services deployment discovery.

Queries the Azure Management API to find AI Services accounts and
list their model deployments. Works with any AIServices account
hosting Anthropic, OpenAI, or other model formats.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

AZURE_MANAGEMENT_SCOPE = "https://management.azure.com/.default"
MANAGEMENT_BASE = "https://management.azure.com"
RESOURCE_API_VERSION = "2021-04-01"
DEPLOYMENT_API_VERSION = "2024-10-01"


@dataclass
class AzureAccount:
    """Discovered Azure AI Services account."""

    resource_id: str
    name: str
    location: str
    resource_group: str
    subscription_id: str


@dataclass
class AzureDeployment:
    """Discovered model deployment on an Azure AI Services account."""

    name: str
    model_name: str
    model_format: str  # "Anthropic", "OpenAI", etc.
    model_version: str
    provisioning_state: str
    sku_name: str
    capacity: int


def _get_management_token() -> str | None:
    """Get a token for the Azure Management API using az login credentials.

    Returns:
        Bearer token string, or None if auth fails.
    """
    try:
        from azure.identity import AzureCliCredential

        credential = AzureCliCredential()
        token = credential.get_token(AZURE_MANAGEMENT_SCOPE)
        return token.token
    except Exception as e:
        logger.warning("Failed to get management token: %s", e)
        return None


def _management_get(token: str, url: str) -> dict[str, Any] | None:
    """Make a GET request to the Azure Management API.

    Args:
        token: Bearer token for authentication.
        url: Full URL to GET.

    Returns:
        Parsed JSON response, or None on error.
    """
    try:
        import httpx

        resp = httpx.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if resp.status_code == 200:
            return resp.json()
        logger.warning("Management API %s returned %d", url, resp.status_code)
        return None
    except Exception as e:
        logger.warning("Management API request failed: %s", e)
        return None


def find_account(resource_name: str) -> AzureAccount | None:
    """Find an Azure AI Services account by name across all accessible subscriptions.

    Args:
        resource_name: The account name to search for.

    Returns:
        AzureAccount if found, None otherwise.
    """
    token = _get_management_token()
    if not token:
        return None

    # List subscriptions
    subs_url = f"{MANAGEMENT_BASE}/subscriptions?api-version=2022-12-01"
    subs_resp = _management_get(token, subs_url)
    if not subs_resp:
        return None

    subscriptions = subs_resp.get("value", [])

    for sub in subscriptions:
        sub_id = sub.get("subscriptionId", "")
        if sub.get("state") != "Enabled":
            continue

        # Search for the resource by name and type
        filter_str = (
            f"name eq '{resource_name}' and "
            f"resourceType eq 'Microsoft.CognitiveServices/accounts'"
        )
        resources_url = (
            f"{MANAGEMENT_BASE}/subscriptions/{sub_id}/resources"
            f"?$filter={filter_str}&api-version={RESOURCE_API_VERSION}"
        )
        resources_resp = _management_get(token, resources_url)
        if not resources_resp:
            continue

        for resource in resources_resp.get("value", []):
            rid = resource.get("id", "")
            parts = rid.split("/")
            # /subscriptions/{sub}/resourceGroups/{rg}/providers/.../accounts/{name}
            rg_idx = next(
                (i for i, p in enumerate(parts) if p.lower() == "resourcegroups"),
                None,
            )
            rg = parts[rg_idx + 1] if rg_idx is not None else ""

            return AzureAccount(
                resource_id=rid,
                name=resource_name,
                location=resource.get("location", ""),
                resource_group=rg,
                subscription_id=sub_id,
            )

    return None


def list_deployments(account: AzureAccount) -> list[AzureDeployment]:
    """List all model deployments on an Azure AI Services account.

    Args:
        account: The account to query.

    Returns:
        List of deployments (all states, caller filters as needed).
    """
    token = _get_management_token()
    if not token:
        return []

    url = (
        f"{MANAGEMENT_BASE}{account.resource_id}"
        f"/deployments?api-version={DEPLOYMENT_API_VERSION}"
    )
    resp = _management_get(token, url)
    if not resp:
        return []

    deployments = []
    for d in resp.get("value", []):
        props = d.get("properties", {})
        model = props.get("model", {})
        sku = d.get("sku", {})

        deployments.append(
            AzureDeployment(
                name=d.get("name", ""),
                model_name=model.get("name", ""),
                model_format=model.get("format", ""),
                model_version=model.get("version", ""),
                provisioning_state=props.get("provisioningState", ""),
                sku_name=sku.get("name", ""),
                capacity=sku.get("capacity", 0),
            )
        )

    return deployments
