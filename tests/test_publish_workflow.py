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


def test_pushes_to_both_release_branches_trigger_the_workflow() -> None:
    lines = workflow_lines()
    start = lines.index("on:")
    push = lines.index("  push:", start, start + 3)
    branches = lines.index("    branches:", push, push + 3)
    names = [
        match.group(1)
        for line in lines[branches + 1 :]
        if (match := re.match(r"      - (\S+)$", line))
    ]

    assert names == ["main", "v1"]


def writeback_script(version: str = "1.0.0rc2") -> str:
    """The named step's shell, with GitHub's version expression substituted."""
    lines = workflow_lines()
    start = next(
        i
        for i, line in enumerate(lines)
        if line.strip() == "- name: Push version bump and tag to GitHub"
    )
    run = next(i for i in range(start, len(lines)) if lines[i] == "        run: |")
    body = []
    for line in lines[run + 1 :]:
        if line and not line.startswith("          "):
            break
        body.append(line[10:] if line else "")
    return (
        "\n".join(body).replace("${{ steps.version.outputs.version }}", version) + "\n"
    )


@pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None,
    reason="release jobs run bash on Linux",
)
def test_writeback_rebases_and_pushes_the_triggering_branch(tmp_path: Path) -> None:
    """A v1 publish must not rebase onto or push main after uploading the RC."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "git.log"
    git = bin_dir / "git"
    git.write_text(
        textwrap.dedent(
            """\
            #!/bin/sh
            printf '%s\\n' "$*" >> "$GIT_LOG"
            exit 0
            """
        ),
        encoding="utf-8",
    )
    git.chmod(0o755)
    script = tmp_path / "writeback.sh"
    script.write_text(writeback_script(), encoding="utf-8")
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "GIT_LOG": str(log),
        "GITHUB_REF_NAME": "v1",
    }

    run = subprocess.run(
        ["bash", str(script)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert run.returncode == 0, run.stderr
    calls = log.read_text(encoding="utf-8").splitlines()
    assert "pull --rebase origin v1" in calls
    assert "push origin v1" in calls
    assert "push origin v1.0.0rc2" in calls
    assert not any("main" in call for call in calls), calls
