"""Retired legacy session seeder.

The application now treats SQLite + JSON session files as the only supported
runtime storage format. The old pickle-to-SQLite migration path has been
removed; this module remains only as a compatibility import target.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def seed_from_pkl_dirs() -> None:
    """No-op compatibility shim for the retired pickle migration path."""
    logger.debug("Legacy session seeder is retired; nothing to migrate")
