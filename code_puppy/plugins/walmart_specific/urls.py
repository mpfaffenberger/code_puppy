from enum import Enum
from typing import Optional


class Environment(Enum):
    DEV = "dev"
    STAGE = "stg"
    PROD = "prod"


class BaseURLs:
    DEV = "https://puppy.dev.walmart.com"
    STAGE = "https://puppy.stg.walmart.com"
    PROD = "https://puppy.walmart.com"


def get_base_url(environment: Environment = Environment.PROD) -> str:
    if environment == Environment.DEV:
        return BaseURLs.DEV
    elif environment == Environment.STAGE:
        return BaseURLs.STAGE
    elif environment == Environment.PROD:
        return BaseURLs.PROD
    else:
        raise ValueError(f"Unsupported environment: {environment}")


def get_models_url(environment: Environment = Environment.PROD) -> str:
    base_url = get_base_url(environment)
    return f"{base_url}/api/puppy-models/latest"


def get_authentication_url(
    port: Optional[int] = None, environment: Environment = Environment.PROD
) -> str:
    base_url = get_base_url(environment)
    url = f"{base_url}/authenticate_puppy"

    if port is not None:
        url = f"{url}?port={port}"

    return url


def get_latest_version_url(environment: Environment = Environment.STAGE) -> str:
    base_url = get_base_url(environment)
    return f"{base_url}/api/releases/latest"


def get_setup_url(environment: Environment = Environment.STAGE) -> str:
    base_url = get_base_url(environment)
    return f"{base_url}/api/releases/setup"
