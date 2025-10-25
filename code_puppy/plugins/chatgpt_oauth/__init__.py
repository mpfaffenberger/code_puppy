"""ChatGPT OAuth plugin package."""

from __future__ import annotations

from . import register_callbacks  # noqa: F401
from .oauth_flow import run_oauth_flow

__all__ = ["run_oauth_flow"]
