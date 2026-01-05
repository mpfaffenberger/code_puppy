"""Azure Cost Management API client."""

import asyncio
from datetime import datetime, timedelta
from typing import Any

from azure.identity import DefaultAzureCredential
from azure.mgmt.costmanagement import CostManagementClient
from azure.mgmt.costmanagement.models import (
    QueryAggregation,
    QueryColumnType,
    QueryDataset,
    QueryDefinition,
    QueryFilter,
    QueryGrouping,
    QueryTimePeriod,
    TimeframeType,
)

from cost_center.collectors.types import CostRecord


API_VERSION = "2023-11-01"
DEFAULT_GROUPINGS = ["ResourceGroupName", "ResourceId", "MeterCategory", "ServiceName"]


async def query_cost_breakdown(
    credential: DefaultAzureCredential,
    subscription_id: str,
    *,
    timeframe: TimeframeType = TimeframeType.MONTH_TO_DATE,
    groupings: list[str] | None = None,
) -> list[CostRecord]:
    """Query cost breakdown for a subscription."""
    if groupings is None:
        groupings = DEFAULT_GROUPINGS

    client = CostManagementClient(credential=credential)
    scope = f"/subscriptions/{subscription_id}"

    # Build query
    query_groupings = [
        QueryGrouping(type=QueryColumnType.DIMENSION, name=group) for group in groupings
    ]

    dataset = QueryDataset(
        granularity="Daily",
        aggregation={"totalCost": QueryAggregation(name="Cost", function="Sum")},
        grouping=query_groupings,
    )

    query = QueryDefinition(
        type="ActualCost",
        timeframe=timeframe,
        dataset=dataset,
    )

    # Execute query
    result = client.query.usage(scope=scope, parameters=query)

    # Parse results
    costs: list[CostRecord] = []
    if not result.rows:
        return costs

    # Map column names to indices
    column_map = {col.name: i for i, col in enumerate(result.columns)}

    for row in result.rows:
        costs.append(
            CostRecord(
                date=str(row[column_map.get("UsageDate", 0)]),
                subscription_id=subscription_id,
                resource_group=row[column_map.get("ResourceGroupName")] if "ResourceGroupName" in column_map else None,
                resource_id=row[column_map.get("ResourceId")] if "ResourceId" in column_map else None,
                meter_category=row[column_map.get("MeterCategory")] if "MeterCategory" in column_map else None,
                service_name=row[column_map.get("ServiceName")] if "ServiceName" in column_map else None,
                cost=float(row[column_map.get("Cost", 0)]),
                currency=row[column_map.get("Currency", "USD")],
            )
        )

    return costs


async def query_month_to_date_cost(
    credential: DefaultAzureCredential,
    subscription_id: str,
) -> list[CostRecord]:
    """Query month-to-date costs."""
    return await query_cost_breakdown(
        credential, subscription_id, timeframe=TimeframeType.MONTH_TO_DATE
    )


async def query_historical_costs(
    credential: DefaultAzureCredential,
    subscription_id: str,
    *,
    months: int = 12,
) -> list[CostRecord]:
    """Query historical costs for the past N months."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=months * 30)

    client = CostManagementClient(credential=credential)
    scope = f"/subscriptions/{subscription_id}"

    # Build query
    query_groupings = [
        QueryGrouping(type=QueryColumnType.DIMENSION, name=group)
        for group in DEFAULT_GROUPINGS
    ]

    dataset = QueryDataset(
        granularity="Monthly",
        aggregation={"totalCost": QueryAggregation(name="Cost", function="Sum")},
        grouping=query_groupings,
    )

    time_period = QueryTimePeriod(
        from_property=start_date.strftime("%Y-%m-%d"),
        to=end_date.strftime("%Y-%m-%d"),
    )

    query = QueryDefinition(
        type="ActualCost",
        timeframe=TimeframeType.CUSTOM,
        time_period=time_period,
        dataset=dataset,
    )

    # Execute query
    result = client.query.usage(scope=scope, parameters=query)

    # Parse results
    costs: list[CostRecord] = []
    if not result.rows:
        return costs

    # Map column names to indices
    column_map = {col.name: i for i, col in enumerate(result.columns)}

    for row in result.rows:
        costs.append(
            CostRecord(
                date=str(row[column_map.get("UsageDate", 0)]),
                subscription_id=subscription_id,
                resource_group=row[column_map.get("ResourceGroupName")] if "ResourceGroupName" in column_map else None,
                resource_id=row[column_map.get("ResourceId")] if "ResourceId" in column_map else None,
                meter_category=row[column_map.get("MeterCategory")] if "MeterCategory" in column_map else None,
                service_name=row[column_map.get("ServiceName")] if "ServiceName" in column_map else None,
                cost=float(row[column_map.get("Cost", 0)]),
                currency=row[column_map.get("Currency", "USD")],
            )
        )

    return costs
