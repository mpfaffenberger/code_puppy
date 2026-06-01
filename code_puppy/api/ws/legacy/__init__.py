"""Legacy WebSocket implementation snapshot for puppy-desk migration.

This package is a reference/rollback copy captured during Gate 2 of the
puppy-desk migration. It is intentionally not imported or registered by the
runtime application yet; the active routes continue to come from
``code_puppy.api.ws``.

Do not edit this snapshot as part of feature work unless intentionally updating
the legacy rollback point.
"""

LEGACY_SNAPSHOT_PURPOSE = "puppy-desk-gate2-reference-copy"
