from __future__ import annotations

import json
import os
import platform
import shlex
import shutil
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

DEFAULT_PACKAGE_NAME = "code-puppy"

_BUILTIN_PROFILES: dict[str, dict[str, Any]] = {
    "core": {
        "description": "Lean base runtime with no optional extras attached.",
        "extras": [],
        "notes": [
            "Use this when a launcher only needs the core CLI/runtime.",
            "Optional capabilities should reattach later based on deployment policy.",
        ],
        "system_packages": [],
    },
    "android-termux-lean": {
        "description": "Android/Termux-safe profile that keeps Python deps lean.",
        "extras": [],
        "notes": [
            "Avoid browser/image/fuzzy/search/provider extras during initial attach.",
            "Reattach optional capabilities only after the target environment is known.",
        ],
        "system_packages": [
            "pkg install ripgrep",
            "pkg install proot",
        ],
    },
    "desktop-browser": {
        "description": "Desktop-oriented profile with local browser and UX helpers.",
        "extras": ["browser", "fuzzy", "images", "search"],
        "notes": [
            "Useful for developer laptops and desktop automation environments.",
        ],
        "system_packages": [],
    },
    "developer-full": {
        "description": "Broad developer profile with provider and tooling extras attached.",
        "extras": [
            "anthropic",
            "azure",
            "bedrock",
            "browser",
            "durable",
            "fuzzy",
            "images",
            "openai",
            "search",
        ],
        "notes": [
            "This is intentionally heavy; use it only when the environment is known-good.",
        ],
        "system_packages": [],
    },
}


def available_profiles() -> list[str]:
    return sorted(_BUILTIN_PROFILES)


def detect_environment() -> dict[str, Any]:
    executable = Path(sys.executable).expanduser().resolve()
    release = platform.release()
    system_name = platform.system()
    termux_prefix = os.environ.get("PREFIX", "")
    termux_version = os.environ.get("TERMUX_VERSION", "")
    is_termux = (
        bool(termux_version)
        or "com.termux" in str(executable)
        or (system_name == "Linux" and "com.termux" in termux_prefix)
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
        "has_uvx": shutil.which("uvx") is not None,
        "has_proot": shutil.which("proot") is not None,
        "has_ripgrep": shutil.which("rg") is not None,
        "has_git": shutil.which("git") is not None,
    }


def auto_profile_name(environment: dict[str, Any]) -> str:
    if environment.get("is_termux") or environment.get("is_android"):
        return "android-termux-lean"
    if environment.get("is_windows") or environment.get("is_macos"):
        return "desktop-browser"
    if environment.get("is_linux"):
        return "desktop-browser"
    return "core"


def resolve_profile_name(
    requested_profile: str | None, environment: dict[str, Any]
) -> str:
    raw = (
        requested_profile or os.environ.get("CODE_PUPPY_INSTALL_PROFILE", "auto")
    ).strip()
    if not raw or raw == "auto":
        return auto_profile_name(environment)
    if raw not in _BUILTIN_PROFILES:
        choices = ", ".join(available_profiles())
        raise ValueError(f"unknown install profile '{raw}'. Choices: auto, {choices}")
    return raw


def _parse_manifest_json(raw: str) -> dict[str, Any]:
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("bootstrap manifest must be a JSON object")
    return data


def load_manifest(
    *,
    manifest_json: str = "",
    manifest_file: str = "",
) -> dict[str, Any]:
    raw_json = (
        manifest_json.strip()
        or os.environ.get("CODE_PUPPY_BOOTSTRAP_MANIFEST_JSON", "").strip()
    )
    raw_file = (
        manifest_file.strip()
        or os.environ.get("CODE_PUPPY_BOOTSTRAP_MANIFEST_FILE", "").strip()
    )

    if raw_json and raw_file:
        raise ValueError("choose manifest_json or manifest_file, not both")
    if raw_json:
        return _parse_manifest_json(raw_json)
    if raw_file:
        return _parse_manifest_json(
            Path(raw_file).expanduser().read_text(encoding="utf-8")
        )
    return {}


