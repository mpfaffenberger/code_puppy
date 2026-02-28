"""Agent skills installation helpers.

This module currently provides the shared InstallResult type used by skill
installers (e.g. local installers, remote zip downloaders).

It is intentionally small so other modules can depend on a stable result shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True, slots=True)
class InstallResult:
    """Result of a skill install attempt."""

    success: bool
    message: str
    installed_path: Optional[Path] = None
