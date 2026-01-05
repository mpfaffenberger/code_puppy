"""Main orchestrator for cost center data collection."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from cost_center.collectors.auth import build_tenant_credential
from cost_center.collectors.cost import query_month_to_date_cost
from cost_center.collectors.graph import (
    build_graph_client,
    fetch_directory_subscriptions,
    fetch_subscribed_skus,
    fetch_user_license_assignments,
    list_users_with_details,
)
from cost_center.collectors.output import upload_report_to_blob, write_report_to_disk
from cost_center.collectors.resources import (
    list_advisor_recommendations,
    list_resource_groups,
    list_resources,
    list_subscriptions,
)
from cost_center.collectors.types import CostReport, TenantReport
from cost_center.config.loader import load_config

console = Console()


async def collect_tenant_data(tenant_name: str, tenant_id: str, subscription_ids: list[str]) -> TenantReport:
    """Collect all data for a single tenant."""
    console.print(f"[bold cyan]Collecting data for tenant: {tenant_name}[/bold cyan]")

    # Build credential
    credential = build_tenant_credential(tenant_id)

    # Build Graph client
    graph_client = build_graph_client(credential)

    # Collect data in parallel where possible
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        # Start tasks
        task1 = progress.add_task(f"[cyan]Fetching subscriptions...", total=None)
        task2 = progress.add_task(f"[cyan]Fetching Graph data...", total=None)
        task3 = progress.add_task(f"[cyan]Fetching costs...", total=None)

        # Collect subscriptions
        subscriptions = await list_subscriptions(credential)
        progress.update(task1, completed=True, description="[green]✓ Subscriptions fetched")

        # Collect Graph data
        subscribed_skus_task = fetch_subscribed_skus(graph_client)
        user_licenses_task = fetch_user_license_assignments(graph_client)
        directory_subs_task = fetch_directory_subscriptions(graph_client)
        users_task = list_users_with_details(graph_client)

        subscribed_skus, user_licenses, directory_subs, users = await asyncio.gather(
            subscribed_skus_task,
            user_licenses_task,
            directory_subs_task,
            users_task,
            return_exceptions=True,
        )

        # Handle exceptions
        subscribed_skus = subscribed_skus if not isinstance(subscribed_skus, Exception) else []
        user_licenses = user_licenses if not isinstance(user_licenses, Exception) else []
        directory_subs = directory_subs if not isinstance(directory_subs, Exception) else []
        users = users if not isinstance(users, Exception) else []

        progress.update(task2, completed=True, description="[green]✓ Graph data fetched")

        # Collect costs and resources for each subscription
        all_costs = []
        all_resource_groups = []
        all_resources = []
        all_recommendations = []

        for sub_id in subscription_ids:
            try:
                costs = await query_month_to_date_cost(credential, sub_id)
                all_costs.extend(costs)

                resource_groups = await list_resource_groups(credential, sub_id)
                all_resource_groups.extend(resource_groups)

                resources = await list_resources(credential, sub_id)
                all_resources.extend(resources)

                recommendations = await list_advisor_recommendations(credential, sub_id)
                all_recommendations.extend(recommendations)
            except Exception as e:
                console.print(f"[yellow]Warning: Failed to collect data for subscription {sub_id}: {e}[/yellow]")

        progress.update(task3, completed=True, description="[green]✓ Costs and resources fetched")

    return TenantReport(
        tenant_name=tenant_name,
        tenant_id=tenant_id,
        collection_timestamp=datetime.now(UTC),
        subscriptions=subscriptions,
        costs=all_costs,
        resource_groups=all_resource_groups,
        resources=all_resources,
        management_groups=[],
        advisor_recommendations=all_recommendations,
        subscribed_skus=subscribed_skus,
        user_licenses=user_licenses,
        directory_subscriptions=directory_subs,
        users=users,
        service_principals=[],
        applications=[],
    )


async def run_multi_tenant_audit(
    output_dir: Path | str | None = None,
    *,
    upload_to_blob: bool = True,
) -> CostReport:
    """Run multi-tenant audit and generate report."""
    console.print("[bold green]Starting Multi-Tenant Cost Center Audit[/bold green]\n")

    # Load configuration
    config = load_config()
    console.print(f"Loaded configuration for {len(config.tenants)} tenants\n")

    # Collect data for all tenants in parallel
    tenant_tasks = [
        collect_tenant_data(tenant.name, tenant.tenant_id, tenant.subscriptions)
        for tenant in config.tenants
    ]

    tenant_reports = await asyncio.gather(*tenant_tasks, return_exceptions=True)

    # Filter out exceptions
    valid_reports = [r for r in tenant_reports if not isinstance(r, Exception)]

    # Build final report
    report = CostReport(
        generated_at=datetime.now(UTC),
        tenants=valid_reports,
    )

    # Write to disk
    console.print("\n[bold cyan]Writing report to disk...[/bold cyan]")
    file_path = await write_report_to_disk(report, output_dir)
    console.print(f"[green]✓ Report written to: {file_path}[/green]")

    # Upload to blob if requested
    if upload_to_blob:
        console.print("\n[bold cyan]Uploading report to Azure Blob Storage...[/bold cyan]")
        try:
            credential = build_tenant_credential(config.tenants[0].tenant_id)
            blob_url = await upload_report_to_blob(report, credential)
            console.print(f"[green]✓ Report uploaded to: {blob_url}[/green]")
        except Exception as e:
            console.print(f"[yellow]Warning: Failed to upload to blob: {e}[/yellow]")

    console.print("\n[bold green]✓ Audit complete![/bold green]")
    return report


async def main() -> None:
    """Main entry point."""
    await run_multi_tenant_audit()


if __name__ == "__main__":
    asyncio.run(main())
