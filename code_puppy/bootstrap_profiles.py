"""Environment-aware install planning for constrained Code Puppy targets.

This module answers a narrow question without importing the Code Puppy
runtime: *given the current machine, what is the minimal supported way to
install Code Puppy here?*

It loads without the Code Puppy runtime/provider stack so a launcher or a fresh
source checkout can import it and inspect the environment before that heavy
dependency stack is available. The motivating case is a
constrained host such as Android/Termux, where prebuilt wheels are scarcer and
a lean first install avoids pulling optional integrations that may need to
build from source.
"""

from __future__ import annotations

import os
import platform
import shlex
import shutil
import sys
from pathlib import Path
from typing import Any

DEFAULT_PACKAGE_NAME = "code-puppy"

# Optional extras that exist in the distribution's
# ``[project.optional-dependencies]``. Keep this in sync with pyproject.toml.
_OPTIONAL_EXTRAS = ("bedrock", "computer-use", "durable")

# Extras whose dependencies are gated to a single platform via environment
# markers (e.g. ``sys_platform == 'darwin'``). On other platforms they install
# nothing, so the planner must not prescribe them there.
_DARWIN_ONLY_EXTRAS = frozenset({"computer-use"})

# ``lean`` attaches no optional extras (the safe default everywhere); ``full``
# attaches every extra that actually applies to the detected platform.
_PROFILES = ("full", "lean")


def available_profiles() -> list[str]:
    """Return the builtin profile names in a stable order."""
    return list(_PROFILES)


def detect_environment() -> dict[str, Any]:
    """Inspect the current machine using the standard library only."""
    executable = Path(sys.executable).expanduser().resolve()
    release = platform.release()
    system_name = platform.system()
    is_termux = (
        bool(os.environ.get("TERMUX_VERSION"))
        or "com.termux" in str(executable)
        or "com.termux" in os.environ.get("PREFIX", "")
    )
    is_android = is_termux or "android" in release.lower()

    return {
        "python_executable": str(executable),
        "python_version": platform.python_version(),
        "platform_system": system_name,
        "platform_release": release,
        "platform_machine": platform.machine(),
        "is_android": is_android,
        "is_termux": is_termux,
        "is_windows": system_name == "Windows",
        "is_macos": system_name == "Darwin",
        "is_linux": system_name == "Linux",
        "has_uv": shutil.which("uv") is not None,
        "has_rust": shutil.which("rustc") is not None
        and shutil.which("cargo") is not None,
        "has_clang": shutil.which("clang") is not None,
        "has_ripgrep": shutil.which("rg") is not None,
        "has_git": shutil.which("git") is not None,
    }


def applicable_optional_extras(environment: dict[str, Any]) -> list[str]:
    """Return the optional extras that can actually apply to this platform."""
    return [
        extra
        for extra in _OPTIONAL_EXTRAS
        if extra not in _DARWIN_ONLY_EXTRAS or environment.get("is_macos")
    ]


def resolve_profile_name(requested_profile: str | None) -> str:
    """Validate and normalize a requested profile name (default ``lean``)."""
    raw = (requested_profile or "lean").strip().lower()
    if not raw:
        raw = "lean"
    if raw not in _PROFILES:
        choices = ", ".join(available_profiles())
        raise ValueError(f"unknown install profile '{raw}'. Choices: {choices}")
    return raw


def _profile_extras(profile_name: str, environment: dict[str, Any]) -> list[str]:
    if profile_name == "full":
        return applicable_optional_extras(environment)
    return []


def package_spec(package_name: str, extras: list[str]) -> str:
    """Render a pip-style package spec, e.g. ``code-puppy[bedrock,durable]``."""
    if not extras:
        return package_name
    return f"{package_name}[{','.join(sorted(extras))}]"


def install_command(spec: str, environment: dict[str, Any]) -> str:
    if environment.get("has_uv"):
        return f"uv tool install --refresh {shlex.quote(spec)}"
    return f"python -m pip install {shlex.quote(spec)}"


def reattach_command(spec: str, environment: dict[str, Any]) -> str:
    """Command to (re)install with the full applicable extra set attached."""
    if environment.get("has_uv"):
        return f"uv tool install --refresh {shlex.quote(spec)}"
    return f"python -m pip install --upgrade {shlex.quote(spec)}"


def suggested_system_packages(environment: dict[str, Any]) -> list[dict[str, str]]:
    """Honest Termux package hints (empty on non-Android hosts).

    On Termux, PyPI's manylinux wheels do not apply (Android uses bionic libc),
    and several mandatory dependencies ship Rust/C native extensions with no
    Termux-compatible wheels -- so they compile on-device and a build toolchain
    is genuinely required. Only missing packages are returned, each tagged as a
    ``required`` build prerequisite or an ``optional`` convenience.
    """
    if not (environment.get("is_termux") or environment.get("is_android")):
        return []

    suggestions: list[dict[str, str]] = []
    if not environment.get("has_rust"):
        suggestions.append(
            {
                "package": "rust",
                "kind": "required",
                "reason": "Rust toolchain. Mandatory dependencies (e.g. "
                "pydantic-core, cryptography) are Rust native extensions with "
                "no Termux-compatible wheels and compile on-device.",
            }
        )
    if not environment.get("has_clang"):
        suggestions.append(
            {
                "package": "clang",
                "kind": "required",
                "reason": "C compiler. Mandatory dependencies (e.g. "
                "cryptography, Pillow) build C native extensions on-device.",
            }
        )
    if not environment.get("has_ripgrep"):
        suggestions.append(
            {
                "package": "ripgrep",
                "kind": "optional",
                "reason": "Speeds up file discovery; Code Puppy works without "
                "it. Not provided via pip on Android.",
            }
        )
    return suggestions


def _notes(
    profile_name: str,
    detached_extras: list[str],
    environment: dict[str, Any],
) -> list[str]:
    notes: list[str] = []
    if profile_name == "lean":
        notes.append(
            "Lean install: no optional extras are attached, keeping the first "
            "install minimal."
        )
    if environment.get("is_termux") or environment.get("is_android"):
        notes.append(
            "On Termux, mandatory native dependencies compile on-device, so "
            "installation can take materially longer than a wheel-based desktop "
            "install."
        )
    if detached_extras:
        notes.append(
            "Attach optional integrations later, once the environment is known "
            "good, using the reattach command."
        )
    return notes


def build_install_plan(
    *,
    requested_profile: str | None = None,
) -> dict[str, Any]:
    """Build a complete, serializable install plan for the current machine."""
    environment = detect_environment()
    profile = resolve_profile_name(requested_profile)
    extras = _profile_extras(profile, environment)
    spec = package_spec(DEFAULT_PACKAGE_NAME, extras)

    applicable = applicable_optional_extras(environment)
    detached_extras = [extra for extra in applicable if extra not in extras]
    full_spec = package_spec(DEFAULT_PACKAGE_NAME, applicable)

    return {
        "profile": profile,
        "package_spec": spec,
        "extras": extras,
        "detached_extras": detached_extras,
        "install_command": install_command(spec, environment),
        "reattach_command": reattach_command(full_spec, environment),
        "run_command": "code-puppy -i",
        "suggested_system_packages": suggested_system_packages(environment),
        "notes": _notes(profile, detached_extras, environment),
        "environment": environment,
    }