def _normalize_list(value: Any, *, field_name: str) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(
            f"bootstrap manifest field '{field_name}' must be a list of strings"
        )
    return [item.strip() for item in value if item.strip()]


def merge_profile(
    profile_name: str,
    manifest: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    profile = deepcopy(_BUILTIN_PROFILES[profile_name])
    reasons = [f"base profile: {profile_name}"]
    manifest = manifest or {}
    if not manifest:
        return profile, reasons

    profile_override = manifest.get("profile", "")
    if profile_override and profile_override != profile_name:
        raise ValueError(
            f"manifest profile '{profile_override}' does not match resolved profile '{profile_name}'"
        )

    extras = set(profile["extras"])
    extras.update(_normalize_list(manifest.get("extras_add"), field_name="extras_add"))
    extras.difference_update(
        _normalize_list(manifest.get("extras_remove"), field_name="extras_remove")
    )
    profile["extras"] = sorted(extras)

    for key in ("notes", "system_packages"):
        profile[key] = profile[key] + _normalize_list(manifest.get(key), field_name=key)

    description = manifest.get("description", "")
    if description:
        if not isinstance(description, str):
            raise ValueError("bootstrap manifest field 'description' must be a string")
        profile["description"] = description.strip()

    package_name = manifest.get("package_name", "")
    if package_name:
        if not isinstance(package_name, str):
            raise ValueError("bootstrap manifest field 'package_name' must be a string")
        profile["package_name"] = package_name.strip()

    if manifest:
        reasons.append("manifest overrides applied")
    return profile, reasons


def package_spec(package_name: str, extras: list[str]) -> str:
    if not extras:
        return package_name
    return f"{package_name}[{','.join(sorted(extras))}]"


def install_command(spec: str, environment: dict[str, Any]) -> str:
    if environment.get("has_uv"):
        return f"uv tool install --refresh {shlex.quote(spec)}"
    return f"python -m pip install {shlex.quote(spec)}"


def reattach_command(spec: str, environment: dict[str, Any]) -> str:
    if environment.get("has_uv"):
        return f"uv tool install --refresh {shlex.quote(spec)}"
    return f"python -m pip install --upgrade {shlex.quote(spec)}"


def build_install_plan(
    *,
    requested_profile: str | None = None,
    manifest_json: str = "",
    manifest_file: str = "",
) -> dict[str, Any]:
    environment = detect_environment()
    resolved_profile = resolve_profile_name(requested_profile, environment)
    manifest = load_manifest(manifest_json=manifest_json, manifest_file=manifest_file)
    profile, reasons = merge_profile(resolved_profile, manifest)
    selected_package = profile.get("package_name", DEFAULT_PACKAGE_NAME)
    selected_extras = profile["extras"]
    spec = package_spec(selected_package, selected_extras)

    degraded = []
    if resolved_profile == "android-termux-lean":
        degraded = [
            "browser automation extras detached",
            "provider SDK extras detached",
            "image/fuzzy/search extras detached",
        ]

    missing_system_packages = []
    if resolved_profile == "android-termux-lean" and not environment.get("has_ripgrep"):
        missing_system_packages.append("ripgrep")
    if resolved_profile == "android-termux-lean" and not environment.get("has_proot"):
        missing_system_packages.append("proot")

    return {
        "profile": resolved_profile,
        "package_name": selected_package,
        "package_spec": spec,
        "description": profile["description"],
        "extras": selected_extras,
        "notes": profile["notes"],
        "system_packages": profile["system_packages"],
        "missing_system_packages": missing_system_packages,
        "environment": environment,
        "reasons": reasons,
        "install_command": install_command(spec, environment),
        "reattach_command": reattach_command(spec, environment),
        "run_command": "code-puppy -i",
        "degraded_capabilities": degraded,
        "manifest_applied": bool(manifest),
    }
