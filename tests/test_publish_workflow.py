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
import sys
import textwrap
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/publish.yml"
GUARD = ROOT / "scripts" / "check_release_version.py"


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
    """Run under bash with a stub that logs its arguments and prints ``output``."""
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


def release(tmp_path: Path, pyproject: str, lock: str | None = None) -> str:
    """Run the bump and capture steps with real uv on a copy of a project.

    Returns the version the workflow would publish. With ``lock``, uv uses it
    as is (``UV_FROZEN``) rather than resolving the project's dependencies;
    without, the project must have none, so uv locks it offline.
    """
    project = tmp_path / "project"
    (project / "scripts").mkdir(parents=True)
    (project / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    if lock is not None:
        (project / "uv.lock").write_text(lock, encoding="utf-8")
    shutil.copy(GUARD, project / "scripts")
    outputs = tmp_path / "github_output"
    script = tmp_path / "steps.sh"
    script.write_text(
        step_script("Bump version") + step_script("Capture new version"),
        encoding="utf-8",
    )
    env = {
        **{k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
        "GITHUB_OUTPUT": str(outputs),
        "UV_FROZEN" if lock is not None else "UV_NO_SYNC": "1",
    }
    run = subprocess.run(
        ["bash", "-e", str(script)],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert run.returncode == 0, run.stderr
    captured = dict(
        line.split("=", 1) for line in outputs.read_text(encoding="utf-8").splitlines()
    )["version"]
    written = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))
    assert written["project"]["version"] == captured
    return captured


with_uv = pytest.mark.skipif(shutil.which("uv") is None, reason="the job runs uv")


@bash_only
@with_uv
@pytest.mark.parametrize(
    ("current", "published"),
    [
        # The cutover: exactly 1.0.0, never a stray 1.0.1.
        ("1.0.0rc1", "1.0.0"),
        ("1.1.0b2", "1.1.0"),
        ("1.0.1.dev3", "1.0.1"),
        ("1.0.0", "1.0.1"),
        ("1.2.9", "1.2.10"),
    ],
)
def test_a_pre_release_is_finalised_and_a_stable_one_patched(
    tmp_path: Path, current: str, published: str
) -> None:
    pyproject = f'[project]\nname = "x"\nversion = "{current}"\n'
    assert release(tmp_path, pyproject) == published


@bash_only
@with_uv
def test_the_checked_in_project_publishes_a_version_the_guard_accepts(
    tmp_path: Path,
) -> None:
    """At the cutover this is 1.0.0; after it, the next patch."""
    version = release(
        tmp_path,
        (ROOT / "pyproject.toml").read_text(encoding="utf-8"),
        (ROOT / "uv.lock").read_text(encoding="utf-8"),
    )
    guard = subprocess.run(
        [sys.executable, str(GUARD), "main", version],
        capture_output=True,
        text=True,
        check=False,
    )
    assert guard.returncode == 0, guard.stdout


@bash_only
def test_writeback_rebases_and_pushes_main(tmp_path: Path) -> None:
    script = step_script("Push version bump and tag to GitHub", "1.0.0")
    run, calls = run_step(tmp_path, script, "git")

    assert run.returncode == 0, run.stderr
    assert "pull --rebase origin main" in calls
    assert "push origin main" in calls
    assert "push origin v1.0.0" in calls
