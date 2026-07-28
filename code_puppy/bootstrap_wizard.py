"""Interactive, environment-aware install wizard for Code Puppy.

The bootstrap *planner* (``code_puppy.bootstrap_profiles``) decides *what*
should be installed. This module is the *wizard*: it walks an operator --
especially an Android/Termux newcomer -- through *doing* it, one confirmed
step at a time, then verifies and reconciles the result.

Design rules honored here:
- stdlib-only (``subprocess``/``shutil``) so it runs before any heavy deps
- destructive/state-altering steps are gated behind explicit confirmation
- ``--dry-run`` never executes; ``--yes`` auto-confirms for automation
- the wizard always ends with a verification + reconciliation summary
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, Callable

from code_puppy.bootstrap_profiles import build_install_plan, detect_environment


@dataclass
class WizardStep:
    """A single confirmable unit of install work."""

    key: str
    title: str
    command: str
    explanation: str
    # Returns True when the step's goal is *already* satisfied (skip it).
    is_satisfied: Callable[[], bool] = field(default=lambda: False)
    required: bool = True


@dataclass
class StepOutcome:
    key: str
    status: str  # satisfied | done | skipped | failed | dry-run
    detail: str = ""


def _has(binary: str) -> bool:
    return shutil.which(binary) is not None


def build_steps(profile: str | None = None) -> tuple[list[WizardStep], dict[str, Any]]:
    """Derive the ordered wizard steps from the canonical install plan.

    Reusing :func:`build_install_plan` keeps a single source of truth for
    *what* to install -- the wizard only decides *how* to walk it.
    """

    plan = build_install_plan(requested_profile=profile)
    env = plan["environment"]
    steps: list[WizardStep] = []

    # 1. Package manager (uv) -- the engine everything else rides on.
    if not env.get("has_uv"):
        if env.get("is_termux") or env.get("is_android"):
            uv_cmd = "pkg install -y uv"
        else:
            uv_cmd = "curl -LsSf https://astral.sh/uv/install.sh | sh"
        steps.append(
            WizardStep(
                key="uv",
                title="Install the uv package manager",
                command=uv_cmd,
                explanation=(
                    "uv installs and runs Code Puppy in an isolated tool env; "
                    "Termux should use its packaged uv instead of building uv from PyPI."
                ),
                is_satisfied=lambda: _has("uv"),
            )
        )

    # 2. System packages: Android build toolchain + native helper binaries.
    missing = plan.get("missing_system_packages") or []
    if missing:
        steps.append(
            WizardStep(
                key="system_packages",
                title=f"Install Termux system packages: {', '.join(missing)}",
                command=f"pkg install -y {' '.join(missing)}",
                explanation=(
                    "Termux needs rust/clang to build unavoidable native Python "
                    "deps (pydantic-core), plus helper binaries like ripgrep/proot."
                ),
                is_satisfied=lambda missing=missing: all(
                    _has({"ripgrep": "rg", "rust": "rustc"}.get(m, m)) for m in missing
                ),
            )
        )

    # 3. Code Puppy itself.
    steps.append(
        WizardStep(
            key="code_puppy",
            title=f"Install Code Puppy ({plan['package_spec']})",
            command=plan["install_command"],
            explanation=plan["description"],
            is_satisfied=lambda: False,  # always (re)attach; --refresh is idempotent
        )
    )

    return steps, plan


def _confirm(prompt: str, *, assume_yes: bool) -> bool:
    if assume_yes:
        print(f"{prompt} [auto-yes]")
        return True
    if not sys.stdin.isatty():
        # Non-interactive without --yes: refuse to act, don't hang.
        print(f"{prompt} [no TTY -- skipping; pass --yes to auto-run]")
        return False
    try:
        answer = input(f"{prompt} [Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in ("", "y", "yes")


def _run_command(command: str) -> tuple[int, str]:
    """Run a shell command, streaming nothing, capturing combined output."""

    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=1800,
        )
    except subprocess.TimeoutExpired:
        return 124, "timed out after 1800s"
    except Exception as exc:  # never crash the wizard
        return 1, f"failed to launch: {exc}"
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, output.strip()


def _verify(plan: dict[str, Any]) -> StepOutcome:
    """Confirm Code Puppy actually landed and can answer for itself."""

    if not _has("code-puppy"):
        return StepOutcome(
            "verify",
            "failed",
            "`code-puppy` not found on PATH after install.",
        )
    code, out = _run_command("code-puppy --help")
    if code != 0:
        tail = out.splitlines()[-3:] if out else []
        return StepOutcome("verify", "failed", "; ".join(tail) or f"exit {code}")
    return StepOutcome("verify", "done", "`code-puppy --help` runs cleanly.")


def run_wizard(
    *,
    profile: str | None = None,
    assume_yes: bool = False,
    dry_run: bool = False,
) -> int:
    """Execute the interactive install wizard. Returns a process exit code."""

    steps, plan = build_steps(profile)
    env = plan["environment"]

    print("Code Puppy install wizard")
    print(f"  profile : {plan['profile']}")
    print(
        "  device  : "
        f"{env['platform_system']} {env['platform_release']} ({env['platform_machine']})"
    )
    print(f"  python  : {env['python_version']}")
    print(f"  steps   : {len(steps)}")
    if dry_run:
        print("  mode    : DRY-RUN (nothing will be executed)")
    print()

    outcomes: list[StepOutcome] = []

    for index, step in enumerate(steps, start=1):
        print(f"[{index}/{len(steps)}] {step.title}")
        print(f"      why: {step.explanation}")
        print(f"      run: {step.command}")

        if step.is_satisfied():
            print("      -> already satisfied, skipping.\n")
            outcomes.append(StepOutcome(step.key, "satisfied"))
            continue

        if dry_run:
            print("      -> dry-run, not executed.\n")
            outcomes.append(StepOutcome(step.key, "dry-run"))
            continue

        if not _confirm("      proceed?", assume_yes=assume_yes):
            status = "skipped"
            print(f"      -> {status}.\n")
            outcomes.append(StepOutcome(step.key, status))
            if step.required:
                print(
                    "      (this step is required -- later steps may fail without it)\n"
                )
            continue

        code, out = _run_command(step.command)
        if code == 0:
            print("      -> done.\n")
            outcomes.append(StepOutcome(step.key, "done"))
        else:
            tail = "\n        ".join(out.splitlines()[-5:]) if out else f"exit {code}"
            print(f"      -> FAILED (exit {code}):\n        {tail}\n")
            outcomes.append(StepOutcome(step.key, "failed", f"exit {code}"))
            if step.required:
                print("Required step failed -- stopping. Fix the above and re-run.\n")
                _print_summary(outcomes, verify=None)
                return 1

    verify = None
    if not dry_run:
        verify = _verify(plan)
        symbol = "OK" if verify.status == "done" else "FAILED"
        print(f"Verification: {symbol} -- {verify.detail}\n")

    _print_summary(outcomes, verify=verify)

    failed = any(o.status == "failed" for o in outcomes)
    if verify is not None and verify.status == "failed":
        failed = True
    return 1 if failed else 0


def _print_summary(outcomes: list[StepOutcome], *, verify: StepOutcome | None) -> None:
    print("Summary (state reconciliation):")
    for outcome in outcomes:
        line = f"  - {outcome.key}: {outcome.status}"
        if outcome.detail:
            line += f" ({outcome.detail})"
        print(line)
    if verify is not None:
        line = f"  - verify: {verify.status}"
        if verify.detail:
            line += f" ({verify.detail})"
        print(line)
    if verify is not None and verify.status == "done":
        print("\nAll set -- run it with:  code-puppy -i")


def detect_summary() -> dict[str, Any]:
    """Thin re-export so callers can pre-flight without importing profiles."""

    return detect_environment()
