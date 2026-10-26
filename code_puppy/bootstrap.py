"""Command-line entry point for the Code Puppy bootstrap planner.

The planner inspects the current environment and prints a minimal, supported
install plan without importing the Code Puppy runtime. It is intended for
constrained targets (notably Android/Termux) where a lean first install avoids
pulling optional integrations that may need to build from source.

Two invocations exist:

* From a source checkout, before Code Puppy is installed, without the Code
  Puppy runtime/provider stack::

      python -m code_puppy.bootstrap plan

* After installation, via the console script::

      code-puppy-bootstrap plan

Subcommands:
    detect  Print the detected environment (human-readable or ``--json``).
    plan    Print an install/reattach plan for a profile (default command).
"""

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
        prog="code-puppy-bootstrap",
        description="Code Puppy bootstrap planner for lean, environment-aware installs",
    )
    subparsers = parser.add_subparsers(dest="command")

    detect_parser = subparsers.add_parser(
        "detect",
        help="Inspect the current environment without importing the runtime",
    )
    detect_parser.add_argument("--json", action="store_true", help="Print JSON output")

    plan_parser = subparsers.add_parser(
        "plan",
        help="Build an install/reattach plan for a profile",
    )
    plan_parser.add_argument(
        "--profile",
        default="lean",
        choices=available_profiles(),
        help="Install profile: 'lean' (no extras, default) or 'full' "
        "(all applicable extras)",
    )
    plan_parser.add_argument("--json", action="store_true", help="Print JSON output")

    return parser


def _human_detect(environment: dict[str, Any]) -> str:
    lines = [
        "Code Puppy bootstrap environment",
        f"- python: {environment['python_executable']}",
        f"- version: {environment['python_version']}",
        (
            f"- platform: {environment['platform_system']} "
            f"{environment['platform_release']} ({environment['platform_machine']})"
        ),
        f"- termux: {'yes' if environment['is_termux'] else 'no'}",
        f"- android: {'yes' if environment['is_android'] else 'no'}",
        f"- uv: {'yes' if environment['has_uv'] else 'no'}",
        f"- rust: {'yes' if environment['has_rust'] else 'no'}",
        f"- clang: {'yes' if environment['has_clang'] else 'no'}",
        f"- ripgrep: {'yes' if environment['has_ripgrep'] else 'no'}",
        f"- git: {'yes' if environment['has_git'] else 'no'}",
    ]
    return "\n".join(lines)


def _human_plan(plan: dict[str, Any]) -> str:
    lines = [
        f"Profile: {plan['profile']}",
        f"Package spec: {plan['package_spec']}",
        f"Install: {plan['install_command']}",
        f"Reattach (all applicable extras): {plan['reattach_command']}",
        f"Run: {plan['run_command']}",
    ]
    if plan["extras"]:
        lines.append(f"Extras attached: {', '.join(plan['extras'])}")
    if plan["detached_extras"]:
        lines.append(
            f"Optional extras not attached: {', '.join(plan['detached_extras'])}"
        )
    if plan["suggested_system_packages"]:
        lines.append("Suggested system packages:")
        for item in plan["suggested_system_packages"]:
            lines.append(f"- {item['package']} ({item['kind']}): {item['reason']}")
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

        plan = build_install_plan(requested_profile=getattr(args, "profile", "lean"))
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
