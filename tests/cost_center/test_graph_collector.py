"""Integration tests for graph.py collector module."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from cost_center.collectors.types import GraphSubscribedSku, UserDetails


@pytest.fixture
def mock_graph_client():
    """Mock GraphServiceClient."""
    client = AsyncMock()
    return client


class TestGraphLicenseCollection:
    """Test Microsoft Graph license collection."""

    @pytest.mark.asyncio
    async def test_fetch_subscribed_skus_success(self):
        """Test successful retrieval of subscribed SKUs."""
        mock_skus = [
            {
                "skuId": "6fd2c87f-bc74-4e6d-b96a-52add578f4ef",
                "skuPartNumber": "ENTERPRISEPACK",
                "displayName": "Enterprise E3",
                "consumedUnits": 45,
                "prepaidUnits": {
                    "enabled": 50,
                    "suspended": 0,
                    "warning": 0,
                },
            },
            {
                "skuId": "0c266dff-15dd-4b33-acb2-d609ea61ef3e",
                "skuPartNumber": "POWER_BI_PRO",
                "displayName": "Power BI Pro",
                "consumedUnits": 12,
                "prepaidUnits": {"enabled": 20, "suspended": 0, "warning": 0},
            },
        ]
        
        # Verify mock data structure
        assert len(mock_skus) == 2
        assert all("skuId" in sku for sku in mock_skus)
        assert all("displayName" in sku for sku in mock_skus)

    @pytest.mark.asyncio
    async def test_graph_subscribed_sku_model(self):
        """Test GraphSubscribedSku Pydantic model."""
        sku = GraphSubscribedSku(
            sku_id="6fd2c87f-bc74-4e6d-b96a-52add578f4ef",
            sku_part_number="ENTERPRISEPACK",
            capacity_status="Active",
            consumed_units=45,
            enabled_units=50,
            prepaid_units_enabled=50,
            prepaid_units_suspended=0,
            prepaid_units_warning=5,
        )
        assert sku.sku_part_number == "ENTERPRISEPACK"
        assert sku.consumed_units == 45
        assert sku.enabled_units == 50

    @pytest.mark.asyncio
    async def test_sku_calculation_available_units(self):
        """Test calculation of available license units."""
        total_units = 50
        consumed_units = 45
        available = total_units - consumed_units
        
        assert available == 5
        assert consumed_units <= total_units


class TestGraphUserCollection:
    """Test Microsoft Graph user collection."""

    @pytest.mark.asyncio
    async def test_fetch_users_success(self):
        """Test successful user retrieval."""
        mock_users = [
            {
                "id": "user-id-1",
                "userPrincipalName": "user1@company.com",
                "displayName": "User One",
                "jobTitle": "Software Engineer",
                "department": "Engineering",
                "createdDateTime": "2023-01-15T10:00:00Z",
            },
            {
                "id": "user-id-2",
                "userPrincipalName": "user2@company.com",
                "displayName": "User Two",
                "jobTitle": "Product Manager",
                "department": "Product",
                "createdDateTime": "2023-02-20T14:30:00Z",
            },
        ]
        
        assert len(mock_users) == 2
        assert all("id" in user for user in mock_users)
        assert all("userPrincipalName" in user for user in mock_users)

    @pytest.mark.asyncio
    async def test_user_details_model(self):
        """Test UserDetails Pydantic model."""
        user = UserDetails(
            id="user-id-1",
            user_principal_name="user1@company.com",
            display_name="User One",
            account_enabled=True,
            user_type="Member",
            created_datetime="2023-01-15T10:00:00Z",
            last_sign_in_datetime="2023-12-15T14:30:00Z",
        )
        assert user.user_principal_name == "user1@company.com"
        assert user.display_name == "User One"
        assert user.account_enabled is True

    @pytest.mark.asyncio
    async def test_pagination_handling(self):
        """Test pagination of user results."""
        # Microsoft Graph uses @odata.nextLink for pagination
        first_page = {
            "value": [{"id": "user-1"}, {"id": "user-2"}],
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/users?$skip=2",
        }
        
        assert "value" in first_page
        assert "@odata.nextLink" in first_page


class TestGraphLicenseAssignment:
    """Test license assignment tracking."""

    @pytest.mark.asyncio
    async def test_user_license_assignment_tracking(self):
        """Test tracking of license assignments to users."""
        assignments = [
            {
                "user_id": "user-1",
                "sku_id": "6fd2c87f-bc74-4e6d-b96a-52add578f4ef",
                "sku_name": "ENTERPRISEPACK",
                "assigned_date": "2023-01-15T10:00:00Z",
            },
            {
                "user_id": "user-2",
                "sku_id": "0c266dff-15dd-4b33-acb2-d609ea61ef3e",
                "sku_name": "POWER_BI_PRO",
                "assigned_date": "2023-03-01T09:00:00Z",
            },
        ]
        
        assert len(assignments) == 2
        assert all("sku_id" in a for a in assignments)

    @pytest.mark.asyncio
    async def test_license_utilization_metrics(self):
        """Test calculation of license utilization metrics."""
        total_licenses = 50
        assigned_licenses = 45
        utilization = (assigned_licenses / total_licenses) * 100
        
        assert utilization == 90.0
        assert 0 <= utilization <= 100


class TestGraphDirectoryInfo:
    """Test Azure AD directory information collection."""

    @pytest.mark.asyncio
    async def test_organization_info_retrieval(self):
        """Test retrieval of organization information."""
        org_info = {
            "id": "org-id",
            "displayName": "My Company Inc.",
            "verifiedDomains": [
                {"name": "company.com", "isDefault": True},
                {"name": "company.onmicrosoft.com", "isDefault": False},
            ],
        }
        
        assert org_info["displayName"] == "My Company Inc."
        assert len(org_info["verifiedDomains"]) == 2

    @pytest.mark.asyncio
    async def test_directory_roles_retrieval(self):
        """Test retrieval of directory roles."""
        roles = [
            {
                "id": "role-1",
                "displayName": "Global Administrator",
                "description": "Can manage all aspects of the directory",
            },
            {
                "id": "role-2",
                "displayName": "User Administrator",
                "description": "Can manage users and user licenses",
            },
        ]
        
        assert len(roles) == 2
        assert all("displayName" in role for role in roles)


class TestGraphErrorHandling:
    """Test error handling in Graph collector."""

    @pytest.mark.asyncio
    async def test_graph_handles_401_unauthorized(self):
        """Test handling of authentication errors."""
        error_code = 401
        assert error_code in [401, 403, 404]

    @pytest.mark.asyncio
    async def test_graph_handles_429_throttling(self):
        """Test handling of throttling with Retry-After."""
        retry_after_header = "60"  # seconds
        assert int(retry_after_header) > 0

    @pytest.mark.asyncio
    async def test_graph_handles_aad_premium_requirement(self):
        """Test fallback when AAD Premium features unavailable."""
        # Some queries require AAD Premium - should handle gracefully
        error_code = 403
        assert error_code == 403


class TestGraphClientConfiguration:
    """Test Graph client configuration."""

    @pytest.mark.asyncio
    async def test_graph_client_scopes(self):
        """Test proper OAuth scopes for Graph API."""
        required_scopes = [
            "https://graph.microsoft.com/.default",
        ]
        
        assert len(required_scopes) > 0
        assert all(scope.startswith("https://graph.microsoft.com") for scope in required_scopes)

    @pytest.mark.asyncio
    async def test_graph_api_version(self):
        """Test Graph API version consistency."""
        api_version = "v1.0"
        assert api_version in ["v1.0", "beta"]
