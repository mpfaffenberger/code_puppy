"""Shared runtime state for interactive prompt, queue, and shell coordination."""

from __future__ import annotations

import asyncio
import contextvars
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Literal

MAX_PROMPT_QUEUE = 25
PROMPT_STATUS_FRAME_INTERVAL = 0.09
PROMPT_STATUS_BACKOFF_WINDOW = 0.045
_ABOVE_PROMPT_RENDER_ACTIVE: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "above_prompt_render_active",
    default=False,
)


@dataclass
class QueuedPrompt:
    """Normalized queued prompt payload."""

    kind: Literal["queued", "interject"]
    text: str
    allow_command_dispatch: bool = True
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def preview_text(self) -> str:
        if self.kind == "interject":
            return f"[INTERJECT] {self.text}"
        return self.text


@dataclass
class PromptRuntimeState:
    """Single source of truth for interactive prompt state."""

    queue: list[QueuedPrompt] = field(default_factory=list)
    running: bool = False
    cancelling: bool = False
    bg_task: asyncio.Task | None = None
    shell_depth: int = 0
    queue_view_offset: int = 0
    pending_submission: str | None = None
    pending_submission_allow_command_dispatch: bool = True
    prompt_surface_kind: Literal["main"] | None = None
    prompt_session: object | None = None
    prompt_status_started_at: float | None = None
    prompt_status_task: asyncio.Task | None = None
    above_prompt_lock: asyncio.Lock | None = field(default=None, init=False, repr=False)
    above_prompt_lock_loop: asyncio.AbstractEventLoop | None = field(
        default=None,
        init=False,
        repr=False,
    )
    last_prompt_invalidation_at: float = 0.0
    last_spinner_invalidation_at: float = 0.0
    active_run_kind: Literal["agent", "interactive_command"] | None = None
    active_cancel_hook: Callable[[], None] | None = None
    active_cancel_requester: Callable[[str], None] | None = None
    queue_autodrain_suppressed: bool = False

    def mark_running(
        self,
        task: asyncio.Task,
        *,
        kind: Literal["agent", "interactive_command"] = "agent",
        cancel_hook: Callable[[], None] | None = None,
    ) -> None:
        self.running = True
        self.cancelling = False
        self.bg_task = task
        self.active_run_kind = kind
        self.active_cancel_hook = cancel_hook
        self.prompt_status_started_at = time.monotonic()
        self._ensure_prompt_status_task()
        self.invalidate_prompt()

    def mark_idle(self) -> None:
        self.running = False
        self.cancelling = False
        self.bg_task = None
        self.active_run_kind = None
        self.active_cancel_hook = None
        self.prompt_status_started_at = None
        self._stop_prompt_status_task()
        self.invalidate_prompt()

    def is_active_task(self, task: asyncio.Task | None) -> bool:
        return task is not None and self.bg_task is task

    def mark_idle_if_task(self, task: asyncio.Task | None) -> bool:
        if not self.is_active_task(task):
            return False
        self.mark_idle()
        return True

    def _can_enqueue(self) -> bool:
        return len(self.queue) < MAX_PROMPT_QUEUE

    def _clamp_queue_view_offset(self, *, max_visible: int = 3) -> None:
        max_start = max(0, len(self.queue) - max_visible)
        self.queue_view_offset = max(0, min(self.queue_view_offset, max_start))

    def request_queue(
        self, prompt: str, *, allow_command_dispatch: bool = True
    ) -> tuple[bool, int, QueuedPrompt | None]:
        if not self._can_enqueue():
            return False, len(self.queue), None
        item = QueuedPrompt(
            kind="queued",
            text=prompt,
            allow_command_dispatch=allow_command_dispatch,
        )
        self.queue.append(item)
        self._clamp_queue_view_offset()
        self.invalidate_prompt()
        return True, len(self.queue), item

    def request_interject(
        self, prompt: str, *, allow_command_dispatch: bool = True
    ) -> tuple[bool, int, QueuedPrompt | None]:
        if not self._can_enqueue():
            return False, len(self.queue), None
        item = QueuedPrompt(
            kind="interject",
            text=prompt,
            allow_command_dispatch=allow_command_dispatch,
        )
        self.queue.insert(0, item)
        self._clamp_queue_view_offset()
        self.invalidate_prompt()
        return True, 1, item

    def dequeue(self) -> QueuedPrompt | None:
        if not self.queue:
            return None
        value = self.queue.pop(0)
        self._clamp_queue_view_offset()
        self.invalidate_prompt()
        return value

    def dequeue_next_interject(self) -> QueuedPrompt | None:
        for index, item in enumerate(self.queue):
            if item.kind != "interject":
                continue
            value = self.queue.pop(index)
            self._clamp_queue_view_offset()
            self.invalidate_prompt()
            return value
        return None

    def queue_preview_texts(self) -> list[str]:
        return [item.preview_text() for item in self.queue]

    def has_pending_submission(self) -> bool:
        return bool(self.pending_submission)

    def set_pending_submission(
        self, text: str | None, *, allow_command_dispatch: bool = True
    ) -> None:
        self.pending_submission = text
        self.pending_submission_allow_command_dispatch = allow_command_dispatch
        self.invalidate_prompt()

    def take_pending_submission(self) -> str | None:
        text, _ = self.take_pending_submission_with_policy()
        return text

    def take_pending_submission_with_policy(self) -> tuple[str | None, bool]:
        text = self.pending_submission
        allow_command_dispatch = self.pending_submission_allow_command_dispatch
        self.pending_submission = None
        self.pending_submission_allow_command_dispatch = True
        self.invalidate_prompt()
        return text, allow_command_dispatch

    def has_active_shell(self) -> bool:
        return self.shell_depth > 0

    def notify_shell_started(self) -> None:
        self.shell_depth += 1
        self.invalidate_prompt()

    def notify_shell_finished(self) -> None:
        if self.shell_depth > 0:
            self.shell_depth -= 1
        self.invalidate_prompt()

    def has_active_interactive_command(self) -> bool:
        return self.active_run_kind == "interactive_command" and self.running

    def set_active_cancel_requester(
        self, requester: Callable[[str], None] | None
    ) -> None:
        self.active_cancel_requester = requester

    def request_active_cancel(self, reason: str) -> bool:
        if self.active_cancel_requester is None:
            return False
        self.active_cancel_requester(reason)
        return True

    def suppress_queue_autodrain(self) -> None:
        self.queue_autodrain_suppressed = True

    def clear_queue_autodrain_suppression(self) -> None:
        self.queue_autodrain_suppressed = False

    def is_queue_autodrain_suppressed(self) -> bool:
        return self.queue_autodrain_suppressed

    def shift_queue_view_offset(self, delta: int, *, max_visible: int = 3) -> bool:
        old_offset = self.queue_view_offset
        self._clamp_queue_view_offset(max_visible=max_visible)
        max_start = max(0, len(self.queue) - max_visible)
        self.queue_view_offset = max(0, min(self.queue_view_offset + delta, max_start))
        changed = self.queue_view_offset != old_offset
        if changed:
            self.invalidate_prompt()
        return changed

    def register_prompt_surface(
        self, session: object, kind: Literal["main"] = "main"
    ) -> None:
        self.prompt_surface_kind = kind
        self.prompt_session = session
        self._ensure_prompt_status_task()
        self.invalidate_prompt()

    def clear_prompt_surface(self, session: object | None = None) -> None:
        if session is not None and self.prompt_session is not session:
            return
        self.prompt_surface_kind = None
        self.prompt_session = None
        self._stop_prompt_status_task()

    def has_prompt_surface(self) -> bool:
        return self.prompt_session is not None

    def is_rendering_above_prompt(self) -> bool:
        return _ABOVE_PROMPT_RENDER_ACTIVE.get()

    def get_prompt_status_frame(self) -> str:
        from code_puppy.messaging.spinner.spinner_base import SpinnerBase

        if self.prompt_status_started_at is None:
            return SpinnerBase.FRAMES[0]

        elapsed = max(0.0, time.monotonic() - self.prompt_status_started_at)
        frame_index = int(elapsed / PROMPT_STATUS_FRAME_INTERVAL) % len(
            SpinnerBase.FRAMES
        )
        return SpinnerBase.FRAMES[frame_index]

    def invalidate_prompt(self) -> None:
        self._invalidate_prompt(low_priority=False)

    def invalidate_prompt_for_spinner(self) -> None:
        self._invalidate_prompt(low_priority=True)

    def _invalidate_prompt(self, *, low_priority: bool) -> None:
        app = getattr(self.prompt_session, "app", None)
        if app is None:
            return

        now = time.monotonic()
        if low_priority:
            if now - self.last_prompt_invalidation_at < PROMPT_STATUS_BACKOFF_WINDOW:
                return
            if (
                self.last_spinner_invalidation_at > 0
                and now - self.last_spinner_invalidation_at < PROMPT_STATUS_FRAME_INTERVAL
            ):
                return

        try:
            app.invalidate()
            if low_priority:
                self.last_spinner_invalidation_at = now
            else:
                self.last_prompt_invalidation_at = now
        except Exception:
            pass

    def _should_refresh_prompt_status(self) -> bool:
        return self.running and self.has_prompt_surface()

    def _get_above_prompt_lock(
        self, loop: asyncio.AbstractEventLoop
    ) -> asyncio.Lock:
        if self.above_prompt_lock is None or self.above_prompt_lock_loop is not loop:
            self.above_prompt_lock = asyncio.Lock()
            self.above_prompt_lock_loop = loop
        return self.above_prompt_lock

    async def _run_above_prompt_serialized(self, func: Callable[[], None]) -> None:
        from prompt_toolkit.application import run_in_terminal

        loop = asyncio.get_running_loop()
        lock = self._get_above_prompt_lock(loop)
        async with lock:
            token = _ABOVE_PROMPT_RENDER_ACTIVE.set(True)
            try:
                await run_in_terminal(func)
            finally:
                _ABOVE_PROMPT_RENDER_ACTIVE.reset(token)

    def _ensure_prompt_status_task(self) -> None:
        if not self._should_refresh_prompt_status():
            return
        if self.prompt_status_task is not None and not self.prompt_status_task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self.prompt_status_task = loop.create_task(self._prompt_status_loop())

    def _stop_prompt_status_task(self) -> None:
        task = self.prompt_status_task
        if task is None:
            return
        self.prompt_status_task = None
        if not task.done():
            task.cancel()

    async def _prompt_status_loop(self) -> None:
        current_task = asyncio.current_task()
        try:
            while self._should_refresh_prompt_status():
                self.invalidate_prompt_for_spinner()
                await asyncio.sleep(PROMPT_STATUS_FRAME_INTERVAL)
        except asyncio.CancelledError:
            pass
        finally:
            if self.prompt_status_task is current_task:
                self.prompt_status_task = None
            self.invalidate_prompt()

    def run_above_prompt(self, func: Callable[[], None], *, timeout: float = 5.0) -> bool:
        """Run a synchronous callback above the mounted prompt surface."""
        app = getattr(self.prompt_session, "app", None)
        loop = getattr(app, "loop", None)
        if app is None or loop is None or not loop.is_running():
            return False

        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        if current_loop is loop:
            return False

        async def _runner() -> None:
            await self._run_above_prompt_serialized(func)

        future = asyncio.run_coroutine_threadsafe(_runner(), loop)
        try:
            future.result(timeout=timeout)
            return True
        except Exception:
            future.cancel()
            return False

    async def run_above_prompt_async(self, func: Callable[[], None]) -> bool:
        """Run a synchronous callback above the mounted prompt from async code."""
        app = getattr(self.prompt_session, "app", None)
        loop = getattr(app, "loop", None)
        if app is None or loop is None or not loop.is_running():
            return False

        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            return False

        async def _runner() -> None:
            await self._run_above_prompt_serialized(func)

        try:
            if current_loop is loop:
                await _runner()
                return True

            future = asyncio.run_coroutine_threadsafe(_runner(), loop)
            await asyncio.wrap_future(future)
            return True
        except Exception:
            return False


_ACTIVE_RUNTIME: PromptRuntimeState | None = None


def register_active_interactive_runtime(runtime: PromptRuntimeState) -> None:
    global _ACTIVE_RUNTIME
    _ACTIVE_RUNTIME = runtime


def get_active_interactive_runtime() -> PromptRuntimeState | None:
    return _ACTIVE_RUNTIME


def clear_active_interactive_runtime(runtime: PromptRuntimeState | None = None) -> None:
    global _ACTIVE_RUNTIME
    if runtime is not None and _ACTIVE_RUNTIME is not runtime:
        return
    _ACTIVE_RUNTIME = None
