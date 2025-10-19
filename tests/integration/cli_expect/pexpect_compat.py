"""Compatibility helpers for cross-platform pexpect usage."""

from __future__ import annotations

import os
import shlex
import sys
from typing import Sequence

import pexpect
from pexpect.spawnbase import SpawnBase

IS_WINDOWS = os.name == "nt" or sys.platform.startswith("win")

SpawnChild = SpawnBase

__all__ = ["SpawnChild", "spawn_process", "IS_WINDOWS"]


def _normalize_command(command: Sequence[str] | str) -> Sequence[str] | str:
    """Ensure commands are formatted correctly across platforms."""
    if isinstance(command, str):
        return command
    if IS_WINDOWS:
        return " ".join(shlex.quote(part) for part in command)
    return command


def spawn_process(
    command: Sequence[str] | str,
    *,
    encoding: str = "utf-8",
    timeout: float | None = None,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
) -> SpawnChild:
    """Spawn a child process using the appropriate pexpect backend."""
    normalized_command = _normalize_command(command)

    if IS_WINDOWS:
        process_env = os.environ.copy()
        if env:
            process_env.update(env)
        child: SpawnChild = pexpect.popen_spawn.PopenSpawn(
            normalized_command,
            timeout=timeout,
            encoding=encoding,
            cwd=cwd,
            env=process_env,
        )
        return child

    if isinstance(normalized_command, str):
        return pexpect.spawn(
            normalized_command,
            timeout=timeout,
            encoding=encoding,
            env=env,
            cwd=cwd,
        )

    return pexpect.spawn(
        normalized_command[0],
        args=list(normalized_command[1:]),
        timeout=timeout,
        encoding=encoding,
        env=env,
        cwd=cwd,
    )
