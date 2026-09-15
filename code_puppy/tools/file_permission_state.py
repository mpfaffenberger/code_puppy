"""Core-side contract for the file-permission UX state.

The interactive file-permission flow is owned by a plugin (the built-in
``file_permission_handler``), which registers its ``file_permission``
decision callback through :mod:`code_puppy.callbacks`. Core never imports
the plugin: instead it reaches the shared *UX state* the flow relies on
through this small registration API:

* ``set_diff_already_shown`` / ``was_diff_already_shown`` /
  ``clear_diff_shown_flag`` - the "a diff preview was already rendered in
  the approval panel" flag so core can skip a redundant inline diff.
* ``get_last_user_feedback`` / ``clear_user_feedback`` - the feedback the
  user typed while rejecting, surfaced in the rejection response.

A provider (e.g. the file-permission plugin) installs thread-local
accessors with :func:`register_file_permission_state_provider`. Its plugin
owner is captured from the callback loading context, so disabling that owner
also disables this provider. Registrations can be explicitly unregistered
for unloads, and stale unload tokens cannot remove a replacement after reload.
Until an enabled provider is registered, core behaves exactly as it did before
the plugin could be imported: no diff was shown and no feedback is available.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

_DiffShownSetter = Callable[[bool], None]
_DiffShownGetter = Callable[[], bool]
_NoArg = Callable[[], None]
_FeedbackGetter = Callable[[], Optional[str]]


@dataclass(frozen=True)
class FilePermissionStateProvider:
    """Accessors registered by one plugin, plus its callback owner."""

    set_diff_already_shown: _DiffShownSetter
    was_diff_already_shown: _DiffShownGetter
    clear_diff_shown_flag: _NoArg
    get_last_user_feedback: _FeedbackGetter
    clear_user_feedback: _NoArg
    owner: Optional[str]


_provider: Optional[FilePermissionStateProvider] = None


def register_file_permission_state_provider(
    *,
    set_diff_already_shown: _DiffShownSetter,
    was_diff_already_shown: _DiffShownGetter,
    clear_diff_shown_flag: _NoArg,
    get_last_user_feedback: _FeedbackGetter,
    clear_user_feedback: _NoArg,
    owner: Optional[str] = None,
) -> FilePermissionStateProvider:
    """Install and return an ownership-aware provider registration token.

    The plugin loader's current owner is captured automatically. Calls only
    reach the provider while that owner is enabled under the same filtering
    used by the callback registry. Passing ``owner`` explicitly is useful for
    embedders and tests that register outside plugin loading.

    Re-registering replaces the current provider. The returned identity token
    can later be passed to :func:`unregister_file_permission_state_provider`;
    stale tokens cannot unregister a newer provider after reload.
    """
    from code_puppy.callbacks import get_loading_context

    provider = FilePermissionStateProvider(
        set_diff_already_shown=set_diff_already_shown,
        was_diff_already_shown=was_diff_already_shown,
        clear_diff_shown_flag=clear_diff_shown_flag,
        get_last_user_feedback=get_last_user_feedback,
        clear_user_feedback=clear_user_feedback,
        owner=owner if owner is not None else get_loading_context(),
    )
    global _provider
    _provider = provider
    return provider


def unregister_file_permission_state_provider(
    provider: FilePermissionStateProvider,
) -> bool:
    """Unregister *provider* if it is still the active registration."""
    global _provider
    if _provider is not provider:
        return False
    _provider = None
    return True


def _get_active_provider() -> Optional[FilePermissionStateProvider]:
    """Return the provider only while its owning plugin is enabled."""
    provider = _provider
    if provider is None:
        return None

    from code_puppy.callbacks import is_callback_owner_enabled

    return provider if is_callback_owner_enabled(provider.owner) else None


def set_diff_already_shown(shown: bool = True) -> None:
    """Record that a diff preview was rendered in the approval prompt."""
    provider = _get_active_provider()
    if provider is not None:
        provider.set_diff_already_shown(shown)


def was_diff_already_shown() -> bool:
    """Return True when a diff preview was already shown for this op."""
    provider = _get_active_provider()
    return provider.was_diff_already_shown() if provider is not None else False


def clear_diff_shown_flag() -> None:
    """Clear the diff-already-shown flag once it has been consumed."""
    provider = _get_active_provider()
    if provider is not None:
        provider.clear_diff_shown_flag()


def get_last_user_feedback() -> Optional[str]:
    """Return the user feedback captured by the last permission prompt."""
    provider = _get_active_provider()
    return provider.get_last_user_feedback() if provider is not None else None


def clear_user_feedback() -> None:
    """Clear the captured user feedback once it has been consumed."""
    provider = _get_active_provider()
    if provider is not None:
        provider.clear_user_feedback()
