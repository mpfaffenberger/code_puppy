"""Interactive feedback wizard for Code Puppy.

Provides a `/feedback` slash command that launches a privacy-conscious
TUI for submitting bug reports, feature requests, and ratings to ATMT.

Privacy guarantees:
- ONLY the user's typed input is collected (subject + body).
- NO session history, NO prompts, NO file paths, NO error messages
  from the active session are captured automatically.
- Build metadata (Code Puppy version + OS platform) is included for
  triage and is non-PII.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning
from code_puppy.plugins.scheduler.scheduler_wizard import (
    MultilineInputMenu,
    SelectionMenu,
)


_TYPE_CHOICES = [
    ("rating", "⭐ Rating", "Rate Code Puppy 1-5 stars with a comment"),
    ("feature", "✨ Feature Request", "Suggest a new capability or improvement"),
    ("bug", "🐛 Bug Report", "Something broke or behaves incorrectly"),
]

# Hardcoded subject lines per type — keeps the wizard short (skip subject prompt).
_SUBJECTS = {
    "bug": "Report a Problem",
    "feature": "Feature Request",
    "rating": "General Feedback",
}

# Per-type prompt for the body field.
_BODY_PROMPTS = {
    "bug": "Describe the problem (what happened, what you expected)",
    "feature": "Describe the feature you'd like to see",
    "rating": "Tell us why (what's working, what isn't)",
}

_RATING_CHOICES = [
    ("5", "★★★★★  (5) Loved it"),
    ("4", "★★★★☆  (4) Liked it"),
    ("3", "★★★☆☆  (3) It's OK"),
    ("2", "★★☆☆☆  (2) Disliked it"),
    ("1", "★☆☆☆☆  (1) Hated it"),
]


def _pick_type() -> Optional[str]:
    """Show the type picker. Returns 'bug' | 'feature' | 'rating' | None."""
    labels = [label for _, label, _ in _TYPE_CHOICES]
    descs = [desc for _, _, desc in _TYPE_CHOICES]
    menu = SelectionMenu("What kind of feedback?", labels, descs)
    chosen = menu.run()
    if chosen is None:
        return None
    for key, label, _ in _TYPE_CHOICES:
        if label == chosen:
            return key
    return None


def _pick_rating() -> Optional[int]:
    """Show the 1-5 star picker. Returns int rating or None."""
    labels = [label for _, label in _RATING_CHOICES]
    menu = SelectionMenu("How would you rate Code Puppy?", labels)
    chosen = menu.run()
    if chosen is None:
        return None
    for value, label in _RATING_CHOICES:
        if label == chosen:
            return int(value)
    return None


def _confirm(summary_lines: list[str]) -> bool:
    """Show the summary and confirm submission."""
    print()
    print("  " + "─" * 56)
    print("  Review your feedback before submitting:")
    print("  " + "─" * 56)
    for line in summary_lines:
        print(f"  {line}")
    print("  " + "─" * 56)
    print()

    from code_puppy.command_line.utils import safe_input

    try:
        answer = safe_input("  Submit this feedback? [y/N]: ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        return False
    return answer in ("y", "yes")


def _print_privacy_notice() -> None:
    """Tell the user exactly what we collect — and what we don't."""
    print()
    print("  ┌─ 🔒 Privacy Notice ─────────────────────────────────────┐")
    print("  │ We collect ONLY what you type below, plus your username,│")
    print("  │ Code Puppy version, and OS platform (for triage).       │")
    print("  │ We DO NOT capture session history, prompts, file paths, │")
    print("  │ or any other context from your current session.         │")
    print("  └─────────────────────────────────────────────────────────┘")
    print()


async def _submit(
    feedback_type: str,
    subject: str,
    body: str,
    rating: int = 0,
) -> dict:
    """Call ATMT and return the raw result dict."""
    from code_puppy.plugins.walmart_specific.atmt_feedback import (
        atmt_submit_feedback,
    )

    return await atmt_submit_feedback(
        feedback_type=feedback_type,
        comment=body,
        subject=subject,
        rating=rating,
    )


def _run_async(coro_factory) -> dict:
    """Run an async coroutine to completion from sync code.

    Handles both "no event loop" (CLI startup) and "already in an event
    loop" (e.g., prompt_toolkit's TUI loop) cases. Takes a *factory* (not
    a coroutine) so the coroutine is only created right before being
    awaited — this avoids orphaned-coroutine warnings.
    """
    try:
        asyncio.get_running_loop()
        in_loop = True
    except RuntimeError:
        in_loop = False

    if not in_loop:
        return asyncio.run(coro_factory())

    # Inside an event loop — must offload to a worker thread with its own loop.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(lambda: asyncio.run(coro_factory())).result()


def run_feedback_wizard() -> None:
    """Run the full feedback wizard. Returns nothing — UI handles all output."""
    emit_info("\n📝 [bold cyan]Code Puppy Feedback[/bold cyan]")
    _print_privacy_notice()

    # Step 1: pick type
    feedback_type = _pick_type()
    if feedback_type is None:
        emit_warning("Feedback cancelled.")
        return

    # Step 2: rating-only — pick star count
    rating = 0
    if feedback_type == "rating":
        rating = _pick_rating() or 0
        if rating == 0:
            emit_warning("Feedback cancelled.")
            return

    # Step 3: body (required). Subject is hardcoded per type — no prompt needed.
    subject = _SUBJECTS[feedback_type]
    body_menu = MultilineInputMenu(_BODY_PROMPTS[feedback_type])
    body = body_menu.run()
    if not body or not body.strip():
        emit_warning("Feedback cancelled — no description provided.")
        return

    # Step 4: confirm
    summary = [
        f"Type:    {feedback_type.title()}",
        f"Subject: {subject}",
    ]
    if rating:
        summary.append(f"Rating:  {'★' * rating}{'☆' * (5 - rating)}  ({rating}/5)")
    summary.append("Body:")
    for line in body.splitlines() or [body]:
        summary.append(f"  {line}")

    if not _confirm(summary):
        emit_warning("Feedback cancelled.")
        return

    # Step 5: submit (async)
    emit_info("📤 Submitting to ATMT...")
    result = _run_async(
        lambda: _submit(feedback_type, subject, body, rating)
    )

    if result.get("success"):
        emit_success(
            f"✅ Your {feedback_type} feedback has been submitted. Thanks! 🐶"
        )
        return

    # Failure path — surface what went wrong from the result dict.
    err = result.get("error") or "Unknown error."
    emit_error(f"❌ Submission failed: {err}")
    action = result.get("action_required")
    if action:
        emit_warning(f"⚠️  Action required: {action}")
    else:
        emit_warning("You can try again with /feedback.")
