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
accessors with :func:`register_file_permission_state_provider`. Until one
is registered, core behaves exactly as it did before the plugin could be
imported: no diff was shown and no feedback is available.
"""

from __future__ import annotations

from typing import Callable, Optional

_DiffShownSetter = Callable[[bool], None]
_DiffShownGetter = Callable[[], bool]
_NoArg = Callable[[], None]
_FeedbackGetter = Callable[[], Optional[str]]

_diff_shown_setter: Optional[_DiffShownSetter] = None
_diff_shown_getter: Optional[_DiffShownGetter] = None
_diff_shown_clearer: Optional[_NoArg] = None
_feedback_getter: Optional[_FeedbackGetter] = None
_feedback_clearer: Optional[_NoArg] = None


def register_file_permission_state_provider(
    *,
    set_diff_already_shown: _DiffShownSetter,
    was_diff_already_shown: _DiffShownGetter,
    clear_diff_shown_flag: _NoArg,
    get_last_user_feedback: _FeedbackGetter,
    clear_user_feedback: _NoArg,
) -> None:
    """Install the accessors behind the file-permission UX state.

    Called by a file-permission provider (e.g. the built-in
    ``file_permission_handler`` plugin) at load time. All five accessors
    are required: they form the single cohesion unit -- thread-local state
    shared between the approval prompt and core's diff/rejection plumbing.

    Until a provider is registered every accessor falls back to a default
    that mirrors the pre-decoupling behavior of an absent plugin: no diff
    was shown and no user feedback is available.
    """
    global _diff_shown_setter, _diff_shown_getter, _diff_shown_clearer
    global _feedback_getter, _feedback_clearer
    _diff_shown_setter = set_diff_already_shown
    _diff_shown_getter = was_diff_already_shown
    _diff_shown_clearer = clear_diff_shown_flag
    _feedback_getter = get_last_user_feedback
    _feedback_clearer = clear_user_feedback


def set_diff_already_shown(shown: bool = True) -> None:
    """Record that a diff preview was rendered in the approval prompt."""
    if _diff_shown_setter is not None:
        _diff_shown_setter(shown)


def was_diff_already_shown() -> bool:
    """Return True when a diff preview was already shown for this op."""
    if _diff_shown_getter is not None:
        return _diff_shown_getter()
    return False


def clear_diff_shown_flag() -> None:
    """Clear the diff-already-shown flag once it has been consumed."""
    if _diff_shown_clearer is not None:
        _diff_shown_clearer()


def get_last_user_feedback() -> Optional[str]:
    """Return the user feedback captured by the last permission prompt."""
    if _feedback_getter is not None:
        return _feedback_getter()
    return None


def clear_user_feedback() -> None:
    """Clear the captured user feedback once it has been consumed."""
    if _feedback_clearer is not None:
        _feedback_clearer()
