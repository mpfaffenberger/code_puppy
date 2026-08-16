"""Shared diagnostics for optional and required runtime monkey patches."""

from __future__ import annotations

import logging

logger = logging.getLogger("code_puppy.pydantic_patches")

# Cleared and summarized by apply_all_patches().
LOUD_FAILURES: list[str] = []


def patch_failed(
    patch_name: str,
    exc: BaseException,
    consequence: str,
    target: str = "pydantic-ai",
) -> bool:
    """Log a loud, actionable error for a required patch failure."""
    LOUD_FAILURES.append(patch_name)
    logger.error(
        "pydantic_patches: %s FAILED to apply (%s internals changed?): %r — %s",
        patch_name,
        target,
        exc,
        consequence,
    )
    return False


def optional_lib_missing(patch_name: str, exc: ImportError) -> bool:
    """Quietly skip a patch whose optional dependency is absent."""
    logger.debug(
        "pydantic_patches: %s skipped (optional dependency missing): %r",
        patch_name,
        exc,
    )
    return False
