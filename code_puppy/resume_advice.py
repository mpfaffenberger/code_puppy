"""Non-destructive advice for large restored sessions."""

from code_puppy.i18n import format_number, t
from code_puppy.messaging import emit_warning


def suggest_compaction(total_tokens: int, context_length: int) -> None:
    """Suggest compaction above 50% of context, independent of auto-compaction."""
    threshold_tokens = context_length // 2
    if total_tokens > threshold_tokens:
        emit_warning(
            t(
                "cli.autosave.compact_suggestion",
                tokens=format_number(total_tokens),
                threshold=format_number(threshold_tokens),
            )
        )
