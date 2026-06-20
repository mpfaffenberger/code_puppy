"""Platform and container shell sandbox command builders."""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class SandboxUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PreparedCommand:
    argv: tuple[str, ...]
    cwd: str
    backend: str
    sandboxed: bool


class SandboxBackend(Protocol):
    name: str

    def available(self) -> bool: ...

    def prepare(self, command: str, cwd: str) -> PreparedCommand: ...


def _shell_argv(command: str) -> tuple[str, ...]:
    if sys.platform.startswith("win"):
        return (os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", command)
    return ("/bin/sh", "-lc", command)


class NoneBackend:
    name = "none"

    def available(self) -> bool:
        return True

    def prepare(self, command: str, cwd: str) -> PreparedCommand:
        return PreparedCommand(_shell_argv(command), cwd, self.name, False)


class BubblewrapBackend:
    name = "bubblewrap"

    def available(self) -> bool:
        return bool(shutil.which("bwrap")) and sys.platform.startswith("linux")

    def prepare(self, command: str, cwd: str) -> PreparedCommand:
        root = str(Path(cwd).resolve())
        argv = (
            "bwrap",
            "--die-with-parent",
            "--unshare-all",
            "--ro-bind",
            "/",
            "/",
            "--bind",
            root,
            root,
            "--tmpfs",
            "/tmp",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--chdir",
            root,
            "/bin/sh",
            "-lc",
            command,
        )
        return PreparedCommand(argv, root, self.name, True)


class MacOSSandboxBackend:
    name = "sandbox_exec"

    def available(self) -> bool:
        return sys.platform == "darwin" and bool(shutil.which("sandbox-exec"))

    def prepare(self, command: str, cwd: str) -> PreparedCommand:
        root = str(Path(cwd).resolve())
        escaped = root.replace('"', '\\"')
        profile = (
            "(version 1)(deny default)(allow process*)"
            "(allow file-read*)"
            f'(allow file-write* (subpath "{escaped}"))'
            '(allow file-write* (subpath "/tmp"))'
            "(deny network*)"
        )
        argv = ("sandbox-exec", "-p", profile, "/bin/sh", "-lc", command)
        return PreparedCommand(argv, root, self.name, True)


class ContainerBackend:
    name = "container"

    def __init__(self, runtime: str | None = None, image: str | None = None):
        self.runtime = runtime or _container_runtime()
        self.image = image or _container_image()

    def available(self) -> bool:
        return bool(self.runtime and shutil.which(self.runtime))

    def prepare(self, command: str, cwd: str) -> PreparedCommand:
        root = str(Path(cwd).resolve())
        if not self.runtime:
            raise SandboxUnavailable("no Docker or Podman runtime found")
        argv = (
            self.runtime,
            "run",
            "--rm",
            "--network",
            "none",
            "--mount",
            f"type=bind,src={root},dst=/workspace",
            "--workdir",
            "/workspace",
            self.image,
            "/bin/sh",
            "-lc",
            command,
        )
        return PreparedCommand(argv, root, self.name, True)


def _container_runtime() -> str | None:
    from code_puppy.config import get_value

    configured = (get_value("sandbox_container_runtime") or "").strip()
    if configured:
        return configured
    return next((name for name in ("docker", "podman") if shutil.which(name)), None)


def _container_image() -> str:
    from code_puppy.config import get_value

    return (get_value("sandbox_container_image") or "python:3.13-slim").strip()


def get_sandbox_backend(name: str | None = None) -> SandboxBackend:
    from code_puppy.config import get_value

    selected = (name or get_value("sandbox_backend") or "none").strip().lower()
    if selected == "none":
        return NoneBackend()
    if selected in {"bubblewrap", "bwrap"}:
        return BubblewrapBackend()
    if selected in {"sandbox_exec", "sandbox-exec", "macos"}:
        return MacOSSandboxBackend()
    if selected in {"container", "docker", "podman"}:
        runtime = selected if selected in {"docker", "podman"} else None
        return ContainerBackend(runtime=runtime)
    if selected == "auto":
        candidates: tuple[SandboxBackend, ...] = (
            BubblewrapBackend(),
            MacOSSandboxBackend(),
            ContainerBackend(),
        )
        return next(
            (candidate for candidate in candidates if candidate.available()),
            candidates[-1],
        )
    raise ValueError(f"unknown sandbox backend: {selected}")


def prepare_shell_command(
    command: str,
    cwd: str | None,
    *,
    allow_unsandboxed_fallback: bool = False,
) -> PreparedCommand:
    root = str(Path(cwd or os.getcwd()).expanduser().resolve())
    backend = get_sandbox_backend()
    if backend.available():
        return backend.prepare(command, root)
    if allow_unsandboxed_fallback:
        return NoneBackend().prepare(command, root)
    raise SandboxUnavailable(
        f"configured sandbox backend {backend.name!r} is not available"
    )
