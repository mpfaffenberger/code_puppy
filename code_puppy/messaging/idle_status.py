"""Initialize persistent context chrome without waiting for a model request."""

import logging
import threading

logger = logging.getLogger(__name__)
_refresh_lock = threading.Lock()


def refresh_context_status() -> None:
    """Schedule best-effort context initialization without blocking the prompt."""
    from code_puppy.i18n import t
    from code_puppy.messaging.bottom_bar import get_bottom_bar

    from code_puppy.messaging.speculation_stats import refresh_speculation_status

    refresh_speculation_status()
    bar = get_bottom_bar()
    if not bar.get_status():
        bar.set_status(t("stream.context.loading"))
    if not _refresh_lock.acquire(blocking=False):
        return

    def refresh() -> None:
        try:
            _refresh_context_status()
        finally:
            _refresh_lock.release()

    try:
        threading.Thread(
            target=refresh, name="idle-context-refresh", daemon=True
        ).start()
    except Exception:
        _refresh_lock.release()
        logger.debug("could not start idle context refresh", exc_info=True)


def _refresh_context_status() -> None:
    """Use the same formatter and decorated writer as live compaction updates.

    Retain the last good summary if current usage cannot be calculated.
    This is called at prompt boundaries, never on animation ticks.
    """
    try:
        from code_puppy.agents._compaction import update_spinner_context
        from code_puppy.messaging.spinner import format_context_info
        from code_puppy.token_usage import get_current_usage

        usage = get_current_usage()
        if usage is not None:
            update_spinner_context(
                format_context_info(
                    usage.total_tokens, usage.capacity, usage.proportion
                )
            )
    except Exception:
        logger.debug("idle context refresh failed", exc_info=True)
