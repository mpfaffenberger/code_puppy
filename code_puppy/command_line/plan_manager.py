"""Plan management for the /plan command.

Handles reading, writing, parsing, and executing steps from .claude/plan.md.
"""

import os
import subprocess
from pathlib import Path
from typing import Optional


class PlanManager:
    """Manage a persisted plan in .claude/plan.md."""

    PLAN_DIR = ".claude"
    PLAN_FILE = "plan.md"

    def __init__(self, cwd: Optional[str] = None) -> None:
        self._cwd = cwd or os.getcwd()

    @property
    def plan_path(self) -> Path:
        return Path(self._cwd) / self.PLAN_DIR / self.PLAN_FILE

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------

    def exists(self) -> bool:
        return self.plan_path.exists()

    def load(self) -> Optional[str]:
        if not self.exists():
            return None
        return self.plan_path.read_text(encoding="utf-8")

    def save(self, content: str) -> Path:
        self.plan_path.parent.mkdir(parents=True, exist_ok=True)
        self.plan_path.write_text(content, encoding="utf-8")
        return self.plan_path

    def create_template(self, title: str = "Plan") -> str:
        """Return a bare-bones template the user can fill in."""
        return f"""# Plan: {title}

## Summary
<!-- Brief overview of what this plan accomplishes -->

## Steps
- [ ] Step 1
- [ ] Step 2
- [ ] Step 3

## Risks / Unknowns
-

## Validation
- [ ] Final validation step
"""

    # ------------------------------------------------------------------
    # Step parsing
    # ------------------------------------------------------------------

    def get_steps(self) -> list[dict]:
        """Parse checklist items from the plan.

        Returns a list of dicts with keys:
            index — 1-based step number
            text  — the checkbox label
            done  — bool
            line  — 0-based line number in the original file
        """
        content = self.load()
        if not content:
            return []

        steps: list[dict] = []
        for i, line in enumerate(content.split("\n")):
            stripped = line.strip()
            if stripped.startswith("- [ ]"):
                steps.append(
                    {
                        "index": len(steps) + 1,
                        "text": stripped[5:].strip(),
                        "done": False,
                        "line": i,
                    }
                )
            elif stripped.startswith("- [x]") or stripped.startswith("- [X]"):
                steps.append(
                    {
                        "index": len(steps) + 1,
                        "text": stripped[5:].strip(),
                        "done": True,
                        "line": i,
                    }
                )

        return steps

    def mark_step_done(self, step_num: int, done: bool = True) -> bool:
        """Mark one step as done (or undone) by 1-based index.

        Returns False if the step number doesn't exist.
        """
        content = self.load()
        if not content:
            return False

        target = None
        for s in self.get_steps():
            if s["index"] == step_num:
                target = s
                break

        if not target:
            return False

        lines = content.split("\n")
        line = lines[target["line"]]
        if done:
            line = line.replace("- [ ]", "- [x]", 1)
        else:
            line = line.replace("- [x]", "- [ ]", 1)
            line = line.replace("- [X]", "- [ ]", 1)
        lines[target["line"]] = line

        self.save("\n".join(lines))
        return True

    # ------------------------------------------------------------------
    # Editor
    # ------------------------------------------------------------------

    def edit_in_editor(self) -> bool:
        """Open the plan file in the user's $EDITOR / $VISUAL.

        Creates a template if the file doesn't exist yet.
        Returns True if the editor exited successfully (user saved).
        """
        path = self.plan_path
        path.parent.mkdir(parents=True, exist_ok=True)

        if not path.exists():
            path.write_text(self.create_template(), encoding="utf-8")

        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "nano"
        try:
            result = subprocess.run([editor, str(path)])
            return result.returncode == 0
        except FileNotFoundError:
            raise RuntimeError(f"Editor '{editor}' not found.  Set $EDITOR or $VISUAL.")

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def show_formatted(self) -> str:
        """Return a human-readable representation of the plan."""
        content = self.load()
        if not content:
            return "No plan file found at .claude/plan.md.\nCreate one with /plan <goal> and then /plan edit, or /plan edit to start a template."

        steps = self.get_steps()
        done_count = sum(1 for s in steps if s["done"])
        total = len(steps)

        header = f"📋  Plan  ({done_count}/{total} steps complete)\n{'─' * 42}\n\n"
        return header + content

    # ------------------------------------------------------------------
    # Execution prompt builders
    # ------------------------------------------------------------------

    def build_run_prompt(self, step_num: Optional[int] = None) -> str:
        """Build a prompt to send to the LLM for executing step(s).

        * step_num=None  — execute all pending (not-done) steps
        * step_num=N     — execute that specific step only
        """
        content = self.load()
        if not content:
            raise ValueError(
                "No plan found at .claude/plan.md.  "
                "Create one with /plan <goal> and then /plan edit."
            )

        steps = self.get_steps()

        if step_num is not None:
            target = None
            for s in steps:
                if s["index"] == step_num:
                    target = s
                    break
            if not target:
                raise ValueError(f"Step {step_num} not found in the plan.")
            if target["done"]:
                raise ValueError(f"Step {step_num} is already marked as done.")

            return (
                f"You are now executing step {step_num} from the plan below.\n"
                f"\n"
                f"## Full plan (for context)\n"
                f"{content}\n"
                f"\n"
                f"## Step {step_num} to execute\n"
                f"{target['text']}\n"
                f"\n"
                f"Implement this step.  Modify files, run commands — do whatever is\n"
                f"needed.  When done, report what was accomplished and output:\n"
                f"    PLAN_STEP_DONE: {step_num}\n"
            )

        # Execute all pending steps in order.
        pending = [s for s in steps if not s["done"]]
        if not pending:
            raise ValueError("All steps are already completed.  No pending steps.")

        pending_text = "\n".join(f"- [ ] {s['text']}" for s in pending)
        step_list = ", ".join(str(s["index"]) for s in pending)

        return (
            f"You are now executing the plan below.  Complete ALL pending steps.\n"
            f"\n"
            f"## Full plan (for context)\n"
            f"{content}\n"
            f"\n"
            f"## Pending steps to execute\n"
            f"{pending_text}\n"
            f"\n"
            f"Execute each step in order.  When you finish a step, output:\n"
            f"    PLAN_STEP_DONE: <step-number>\n"
            f"\n"
            f"Continue until all steps (steps {step_list}) are done, then sum up what was accomplished.\n"
        )
