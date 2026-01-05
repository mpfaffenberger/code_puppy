"""Setup Azure Storage for cost center reports."""

import asyncio
import os
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient


STORAGE_ACCOUNT = os.getenv("AZURE_STORAGE_ACCOUNT", "httcostcenter")
CONTAINER_NAME = os.getenv("AZURE_STORAGE_CONTAINER", "cost-reports")


async def setup_storage() -> None:
    """Create storage container if it doesn't exist."""
    print(f"Setting up Azure Storage account: {STORAGE_ACCOUNT}")
    
    # Build credential
    credential = DefaultAzureCredential()
    
    # Build blob client
    account_url = f"https://{STORAGE_ACCOUNT}.blob.core.windows.net"
    blob_client = BlobServiceClient(account_url=account_url, credential=credential)
    
    # Create container
    try:
        container_client = blob_client.get_container_client(CONTAINER_NAME)
        container_client.create_container()
        print(f"✓ Container '{CONTAINER_NAME}' created successfully")
    except Exception as e:
        if "ContainerAlreadyExists" in str(e):
            print(f"✓ Container '{CONTAINER_NAME}' already exists")
        else:
            print(f"✗ Error creating container: {e}")
            raise
    
    # Set CORS rules for dashboard access
    try:
        blob_client.set_service_properties(
            cors=[
                {
                    "allowed_origins": ["*"],
                    "allowed_methods": ["GET"],
                    "allowed_headers": ["*"],
                    "exposed_headers": ["*"],
                    "max_age_in_seconds": 3600,
                }
            ]
        )
        print("✓ CORS rules configured")
    except Exception as e:
        print(f"Warning: Could not set CORS rules: {e}")
    
    print("\n✓ Storage setup complete!")


if __name__ == "__main__":
    asyncio.run(setup_storage())
