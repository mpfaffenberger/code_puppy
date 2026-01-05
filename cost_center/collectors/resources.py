"""Azure Resource Manager API client."""

import asyncio
from typing import Any

from azure.identity import DefaultAzureCredential
from azure.mgmt.advisor import AdvisorManagementClient
from azure.mgmt.resource import ResourceManagementClient, SubscriptionClient
from azure.mgmt.resource.resources.models import ResourceGroup as AzureResourceGroup

from cost_center.collectors.types import (
    AdvisorRecommendation,
    AzureResource,
    ManagementGroup,
    ResourceGroup,
    SubscriptionInfo,
)


async def list_subscriptions(credential: DefaultAzureCredential) -> list[SubscriptionInfo]:
    """List all subscriptions."""
    client = SubscriptionClient(credential=credential)
    subscriptions: list[SubscriptionInfo] = []

    for sub in client.subscriptions.list():
        subscriptions.append(
            SubscriptionInfo(
                subscription_id=sub.subscription_id or "",
                display_name=sub.display_name or "Unknown",
                state=str(sub.state),
                tenant_id=sub.tenant_id or "",
            )
        )

    return subscriptions


async def list_resource_groups(
    credential: DefaultAzureCredential, subscription_id: str
) -> list[ResourceGroup]:
    """List resource groups in a subscription."""
    client = ResourceManagementClient(credential=credential, subscription_id=subscription_id)
    resource_groups: list[ResourceGroup] = []

    for rg in client.resource_groups.list():
        resource_groups.append(
            ResourceGroup(
                id=rg.id or "",
                name=rg.name or "",
                location=rg.location or "",
                subscription_id=subscription_id,
            )
        )

    return resource_groups


async def list_resources(
    credential: DefaultAzureCredential, subscription_id: str
) -> list[AzureResource]:
    """List all resources in a subscription."""
    client = ResourceManagementClient(credential=credential, subscription_id=subscription_id)
    resources: list[AzureResource] = []

    for resource in client.resources.list():
        # Extract resource group from ID
        resource_group = None
        if resource.id:
            parts = resource.id.split("/")
            if "resourceGroups" in parts:
                idx = parts.index("resourceGroups")
                if idx + 1 < len(parts):
                    resource_group = parts[idx + 1]

        resources.append(
            AzureResource(
                id=resource.id or "",
                name=resource.name or "",
                type=resource.type or "",
                location=resource.location or "",
                resource_group=resource_group,
                subscription_id=subscription_id,
            )
        )

    return resources


async def list_management_groups(credential: DefaultAzureCredential) -> list[ManagementGroup]:
    """List management groups."""
    # Note: Management Groups API requires separate client
    # For now, return empty list - can be enhanced later
    return []


async def list_advisor_recommendations(
    credential: DefaultAzureCredential, subscription_id: str
) -> list[AdvisorRecommendation]:
    """List Azure Advisor recommendations for a subscription."""
    client = AdvisorManagementClient(credential=credential, subscription_id=subscription_id)
    recommendations: list[AdvisorRecommendation] = []

    try:
        for rec in client.recommendations.list():
            recommendations.append(
                AdvisorRecommendation(
                    id=rec.id or "",
                    name=rec.name or "",
                    category=rec.category or "Unknown",
                    impact=rec.impact or "Unknown",
                    risk=rec.risk if hasattr(rec, "risk") else None,
                    short_description=(
                        rec.short_description.problem if rec.short_description else ""
                    ),
                    extended_properties=rec.extended_properties or {},
                    resource_metadata=rec.resource_metadata.as_dict() if rec.resource_metadata else {},
                )
            )
    except Exception:
        # Some subscriptions may not have Advisor enabled
        pass

    return recommendations


async def get_all_cost_recommendations(
    credential: DefaultAzureCredential, subscription_id: str
) -> list[AdvisorRecommendation]:
    """Get all cost-related recommendations."""
    all_recs = await list_advisor_recommendations(credential, subscription_id)
    return [rec for rec in all_recs if rec.category.lower() == "cost"]
