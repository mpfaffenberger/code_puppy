"""Lazy internal bridge between plugin loading and optional i18n catalogs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


class _CatalogLoadFinalizer(Protocol):
    def __call__(
        self,
        transaction_id: object,
        *,
        parent_transaction_id: object | None,
        succeeded: bool,
    ) -> None: ...


@dataclass(frozen=True)
class _I18nLifecycleHooks:
    finish_load: _CatalogLoadFinalizer
    state_changed: Callable[[], None]


_hooks: _I18nLifecycleHooks | None = None


def register_i18n_lifecycle_hooks(
    *,
    finish_load: _CatalogLoadFinalizer,
    state_changed: Callable[[], None],
) -> None:
    """Install hooks when the optional i18n catalog module is imported."""
    global _hooks
    _hooks = _I18nLifecycleHooks(finish_load, state_changed)


def finish_i18n_plugin_load(
    transaction_id: object,
    *,
    parent_transaction_id: object | None,
    succeeded: bool,
) -> None:
    """Finalize catalog staging when i18n registered a lifecycle hook."""
    hooks = _hooks
    if hooks is not None:
        hooks.finish_load(
            transaction_id,
            parent_transaction_id=parent_transaction_id,
            succeeded=succeeded,
        )


def notify_i18n_plugin_state_changed() -> None:
    """Invalidate optional catalog snapshots when i18n registered a hook."""
    hooks = _hooks
    if hooks is not None:
        hooks.state_changed()
