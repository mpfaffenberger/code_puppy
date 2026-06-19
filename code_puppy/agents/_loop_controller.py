"""Explicit state machine for the model/continuation loop."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LoopState(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    FOLLOW_UP = "follow_up"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class LoopAction(str, Enum):
    STEER = "steer"
    HOOK_RETRY = "hook_retry"
    STOP = "stop"


_ALLOWED_TRANSITIONS = {
    LoopState.CREATED: {LoopState.RUNNING, LoopState.CANCELLED, LoopState.FAILED},
    LoopState.RUNNING: {
        LoopState.FOLLOW_UP,
        LoopState.COMPLETED,
        LoopState.CANCELLED,
        LoopState.FAILED,
    },
    LoopState.FOLLOW_UP: {
        LoopState.FOLLOW_UP,
        LoopState.COMPLETED,
        LoopState.CANCELLED,
        LoopState.FAILED,
    },
    LoopState.COMPLETED: set(),
    LoopState.CANCELLED: set(),
    LoopState.FAILED: set(),
}


@dataclass(slots=True)
class LoopController:
    """Own loop state, budgets, and continuation priority."""

    max_hook_retries: int
    max_queued_steers: int = 50
    state: LoopState = LoopState.CREATED
    model_calls: int = 0
    hook_retries: int = 0
    queued_steers: int = 0

    def transition(self, target: LoopState) -> None:
        if target not in _ALLOWED_TRANSITIONS[self.state]:
            raise RuntimeError(
                f"Invalid agent loop transition: {self.state} -> {target}"
            )
        self.state = target

    def start(self) -> None:
        self.transition(LoopState.RUNNING)

    def record_model_call(self) -> None:
        if self.state not in {LoopState.RUNNING, LoopState.FOLLOW_UP}:
            raise RuntimeError(f"Cannot record model call while loop is {self.state}")
        self.model_calls += 1

    def next_action(
        self,
        *,
        steer_available: bool,
        hook_retry_requested: bool,
    ) -> LoopAction:
        if steer_available and self.queued_steers < self.max_queued_steers:
            self.queued_steers += 1
            self.transition(LoopState.FOLLOW_UP)
            return LoopAction.STEER
        if hook_retry_requested and self.hook_retries < self.max_hook_retries:
            self.hook_retries += 1
            self.transition(LoopState.FOLLOW_UP)
            return LoopAction.HOOK_RETRY
        self.transition(LoopState.COMPLETED)
        return LoopAction.STOP

    def fail(self) -> None:
        if self.state not in {
            LoopState.COMPLETED,
            LoopState.CANCELLED,
            LoopState.FAILED,
        }:
            self.transition(LoopState.FAILED)

    def cancel(self) -> None:
        if self.state not in {
            LoopState.COMPLETED,
            LoopState.CANCELLED,
            LoopState.FAILED,
        }:
            self.transition(LoopState.CANCELLED)
