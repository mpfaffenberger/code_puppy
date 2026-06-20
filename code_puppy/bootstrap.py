from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from code_puppy.bootstrap_profiles import (
    available_profiles,
    build_install_plan,
    detect_environment,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Code Puppy bootstrap planner for lean environment-aware installs"
    )
    subparsers = parser.add_subparsers(dest="command")

    detect_parser = subparsers.add_parser(
        "detect",
        help="Inspect the current environment without importing the runtime CLI",
    )
    detect_parser.add_argument("--json", action="store_true", help="Print JSON output")

    plan_parser = subparsers.add_parser(
        "plan",
        help="Build a lean install/reattach plan from a builtin profile and optional manifest",
    )
    plan_parser.add_argument(
        "--profile",
        default="auto",
        choices=["auto", *available_profiles()],
        help="Builtin install profile to use",
    )
    plan_parser.add_argument(
        "--manifest-json",
        default="",
        help="Inline JSON manifest with extras_add/extras_remove/notes overrides",
    )
    plan_parser.add_argument(
        "--manifest-file",
        default="",
        help="Path to a JSON manifest file with plan overrides",
    )
    plan_parser.add_argument("--json", action="store_true", help="Print JSON output")

    return parser


def _human_detect(environment: dict[str, Any]) -> str:
    lines = [
        "Code Puppy bootstrap environment",
        f"- python: {environment['python_executable']}",
        f"- version: {environment['python_version']}",
        f"- platform: {environment['platform_system']} {environment['platform_release']} ({environment['platform_machine']})",
        f"- termux: {'yes' if environment['is_termux'] else 'no'}",
        f"- android: {'yes' if environment['is_android'] else 'no'}",
        f"- uv: {'yes' if environment['has_uv'] else 'no'}",
        f"- uvx: {'yes' if environment['has_uvx'] else 'no'}",
        f"- proot: {'yes' if environment['has_proot'] else 'no'}",
        f"- ripgrep: {'yes' if environment['has_ripgrep'] else 'no'}",
    ]
    return "\n".join(lines)


def _human_plan(plan: dict[str, Any]) -> str:
    lines = [
        f"Profile: {plan['profile']}",
        f"Package spec: {plan['package_spec']}",
        f"Install: {plan['install_command']}",
        f"Reattach: {plan['reattach_command']}",
        f"Run: {plan['run_command']}",
    ]
    if plan["extras"]:
        lines.append(f"Extras: {', '.join(plan['extras'])}")
    if plan["degraded_capabilities"]:
        lines.append("Degraded until reattach:")
        lines.extend(f"- {item}" for item in plan["degraded_capabilities"])
    if plan["system_packages"]:
        lines.append("Suggested system packages:")
        lines.extend(f"- {item}" for item in plan["system_packages"])
    if plan["notes"]:
        lines.append("Notes:")
        lines.extend(f"- {item}" for item in plan["notes"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    command = args.command or "plan"

    try:
        if command == "detect":
            environment = detect_environment()
            if args.json:
                print(json.dumps(environment, indent=2, sort_keys=True))
            else:
                print(_human_detect(environment))
            return 0

        plan = build_install_plan(
            requested_profile=getattr(args, "profile", "auto"),
            manifest_json=getattr(args, "manifest_json", ""),
            manifest_file=getattr(args, "manifest_file", ""),
        )
        if getattr(args, "json", False):
            print(json.dumps(plan, indent=2, sort_keys=True))
        else:
            print(_human_plan(plan))
        return 0
    except ValueError as exc:
        parser.exit(status=2, message=f"error: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
