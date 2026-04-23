"""Configuration constants for the AWS Bedrock plugin."""

from __future__ import annotations

import functools
import os
from pathlib import Path

from code_puppy.config import DATA_DIR

ENV_AWS_REGION = "AWS_REGION"
ENV_AWS_PROFILE = "AWS_PROFILE"
ENV_BEDROCK_REGION = "BEDROCK_REGION"

DEFAULT_REGION = "us-east-1"


@functools.lru_cache(maxsize=1)
def _detect_region() -> str | None:
    """Detect region from boto3 session or EC2 instance metadata.

    Result is cached for the process lifetime: on non-EC2 hosts with no
    AWS config, the IMDS path below incurs two 1-second timeouts, and
    this function is called on every model instantiation.
    """
    try:
        import boto3

        region = boto3.Session().region_name
        if region:
            return region
    except Exception:
        pass

    try:
        import urllib.request

        token_req = urllib.request.Request(
            "http://169.254.169.254/latest/api/token",
            method="PUT",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "30"},
        )
        token = urllib.request.urlopen(token_req, timeout=1).read().decode()
        region_req = urllib.request.Request(
            "http://169.254.169.254/latest/meta-data/placement/region",
            headers={"X-aws-ec2-metadata-token": token},
        )
        return urllib.request.urlopen(region_req, timeout=1).read().decode()
    except Exception:
        return None


MODELS: list[dict] = [
    {
        "base_key": "bedrock-opus-4-7",
        "model_id": "us.anthropic.claude-opus-4-7",
        "context_length": 1000000,
        "variants": ["default", "low", "medium", "high", "xhigh", "max"],
    },
    {
        "base_key": "bedrock-opus-4-6",
        "model_id": "us.anthropic.claude-opus-4-6-v1:0",
        "context_length": 1000000,
        "variants": ["default", "low", "medium", "high", "max"],
    },
    {
        "base_key": "bedrock-sonnet-4-6",
        "model_id": "us.anthropic.claude-sonnet-4-6-v1:0",
        "context_length": 1000000,
        "variants": ["default", "low", "medium", "high", "max"],
    },
    {
        "base_key": "bedrock-haiku",
        "model_id": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
        "context_length": 200000,
        "variants": None,
    },
]


def get_bedrock_region() -> str:
    """Get the AWS region for Bedrock.

    Precedence: BEDROCK_REGION > AWS_REGION > boto3 session > default.
    """
    return (
        os.environ.get(ENV_BEDROCK_REGION)
        or os.environ.get(ENV_AWS_REGION)
        or _detect_region()
        or DEFAULT_REGION
    )


def get_aws_profile() -> str | None:
    """Get the AWS profile name from environment."""
    return os.environ.get(ENV_AWS_PROFILE)


def get_extra_models_path() -> Path:
    """Get the path to the extra_models.json file."""
    return Path(DATA_DIR) / "extra_models.json"
