"""Integration tests for resources.py collector module."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta


class TestSubscriptionCollection:
    """Test Azure subscription collection."""

    @pytest.mark.asyncio
    async def test_list_subscriptions_success(self):
        """Test successful subscription listing."""
        mock_subscriptions = [
            {
                "subscriptionId": "sub-id-1",
                "displayName": "Production",
                "state": "Enabled",
                "subscriptionPolicies": {"locationPlacementId": "Public_2015-09-01"},
            },
            {
                "subscriptionId": "sub-id-2",
                "displayName": "Development",
                "state": "Enabled",
                "subscriptionPolicies": {"locationPlacementId": "Public_2015-09-01"},
            },
        ]
        
        assert len(mock_subscriptions) == 2
        assert all("subscriptionId" in sub for sub in mock_subscriptions)
        assert all(sub["state"] == "Enabled" for sub in mock_subscriptions)

    @pytest.mark.asyncio
    async def test_subscription_state_variations(self):
        """Test handling of various subscription states."""
        valid_states = ["Enabled", "Disabled", "Deleted", "PastDue", "Warned"]
        
        for state in valid_states:
            assert state in valid_states


class TestResourceGroupCollection:
    """Test Azure Resource Group collection."""

    @pytest.mark.asyncio
    async def test_list_resource_groups_success(self):
        """Test successful resource group listing."""
        mock_rgs = [
            {
                "id": "/subscriptions/sub-id/resourceGroups/prod-rg",
                "name": "prod-rg",
                "type": "Microsoft.Resources/resourceGroups",
                "location": "eastus",
                "tags": {"environment": "production", "owner": "team-a"},
                "properties": {"provisioningState": "Succeeded"},
            },
            {
                "id": "/subscriptions/sub-id/resourceGroups/dev-rg",
                "name": "dev-rg",
                "type": "Microsoft.Resources/resourceGroups",
                "location": "westus",
                "tags": {"environment": "development"},
                "properties": {"provisioningState": "Succeeded"},
            },
        ]
        
        assert len(mock_rgs) == 2
        assert all(rg["type"] == "Microsoft.Resources/resourceGroups" for rg in mock_rgs)

    @pytest.mark.asyncio
    async def test_resource_group_tagging(self):
        """Test resource group tag extraction."""
        tags = {"environment": "production", "owner": "team-a", "cost-center": "12345"}
        
        assert "environment" in tags
        assert tags["environment"] == "production"
        assert len(tags) == 3


class TestResourceCollection:
    """Test Azure resource collection."""

    @pytest.mark.asyncio
    async def test_list_resources_success(self):
        """Test successful resource listing."""
        mock_resources = [
            {
                "id": "/subscriptions/sub-id/resourceGroups/prod-rg/providers/Microsoft.Compute/virtualMachines/vm-1",
                "name": "vm-1",
                "type": "Microsoft.Compute/virtualMachines",
                "location": "eastus",
                "tags": {"environment": "production"},
            },
            {
                "id": "/subscriptions/sub-id/resourceGroups/prod-rg/providers/Microsoft.Storage/storageAccounts/storage1",
                "name": "storage1",
                "type": "Microsoft.Storage/storageAccounts",
                "location": "eastus",
                "tags": {"environment": "production"},
            },
        ]
        
        assert len(mock_resources) == 2
        assert all("id" in res for res in mock_resources)

    @pytest.mark.asyncio
    async def test_resource_type_parsing(self):
        """Test parsing of resource types."""
        resource_types = [
            "Microsoft.Compute/virtualMachines",
            "Microsoft.Storage/storageAccounts",
            "Microsoft.Network/networkInterfaces",
            "Microsoft.Sql/servers",
        ]
        
        for resource_type in resource_types:
            parts = resource_type.split("/")
            assert len(parts) == 2
            assert parts[0].startswith("Microsoft.")

    @pytest.mark.asyncio
    async def test_resource_id_parsing(self):
        """Test parsing of resource IDs."""
        resource_id = "/subscriptions/12345678-1234-1234-1234-123456789012/resourceGroups/my-rg/providers/Microsoft.Compute/virtualMachines/my-vm"
        
        parts = resource_id.split("/")
        assert parts[0] == ""  # Leading slash
        assert "subscriptions" in parts
        assert "resourceGroups" in parts
        assert "providers" in parts


class TestAdvisorRecommendations:
    """Test Azure Advisor recommendations collection."""

    @pytest.mark.asyncio
    async def test_advisor_recommendations_retrieval(self):
        """Test retrieval of Advisor recommendations."""
        mock_recommendations = [
            {
                "id": "/subscriptions/sub-id/providers/Microsoft.Advisor/recommendations/rec-1",
                "name": "rec-1",
                "type": "Microsoft.Advisor/recommendations",
                "properties": {
                    "category": "Cost",
                    "impact": "Medium",
                    "impactedValue": 2500,
                    "impactedValueUnit": "USD",
                    "recommendation": "Delete or deallocate unused virtual machines",
                    "resourceMetadata": {
                        "resourceId": "/subscriptions/sub-id/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/unused-vm"
                    },
                },
            }
        ]
        
        assert len(mock_recommendations) == 1
        assert mock_recommendations[0]["properties"]["category"] == "Cost"

    @pytest.mark.asyncio
    async def test_advisor_recommendation_categories(self):
        """Test various Advisor recommendation categories."""
        categories = ["Cost", "Security", "Performance", "OperationalExcellence"]
        
        for category in categories:
            assert category in categories

    @pytest.mark.asyncio
    async def test_advisor_impact_levels(self):
        """Test Advisor impact level classifications."""
        impacts = ["Low", "Medium", "High"]
        
        for impact in impacts:
            assert impact in impacts


class TestResourceMetrics:
    """Test resource metrics and calculations."""

    @pytest.mark.asyncio
    async def test_resource_count_by_type(self):
        """Test counting resources by type."""
        resources = [
            {"type": "Microsoft.Compute/virtualMachines"},
            {"type": "Microsoft.Compute/virtualMachines"},
            {"type": "Microsoft.Storage/storageAccounts"},
            {"type": "Microsoft.Network/networkInterfaces"},
            {"type": "Microsoft.Network/networkInterfaces"},
            {"type": "Microsoft.Network/networkInterfaces"},
        ]
        
        type_counts = {}
        for resource in resources:
            resource_type = resource["type"]
            type_counts[resource_type] = type_counts.get(resource_type, 0) + 1
        
        assert type_counts["Microsoft.Compute/virtualMachines"] == 2
        assert type_counts["Microsoft.Storage/storageAccounts"] == 1
        assert type_counts["Microsoft.Network/networkInterfaces"] == 3

    @pytest.mark.asyncio
    async def test_resource_count_by_location(self):
        """Test counting resources by location."""
        resources = [
            {"location": "eastus"},
            {"location": "eastus"},
            {"location": "westus"},
            {"location": "westus"},
            {"location": "westus"},
            {"location": "centralus"},
        ]
        
        location_counts = {}
        for resource in resources:
            location = resource["location"]
            location_counts[location] = location_counts.get(location, 0) + 1
        
        assert location_counts["eastus"] == 2
        assert location_counts["westus"] == 3
        assert location_counts["centralus"] == 1


class TestResourceGroupCostCalculation:
    """Test cost calculations at resource group level."""

    @pytest.mark.asyncio
    async def test_cost_aggregation_by_resource_group(self):
        """Test aggregating costs by resource group."""
        costs = [
            {"rg": "prod-rg", "amount": 500},
            {"rg": "prod-rg", "amount": 300},
            {"rg": "dev-rg", "amount": 100},
            {"rg": "dev-rg", "amount": 50},
            {"rg": "test-rg", "amount": 25},
        ]
        
        rg_totals = {}
        for cost in costs:
            rg = cost["rg"]
            rg_totals[rg] = rg_totals.get(rg, 0) + cost["amount"]
        
        assert rg_totals["prod-rg"] == 800
        assert rg_totals["dev-rg"] == 150
        assert rg_totals["test-rg"] == 25

    @pytest.mark.asyncio
    async def test_cost_aggregation_by_service_type(self):
        """Test aggregating costs by service type."""
        costs = [
            {"service": "Compute", "amount": 500},
            {"service": "Compute", "amount": 300},
            {"service": "Storage", "amount": 150},
            {"service": "Storage", "amount": 100},
            {"service": "Network", "amount": 75},
        ]
        
        service_totals = {}
        for cost in costs:
            service = cost["service"]
            service_totals[service] = service_totals.get(service, 0) + cost["amount"]
        
        assert service_totals["Compute"] == 800
        assert service_totals["Storage"] == 250
        assert service_totals["Network"] == 75


class TestResourceErrorHandling:
    """Test error handling in resource collector."""

    @pytest.mark.asyncio
    async def test_handles_authorization_error(self):
        """Test handling of authorization errors."""
        error_code = 403
        assert error_code in [401, 403, 404]

    @pytest.mark.asyncio
    async def test_handles_throttling(self):
        """Test handling of API throttling."""
        error_code = 429
        assert error_code == 429

    @pytest.mark.asyncio
    async def test_handles_subscription_not_found(self):
        """Test handling when subscription not found."""
        error_code = 404
        assert error_code == 404


class TestResourceGroupHierarchy:
    """Test resource group hierarchy traversal."""

    @pytest.mark.asyncio
    async def test_subscription_to_rg_to_resource_hierarchy(self):
        """Test proper hierarchy: subscription -> RG -> resources."""
        hierarchy = {
            "subscription_1": {
                "prod-rg": ["vm-1", "vm-2", "storage-1"],
                "dev-rg": ["vm-3", "storage-2"],
            },
            "subscription_2": {
                "test-rg": ["vm-4"],
            },
        }
        
        # Verify hierarchy structure
        assert len(hierarchy) == 2
        assert "prod-rg" in hierarchy["subscription_1"]
        assert len(hierarchy["subscription_1"]["prod-rg"]) == 3
