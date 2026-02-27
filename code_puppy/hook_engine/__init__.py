"""Hook engine package for Code Puppy."""

from . import aliases
from .engine import HookEngine
from .models import (
    EventData,
    ExecutionResult,
    HookConfig,
    HookRegistry,
    ProcessEventResult,
)

__all__ = [
    "HookEngine",
    "HookConfig",
    "EventData",
    "ExecutionResult",
    "ProcessEventResult",
    "HookRegistry",
    "aliases",
]
