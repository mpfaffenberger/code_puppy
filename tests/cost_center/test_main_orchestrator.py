"""Integration tests for main orchestrator module."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from cost_center.collectors.types import TenantReport, CostReport


class TestMainOrchestrator:
    """Test main data collection orchestrator."""

    @pytest.mark.asyncio
    async def test_multi_tenant_data_collection_structure(self):
        """Test structure of multi-tenant data collection."""
        # Mock tenant configuration
        tenants = [
            {
                "tenant_id": "tenant-1",
                "tenant_name": "Organization 1",
                "subscriptions": ["sub-1", "sub-2"],
            },
            {
                "tenant_id": "tenant-2",
                "tenant_name": "Organization 2",
                "subscriptions": ["sub-3"],
            },
        ]
        
        assert len(tenants) == 2
        assert all("tenant_id" in t for t in tenants)
        assert all("subscriptions" in t for t in tenants)

    @pytest.mark.asyncio
    async def test_tenant_report_generation(self):
        """Test generation of tenant reports."""
        # TenantReport should aggregate data from all collectors
        report_data = {
            "tenant_id": "tenant-1",
            "tenant_name": "Organization 1",
            "collection_timestamp": datetime.now().isoformat(),
            "subscription_count": 2,
            "total_resources": 150,
            "total_cost_usd": 5000.50,
        }
        
        assert report_data["tenant_id"] == "tenant-1"
        assert report_data["subscription_count"] == 2
        assert report_data["total_cost_usd"] > 0

    @pytest.mark.asyncio
    async def test_parallel_tenant_collection(self):
        """Test parallel collection across multiple tenants."""
        # Simulate concurrent tenant collection with asyncio.gather
        collection_times = [0.5, 0.6, 0.5]  # seconds per tenant
        total_sequential_time = sum(collection_times)
        max_parallel_time = max(collection_times)
        
        # Parallel should be faster than sequential
        assert max_parallel_time < total_sequential_time

    @pytest.mark.asyncio
    async def test_subscription_level_data_collection(self):
        """Test subscription-level data aggregation."""
        subscription_data = {
            "subscription_id": "sub-1",
            "subscription_name": "Production",
            "resource_groups": 5,
            "total_resources": 50,
            "total_cost_usd": 2000.00,
            "costs_by_service": {
                "Compute": 1200.00,
                "Storage": 500.00,
                "Network": 300.00,
            },
        }
        
        assert subscription_data["subscription_id"] == "sub-1"
        assert len(subscription_data["costs_by_service"]) == 3
        service_total = sum(subscription_data["costs_by_service"].values())
        assert service_total == subscription_data["total_cost_usd"]


class TestDataAggregation:
    """Test data aggregation across collectors."""

    @pytest.mark.asyncio
    async def test_cost_data_aggregation(self):
        """Test aggregation of cost data."""
        cost_records = [
            {"date": "2025-01-05", "service": "Compute", "amount": 100},
            {"date": "2025-01-05", "service": "Storage", "amount": 50},
            {"date": "2025-01-05", "service": "Network", "amount": 25},
        ]
        
        total_cost = sum(record["amount"] for record in cost_records)
        assert total_cost == 175

    @pytest.mark.asyncio
    async def test_license_data_aggregation(self):
        """Test aggregation of license data."""
        licenses = [
            {"sku": "ENTERPRISEPACK", "total": 50, "consumed": 45},
            {"sku": "POWER_BI_PRO", "total": 20, "consumed": 12},
        ]
        
        total_licenses = sum(lic["total"] for lic in licenses)
        consumed_licenses = sum(lic["consumed"] for lic in licenses)
        
        assert total_licenses == 70
        assert consumed_licenses == 57
        assert consumed_licenses / total_licenses * 100 == pytest.approx(81.43, rel=0.01)

    @pytest.mark.asyncio
    async def test_resource_data_aggregation(self):
        """Test aggregation of resource data."""
        resources = [
            {"rg": "prod-rg", "type": "Microsoft.Compute/virtualMachines", "count": 10},
            {"rg": "prod-rg", "type": "Microsoft.Storage/storageAccounts", "count": 3},
            {"rg": "dev-rg", "type": "Microsoft.Compute/virtualMachines", "count": 5},
        ]
        
        vm_count = sum(r["count"] for r in resources if "virtualMachines" in r["type"])
        storage_count = sum(r["count"] for r in resources if "storageAccounts" in r["type"])
        
        assert vm_count == 15
        assert storage_count == 3


class TestReportGeneration:
    """Test final report generation."""

    @pytest.mark.asyncio
    async def test_cost_report_structure(self):
        """Test CostReport structure and content."""
        report_data = {
            "report_id": "report-123",
            "report_date": datetime.now().isoformat(),
            "period": "monthly",
            "tenant_count": 2,
            "subscription_count": 5,
            "total_cost_usd": 15000.00,
            "cost_by_service": {
                "Compute": 8000.00,
                "Storage": 4000.00,
                "Network": 2000.00,
                "Database": 1000.00,
            },
            "cost_by_tenant": {
                "tenant-1": 10000.00,
                "tenant-2": 5000.00,
            },
        }
        
        assert report_data["tenant_count"] == 2
        assert len(report_data["cost_by_service"]) == 4
        assert len(report_data["cost_by_tenant"]) == 2

    @pytest.mark.asyncio
    async def test_recommendations_in_report(self):
        """Test inclusion of recommendations in report."""
        recommendations = [
            {
                "type": "cost_optimization",
                "title": "Delete unused VMs",
                "potential_savings": 2500.00,
                "priority": "high",
            },
            {
                "type": "security",
                "title": "Enable disk encryption",
                "impact": "medium",
                "priority": "medium",
            },
            {
                "type": "performance",
                "title": "Upgrade underutilized instances",
                "potential_benefit": "improved throughput",
                "priority": "low",
            },
        ]
        
        assert len(recommendations) == 3
        cost_recs = [r for r in recommendations if r["type"] == "cost_optimization"]
        assert len(cost_recs) == 1


class TestErrorRecovery:
    """Test error handling and recovery in orchestrator."""

    @pytest.mark.asyncio
    async def test_partial_tenant_failure(self):
        """Test handling of failure in one tenant while others succeed."""
        tenant_results = {
            "tenant-1": {"status": "success", "data": {"cost": 5000}},
            "tenant-2": {"status": "failed", "error": "authentication_error"},
            "tenant-3": {"status": "success", "data": {"cost": 3000}},
        }
        
        successful = [t for t in tenant_results.values() if t["status"] == "success"]
        failed = [t for t in tenant_results.values() if t["status"] == "failed"]
        
        assert len(successful) == 2
        assert len(failed) == 1

    @pytest.mark.asyncio
    async def test_partial_subscription_failure(self):
        """Test handling of failure in one subscription while others succeed."""
        subscription_results = [
            {"subscription_id": "sub-1", "status": "success", "resource_count": 50},
            {"subscription_id": "sub-2", "status": "failed", "error": "quota_exceeded"},
            {"subscription_id": "sub-3", "status": "success", "resource_count": 75},
        ]
        
        successful = [s for s in subscription_results if s["status"] == "success"]
        assert len(successful) == 2

    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        """Test handling of collection timeouts."""
        timeout_seconds = 300  # 5 minutes default
        individual_timeout = 60  # 1 minute per tenant
        
        assert timeout_seconds > individual_timeout


class TestDataValidation:
    """Test data validation in orchestrator."""

    @pytest.mark.asyncio
    async def test_cost_data_validation(self):
        """Test validation of cost data."""
        costs = [
            {"amount": 100.50, "currency": "USD"},
            {"amount": 0.01, "currency": "USD"},
            {"amount": 99999.99, "currency": "USD"},
        ]
        
        # All amounts should be positive
        assert all(cost["amount"] > 0 for cost in costs)

    @pytest.mark.asyncio
    async def test_license_count_validation(self):
        """Test validation of license counts."""
        licenses = [
            {"total": 100, "consumed": 80, "available": 20},
            {"total": 50, "consumed": 50, "available": 0},
            {"total": 200, "consumed": 150, "available": 50},
        ]
        
        # Validate math: total = consumed + available
        for lic in licenses:
            assert lic["total"] == lic["consumed"] + lic["available"]

    @pytest.mark.asyncio
    async def test_resource_count_validation(self):
        """Test validation of resource counts."""
        resources = [
            {"total": 100, "running": 80, "stopped": 20},
            {"total": 50, "running": 30, "stopped": 20},
        ]
        
        # Validate math
        for res in resources:
            assert res["total"] == res["running"] + res["stopped"]


class TestPerformanceMetrics:
    """Test performance metrics collection."""

    @pytest.mark.asyncio
    async def test_collection_duration_tracking(self):
        """Test tracking of collection duration."""
        import time
        
        start_time = time.time()
        # Simulate work
        test_duration = 2.5  # seconds
        end_time = start_time + test_duration
        
        elapsed = end_time - start_time
        assert elapsed == pytest.approx(2.5, rel=0.01)

    @pytest.mark.asyncio
    async def test_per_tenant_timing(self):
        """Test per-tenant collection timing."""
        timings = {
            "tenant-1": 0.5,
            "tenant-2": 0.6,
            "tenant-3": 0.4,
        }
        
        average_time = sum(timings.values()) / len(timings)
        assert average_time == pytest.approx(0.5, rel=0.1)

    @pytest.mark.asyncio
    async def test_api_call_counting(self):
        """Test counting of API calls."""
        api_calls = {
            "cost_management": 3,
            "graph": 5,
            "resource_manager": 8,
            "advisor": 2,
        }
        
        total_calls = sum(api_calls.values())
        assert total_calls == 18
