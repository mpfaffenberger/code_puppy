"""Queued-message navigation for the persistent prompt editor.

Queued turns are temporarily removed from ``PauseController`` while the user
edits them. This prevents the runtime from consuming the stale version during
the edit and avoids submitting an edited copy beside the original.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class QueuedMessageNavigator:
    """Reserve queued turns and expose them as editable history entries."""

    def __init__(self, controller_provider: Callable[[], Any]) -> None:
        self._controller_provider = controller_provider
        self._originals: list[str] = []  # newest -> oldest
        self._drafts: list[str] = []  # newest -> oldest
        self._index = -1
        self._working = ""

    @property
    def active(self) -> bool:
        return self._index >= 0

    def up(self, current: str) -> tuple[bool, str, list[str]]:
        """Recall an older queued turn, or hand off to regular history.

        Returns ``(handled, text, history_suppressions)``. Suppressions are
        newest-first queue entries that regular history should skip once, since
        queued submissions are already present in the on-disk history.
        """
        if self.active:
            self._drafts[self._index] = current
            next_index = self._index + 1
            if next_index < len(self._drafts):
                self._index = next_index
                return True, self._drafts[self._index], []
        else:
            self._working = current

        item = self._pop_latest()
        if item is not None:
            self._originals.append(item)
            self._drafts.append(item)
            self._index = len(self._drafts) - 1
            return True, item, []

        working = self._working
        suppressions = list(self._originals)
        self._restore(self._drafts)
        return False, working, suppressions

    def down(self, current: str) -> tuple[bool, str]:
        """Recall a newer reserved turn, then the pre-navigation draft."""
        if not self.active:
            return False, current
        self._drafts[self._index] = current
        if self._index > 0:
            self._index -= 1
            return True, self._drafts[self._index]

        working = self._working
        self._restore(self._drafts)
        return True, working

    def prepare_submit(self, text: str, mode: str) -> bool | None:
        """Commit an edit and say whether normal submission should continue.

        ``None`` means no queued item is being edited. ``False`` means an
        Enter submission updated the queued item in place. ``True`` means
        Ctrl+Enter removed that item from the queue and should route it as an
        immediate steer.
        """
        if not self.active:
            return None
        if not text.strip():
            self._restore(self._originals)
            return False

        self._drafts[self._index] = text
        if mode == "now":
            remaining = [
                draft
                for index, draft in enumerate(self._drafts)
                if index != self._index
            ]
            self._restore(remaining)
            return True

        self._restore(self._drafts)
        return False

    def cancel(self) -> None:
        """Abandon edits and put every reserved turn back unchanged."""
        if self.active:
            self._restore(self._originals)

    def _pop_latest(self) -> str | None:
        try:
            return self._controller_provider().pop_latest_steer_queued()
        except (AttributeError, TypeError):
            return None
        except Exception:
            logger.debug("queued message recall failed", exc_info=True)
            return None

    def _restore(self, newest_first: list[str]) -> None:
        oldest_first = list(reversed(newest_first))
        if oldest_first:
            controller = None
            try:
                controller = self._controller_provider()
                controller.restore_pending_steer_queued(oldest_first)
            except Exception:
                logger.debug(
                    "queued message restore failed; falling back", exc_info=True
                )
                try:
                    if controller is None:
                        controller = self._controller_provider()
                    for item in oldest_first:
                        controller.request_steer(item, mode="queue")
                except Exception:
                    logger.exception("queued messages could not be restored")
        self._originals = []
        self._drafts = []
        self._index = -1
        self._working = ""


__all__ = ["QueuedMessageNavigator"]
