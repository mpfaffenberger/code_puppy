"""Report generation and Azure Blob Storage upload."""

import json
from datetime import UTC, datetime
from pathlib import Path

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

from cost_center.collectors.types import CostReport


DEFAULT_OUTPUT_DIR = Path("./out")
DEFAULT_STORAGE_ACCOUNT = "httcostcenter"
DEFAULT_CONTAINER = "cost-reports"


async def write_report_to_disk(report: CostReport, output_dir: Path | str | None = None) -> Path:
    """Write report to disk as JSON."""
    if output_dir is None:
        output_dir = DEFAULT_OUTPUT_DIR

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # Generate timestamp-based filename
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    filename = f"cost-report-{timestamp}.json"
    file_path = out_path / filename

    # Write report
    with file_path.open("w") as f:
        json.dump(report.model_dump(mode="json"), f, indent=2, default=str)

    # Also write as latest.json
    latest_path = out_path / "latest-report.json"
    with latest_path.open("w") as f:
        json.dump(report.model_dump(mode="json"), f, indent=2, default=str)

    return file_path


def build_blob_service_client(
    credential: DefaultAzureCredential, storage_account: str | None = None
) -> BlobServiceClient:
    """Build Azure Blob Storage client."""
    if storage_account is None:
        storage_account = DEFAULT_STORAGE_ACCOUNT

    account_url = f"https://{storage_account}.blob.core.windows.net"
    return BlobServiceClient(account_url=account_url, credential=credential)


async def upload_report_to_blob(
    report: CostReport,
    credential: DefaultAzureCredential,
    *,
    storage_account: str | None = None,
    container: str | None = None,
) -> str:
    """Upload report to Azure Blob Storage."""
    if storage_account is None:
        storage_account = DEFAULT_STORAGE_ACCOUNT
    if container is None:
        container = DEFAULT_CONTAINER

    # Build blob client
    blob_client = build_blob_service_client(credential, storage_account)
    container_client = blob_client.get_container_client(container)

    # Ensure container exists
    try:
        container_client.create_container()
    except Exception:
        pass  # Container already exists

    # Generate timestamp-based blob name
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    blob_name = f"cost-report-{timestamp}.json"

    # Upload report
    report_json = json.dumps(report.model_dump(mode="json"), indent=2, default=str)
    blob_client_upload = container_client.get_blob_client(blob_name)
    blob_client_upload.upload_blob(report_json, overwrite=True)

    # Also upload as latest-report.json
    latest_blob = container_client.get_blob_client("latest-report.json")
    latest_blob.upload_blob(report_json, overwrite=True)

    return f"https://{storage_account}.blob.core.windows.net/{container}/{blob_name}"
