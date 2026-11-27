"""Contracts in the publish workflow that Python tests would otherwise miss.

The release guard is tested as Python, but the YAML decides which branch ever
runs it and where its version bump lands. These tests read that YAML directly;
the writeback test also executes its shell with a recording `git` stub.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

WORKFLOW = Path(__file__).resolve().parent.parent / ".github/workflows/publish.yml"


def workflow_lines() -> list[str]:
    return WORKFLOW.read_text(encoding="utf-8").splitlines()


def test_only_main_triggers_the_workflow() -> None:
    lines = workflow_lines()
    start = lines.index("on:")
    push = lines.index("  push:", start, start + 3)
    branches = lines.index("    branches:", push, push + 3)
    names = [
        match.group(1)
        for line in lines[branches + 1 :]
        if (match := re.match(r"      - (\S+)$", line))
    ]

    assert names == ["main"]


def step_script(name: str, version: str = "1.0.1") -> str:
    """The named step's shell, with GitHub's version expression substituted."""
    lines = workflow_lines()
    start = next(i for i, line in enumerate(lines) if line.strip() == f"- name: {name}")
    run = next(i for i in range(start, len(lines)) if lines[i] == "        run: |")
    body = []
    for line in lines[run + 1 :]:
        if line and not line.startswith("          "):
            break
        body.append(line[10:] if line else "")
    return (
        "\n".join(body).replace("${{ steps.version.outputs.version }}", version) + "\n"
    )


def run_step(
    tmp_path: Path, script: str, stub: str, output: str = ""
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """Run ``script`` under bash with ``stub`` replaced by a command that logs its arguments.

    The stub prints ``output`` and succeeds.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / f"{stub}.log"
    fake = bin_dir / stub
    fake.write_text(
        textwrap.dedent(
            f"""\
            #!/bin/sh
            printf '%s\\n' "$*" >> "{log}"
            printf '%s' '{output}'
            exit 0
            """
        ),
        encoding="utf-8",
    )
    fake.chmod(0o755)
    path = tmp_path / "step.sh"
    path.write_text(script, encoding="utf-8")
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "GITHUB_REF_NAME": "main",
    }
    run = subprocess.run(
        ["bash", str(path)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return run, log.read_text(encoding="utf-8").splitlines()


bash_only = pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None,
    reason="release jobs run bash on Linux",
)


@bash_only
@pytest.mark.parametrize(
    ("current", "bump"),
    [
        # The cutover: exactly 1.0.0, never a stray 1.0.1.
        ("1.0.0rc1", "stable"),
        ("1.1.0b2", "stable"),
        ("1.0.1.dev3", "stable"),
        ("1.0.0", "patch"),
        ("1.2.9", "patch"),
    ],
)
def test_bump_finalises_a_pre_release_and_patches_a_stable_one(
    tmp_path: Path, current: str, bump: str
) -> None:
    run, calls = run_step(tmp_path, step_script("Bump version"), "uv", current)

    assert run.returncode == 0, run.stderr
    assert calls == ["version --short", f"version --bump {bump}"]


@bash_only
def test_writeback_rebases_and_pushes_main(tmp_path: Path) -> None:
    script = step_script("Push version bump and tag to GitHub", "1.0.0")
    run, calls = run_step(tmp_path, script, "git")

    assert run.returncode == 0, run.stderr
    assert "pull --rebase origin main" in calls
    assert "push origin main" in calls
    assert "push origin v1.0.0" in calls
