"""Microsoft Graph API client."""

import asyncio
from datetime import datetime

from azure.identity import DefaultAzureCredential
from msgraph import GraphServiceClient
from msgraph.generated.models.organization import Organization
from msgraph.generated.models.subscribed_sku import SubscribedSku
from msgraph.generated.models.user import User

from cost_center.collectors.types import (
    DirectorySubscription,
    GraphSubscribedSku,
    UserDetails,
    UserLicenseAssignment,
)


def build_graph_client(credential: DefaultAzureCredential) -> GraphServiceClient:
    """Build Microsoft Graph client."""
    return GraphServiceClient(credentials=credential, scopes=["https://graph.microsoft.com/.default"])


async def fetch_organization_profile(client: GraphServiceClient) -> Organization | None:
    """Fetch organization profile."""
    result = await client.organization.get()
    if result and result.value:
        return result.value[0]
    return None


async def fetch_subscribed_skus(client: GraphServiceClient) -> list[GraphSubscribedSku]:
    """Fetch subscribed SKUs from Graph API."""
    result = await client.subscribed_skus.get()
    skus: list[GraphSubscribedSku] = []

    if not result or not result.value:
        return skus

    for sku in result.value:
        prepaid = sku.prepaid_units or {}
        skus.append(
            GraphSubscribedSku(
                sku_id=sku.sku_id,
                sku_part_number=sku.sku_part_number or "Unknown",
                capacity_status=sku.capacity_status,
                consumed_units=sku.consumed_units or 0,
                enabled_units=prepaid.get("enabled", 0),
                prepaid_units_enabled=prepaid.get("enabled", 0),
                prepaid_units_suspended=prepaid.get("suspended", 0),
                prepaid_units_warning=prepaid.get("warning", 0),
            )
        )

    return skus


async def fetch_user_license_assignments(client: GraphServiceClient) -> list[UserLicenseAssignment]:
    """Fetch user license assignments."""
    result = await client.users.get(
        request_configuration=lambda config: setattr(
            config.query_parameters,
            "select",
            ["userPrincipalName", "displayName", "assignedLicenses"],
        )
    )

    assignments: list[UserLicenseAssignment] = []
    if not result or not result.value:
        return assignments

    for user in result.value:
        license_ids = [lic.sku_id for lic in (user.assigned_licenses or []) if lic.sku_id]
        assignments.append(
            UserLicenseAssignment(
                user_principal_name=user.user_principal_name or "Unknown",
                display_name=user.display_name or "Unknown",
                assigned_licenses=license_ids,
            )
        )

    return assignments


async def fetch_directory_subscriptions(client: GraphServiceClient) -> list[DirectorySubscription]:
    """Fetch directory subscriptions."""
    result = await client.directory.subscriptions.get()
    subscriptions: list[DirectorySubscription] = []

    if not result or not result.value:
        return subscriptions

    for sub in result.value:
        subscriptions.append(
            DirectorySubscription(
                sku_id=sub.sku_id or "Unknown",
                sku_part_number=sub.sku_part_number or "Unknown",
                total_licenses=sub.total_licenses,
            )
        )

    return subscriptions


async def get_default_domain_from_org(client: GraphServiceClient) -> str | None:
    """Get default domain from organization."""
    org = await fetch_organization_profile(client)
    if org and org.verified_domains:
        default = next((d.name for d in org.verified_domains if d.is_default), None)
        return default
    return None


async def list_users_with_details(client: GraphServiceClient) -> list[UserDetails]:
    """List users with detailed information."""
    result = await client.users.get(
        request_configuration=lambda config: setattr(
            config.query_parameters,
            "select",
            [
                "id",
                "userPrincipalName",
                "displayName",
                "accountEnabled",
                "userType",
                "createdDateTime",
                "signInActivity",
            ],
        )
    )

    users: list[UserDetails] = []
    if not result or not result.value:
        return users

    for user in result.value:
        # Handle sign-in activity (requires AAD Premium)
        last_sign_in = None
        if hasattr(user, "sign_in_activity") and user.sign_in_activity:
            last_sign_in = user.sign_in_activity.last_sign_in_date_time

        users.append(
            UserDetails(
                id=user.id or "",
                user_principal_name=user.user_principal_name or "Unknown",
                display_name=user.display_name or "Unknown",
                account_enabled=user.account_enabled or False,
                user_type=user.user_type,
                created_datetime=user.created_date_time,
                last_sign_in_datetime=last_sign_in,
            )
        )

    return users
