"""Type definitions for cost center data structures."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TenantDefinition(BaseModel):
    """Configuration for a single tenant."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    tenant_id: str = Field(alias="tenantId")
    subscriptions: list[str] = Field(default_factory=list)
    github_org: str | None = Field(None, alias="githubOrg")


class AppConfig(BaseModel):
    """Application configuration."""

    model_config = ConfigDict(populate_by_name=True)

    azure_client_id: str = Field(alias="azureClientId")
    authority_host: str | None = Field(None, alias="authorityHost")
    admin_consent_redirect_uri: str | None = Field(None, alias="adminConsentRedirectUri")
    tenants: list[TenantDefinition]


class SubscriptionInfo(BaseModel):
    """Azure subscription information."""

    subscription_id: str
    display_name: str
    state: str
    tenant_id: str


class CostRecord(BaseModel):
    """Individual cost record from Azure Cost Management."""

    date: str
    subscription_id: str | None = None
    subscription_name: str | None = None
    resource_group: str | None = None
    resource_id: str | None = None
    meter_category: str | None = None
    service_name: str | None = None
    cost: float
    currency: str


class GraphSubscribedSku(BaseModel):
    """Microsoft Graph subscribed SKU."""

    sku_id: str | None = None
    sku_part_number: str
    capacity_status: str | None = None
    consumed_units: int = 0
    enabled_units: int = 0
    prepaid_units_enabled: int = 0
    prepaid_units_suspended: int = 0
    prepaid_units_warning: int = 0


class UserLicenseAssignment(BaseModel):
    """User license assignment details."""

    user_principal_name: str
    display_name: str
    assigned_licenses: list[str] = Field(default_factory=list)


class DirectorySubscription(BaseModel):
    """Directory subscription from Microsoft Graph."""

    sku_id: str
    sku_part_number: str
    total_licenses: int | None = None


class UserDetails(BaseModel):
    """Detailed user information."""

    id: str
    user_principal_name: str
    display_name: str
    account_enabled: bool = True
    user_type: str | None = None
    created_datetime: datetime | None = None
    last_sign_in_datetime: datetime | None = None


class ServicePrincipalInfo(BaseModel):
    """Service principal information."""

    id: str
    app_id: str
    display_name: str
    service_principal_type: str | None = None
    account_enabled: bool = True


class AppRegistrationInfo(BaseModel):
    """Application registration information."""

    id: str
    app_id: str
    display_name: str
    created_datetime: datetime | None = None
    sign_in_audience: str | None = None


class ManagementGroup(BaseModel):
    """Azure management group."""

    id: str
    name: str
    display_name: str
    tenant_id: str


class ResourceGroup(BaseModel):
    """Azure resource group."""

    id: str
    name: str
    location: str
    subscription_id: str


class AzureResource(BaseModel):
    """Azure resource."""

    id: str
    name: str
    type: str
    location: str
    resource_group: str | None = None
    subscription_id: str


class AdvisorRecommendation(BaseModel):
    """Azure Advisor recommendation."""

    id: str
    name: str
    category: str
    impact: str
    risk: str | None = None
    short_description: str
    extended_properties: dict[str, Any] = Field(default_factory=dict)
    resource_metadata: dict[str, Any] = Field(default_factory=dict)


class TenantReport(BaseModel):
    """Complete report for a single tenant."""

    tenant_name: str
    tenant_id: str
    collection_timestamp: datetime
    subscriptions: list[SubscriptionInfo] = Field(default_factory=list)
    costs: list[CostRecord] = Field(default_factory=list)
    resource_groups: list[ResourceGroup] = Field(default_factory=list)
    resources: list[AzureResource] = Field(default_factory=list)
    management_groups: list[ManagementGroup] = Field(default_factory=list)
    advisor_recommendations: list[AdvisorRecommendation] = Field(default_factory=list)
    subscribed_skus: list[GraphSubscribedSku] = Field(default_factory=list)
    user_licenses: list[UserLicenseAssignment] = Field(default_factory=list)
    directory_subscriptions: list[DirectorySubscription] = Field(default_factory=list)
    users: list[UserDetails] = Field(default_factory=list)
    service_principals: list[ServicePrincipalInfo] = Field(default_factory=list)
    applications: list[AppRegistrationInfo] = Field(default_factory=list)


class CostReport(BaseModel):
    """Complete multi-tenant cost report."""

    generated_at: datetime
    tenants: list[TenantReport] = Field(default_factory=list)
    version: str = "1.0"
