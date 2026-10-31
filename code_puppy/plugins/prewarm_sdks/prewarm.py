"""Background pre-import of provider SDKs for the active model family."""

from __future__ import annotations

import importlib
import logging
import os
import threading
from collections.abc import Iterable

logger = logging.getLogger(__name__)

OPT_OUT_ENV = "CODE_PUPPY_NO_PREWARM"
THREAD_NAME = "pup-sdk-prewarm"
_TRUTHY = frozenset({"1", "true", "yes", "on"})

FamilyRule = tuple[str, tuple[str, ...]]

_ANTHROPIC = ("anthropic",)
_OPENAI = ("openai",)

_families: list[FamilyRule] = [
    ("claude-", _ANTHROPIC),
    ("anthropic-", _ANTHROPIC),
    ("gpt-", _OPENAI),
    ("o1-", _OPENAI),
    ("o3-", _OPENAI),
    ("o4-", _OPENAI),
    ("chatgpt-", _OPENAI),
    ("codex-", _OPENAI),
]

_lock = threading.Lock()
_requested: set[str] = set()


def register_prewarm_families(rules: Iterable[FamilyRule]) -> None:
    """Add model-family rules (prefix -> SDK module names) for a build's providers."""
    with _lock:
        _families.extend(rules)


def modules_for_model(model_name: str | None) -> tuple[str, ...]:
    if not model_name:
        return ()
    name = model_name.lower()
    with _lock:
        families = tuple(_families)
    for prefix, modules in families:
        if name.startswith(prefix):
            return modules
    return ()


def is_opted_out() -> bool:
    return os.environ.get(OPT_OUT_ENV, "").strip().lower() in _TRUTHY


def _import_all(modules: tuple[str, ...]) -> None:
    for module_name in modules:
        try:
            importlib.import_module(module_name)
        except MemoryError:
            raise
        except Exception:
            logger.debug("SDK prewarm of %s failed", module_name, exc_info=True)


def start_prewarm(model_name: str | None) -> bool:
    """Start one daemon thread importing any not-yet-requested SDK modules."""
    modules = modules_for_model(model_name)
    with _lock:
        pending = tuple(module for module in modules if module not in _requested)
        if not pending:
            return False
        _requested.update(pending)
        try:
            threading.Thread(
                target=_import_all,
                args=(pending,),
                name=THREAD_NAME,
                daemon=True,
            ).start()
        except Exception:
            _requested.difference_update(pending)
            logger.debug("SDK prewarm thread failed to start", exc_info=True)
            return False
    return True


def start_prewarm_for_active_model() -> bool:
    if is_opted_out():
        return False
    from code_puppy.agents.agent_manager import get_current_agent
    from code_puppy.config import get_global_model_name

    model_name = get_current_agent().get_model_name() or get_global_model_name()
    return start_prewarm(model_name)
