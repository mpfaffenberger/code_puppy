"""Non-destructive advice for large restored sessions."""

from code_puppy.config import get_compaction_threshold
from code_puppy.i18n import format_number, t
from code_puppy.messaging import emit_warning


def suggest_compaction(total_tokens: int, context_length: int) -> None:
    """Suggest manual compaction when restored history exceeds its trigger."""
    threshold_tokens = int(get_compaction_threshold() * context_length)
    if total_tokens > threshold_tokens:
        emit_warning(
            t(
                "cli.autosave.compact_suggestion",
                tokens=format_number(total_tokens),
                threshold=format_number(threshold_tokens),
            )
        )
