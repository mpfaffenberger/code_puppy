"""State for the Wiggum/goal continuation plugin."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WiggumState:
    """Tiny state container. No behavior soup, please and thank you."""

    active: bool = False
    prompt: str | None = None
    loop_count: int = 0
    mode: str = "wiggum"
    remediation_notes: str | None = None
    run_id: str | None = None

    def start(
        self,
        prompt: str,
        *,
        mode: str = "wiggum",
        run_id: str | None = None,
        loop_count: int = 0,
        remediation_notes: str | None = None,
    ) -> None:
        self.active = True
        self.prompt = prompt
        self.loop_count = loop_count
        self.mode = mode
        self.remediation_notes = remediation_notes
        self.run_id = run_id

    def stop(self) -> None:
        self.active = False
        self.prompt = None
        self.loop_count = 0
        self.mode = "wiggum"
        self.remediation_notes = None
        self.run_id = None

    def increment(self) -> int:
        self.loop_count += 1
        return self.loop_count


_STATE = WiggumState()


def get_state() -> WiggumState:
    return _STATE


def is_active() -> bool:
    return _STATE.active


def is_goal_mode() -> bool:
    return _STATE.active and _STATE.mode == "goal"


def get_prompt() -> str | None:
    return _STATE.prompt if _STATE.active else None


def start(
    prompt: str,
    *,
    mode: str = "wiggum",
    run_id: str | None = None,
    loop_count: int = 0,
    remediation_notes: str | None = None,
) -> None:
    _STATE.start(
        prompt,
        mode=mode,
        run_id=run_id,
        loop_count=loop_count,
        remediation_notes=remediation_notes,
    )


def stop() -> None:
    _STATE.stop()


def increment() -> int:
    return _STATE.increment()
