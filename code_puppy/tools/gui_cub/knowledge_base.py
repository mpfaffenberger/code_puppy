"""GUI-Cub Knowledge Base Tool - Persistent learning across sessions."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic_ai import RunContext

if TYPE_CHECKING:
    from pydantic_ai import Agent
from rich.console import Console

console = Console()


def get_gui_cub_base_dir() -> Path:
    """Get the base directory for GUI-Cub data storage."""
    base_dir = Path.home() / ".code_puppy" / "gui_cub"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def append_to_knowledge_base(
    context: str,
    discovery: str,
    what_worked: str | None = None,
    what_failed: str | None = None,
    reusable: str | None = None,
    tags: str | None = None,
) -> tuple[bool, str]:
    """Append a diary-style entry to the knowledge base.

    The KB is a living document - accumulates reusable learnings across sessions.
    When it reaches 1000 lines, oldest entries are pruned (FIFO).

    Args:
        context: What was the agent doing? (e.g., "Automating Calculator app")
        discovery: What did the agent learn that's reusable?
        what_worked: Successful approaches (optional)
        what_failed: Failed approaches to avoid (optional)
        reusable: Links to workflows/files created (optional)
        tags: Searchable keywords like "#calculator #timing" (optional)

    Returns:
        Tuple of (success: bool, message: str)

    Example:
        append_to_knowledge_base(
            context="Calculator app automation",
            discovery="Requires 0.3s delay between button clicks",
            what_worked="Accessibility API with AXButton elements",
            what_failed="OCR unreliable for small number buttons",
            reusable="workflows/calculator_operations.yaml",
            tags="#calculator #accessibility #timing"
        )
    """
    try:
        base_dir = get_gui_cub_base_dir()
        kb_path = base_dir / "gui_cub_knowledge_base.md"

        # Build diary entry
        date_str = datetime.now().strftime("%Y-%m-%d")
        entry_lines = []
        entry_lines.append(f"## {date_str} | {context}")
        entry_lines.append(f"**Discovery:** {discovery}")

        if what_worked:
            entry_lines.append(f"**What worked:** {what_worked}")

        if what_failed:
            entry_lines.append(f"**What failed:** {what_failed}")

        if reusable:
            entry_lines.append(f"**Reusable:** {reusable}")

        if tags:
            entry_lines.append(f"**Tags:** {tags}")

        entry_lines.append("---")
        entry = "\n".join(entry_lines) + "\n"

        # Initialize KB if it doesn't exist
        if not kb_path.exists():
            header = "# GUI-Cub Knowledge Base\n"
            header += "Accumulated learnings across sessions - searchable, reusable wisdom\n\n"
            header += "---\n\n"
            kb_path.write_text(header, encoding="utf-8")

        # Read current KB
        current_content = kb_path.read_text(encoding="utf-8")
        lines = current_content.split("\n")

        # Append new entry
        updated_content = current_content + entry

        # FIFO pruning: if > 1000 lines, remove oldest diary entry
        if len(updated_content.split("\n")) > 1000:
            # Find first diary entry (## YYYY-MM-DD)
            first_entry_idx = None
            second_entry_idx = None

            for i, line in enumerate(lines):
                if line.startswith("## 20"):  # Diary entries start with ## 20XX-XX-XX
                    if first_entry_idx is None:
                        first_entry_idx = i
                    elif second_entry_idx is None:
                        second_entry_idx = i
                        break

            # Remove first entry (between first_entry_idx and second_entry_idx)
            if first_entry_idx is not None and second_entry_idx is not None:
                # Keep header + everything after first entry
                pruned_lines = lines[:first_entry_idx] + lines[second_entry_idx:]
                updated_content = "\n".join(pruned_lines) + "\n" + entry
                console.print(
                    "[dim]📝 Knowledge base pruned (FIFO): removed oldest entry[/dim]"
                )
            elif first_entry_idx is not None:
                # Only one entry exists, keep it and add new one
                pass

        # Write updated KB
        kb_path.write_text(updated_content, encoding="utf-8")

        console.print(
            f"[green]✅ Knowledge base updated:[/green] {context}\n"
            f"[dim]   Discovery: {discovery[:60]}{'...' if len(discovery) > 60 else ''}[/dim]"
        )

        return True, f"Knowledge base entry added: {context}"

    except Exception as e:
        console.print(f"[red]❌ Failed to update knowledge base: {e}[/red]")
        return False, f"Error: {e}"


def register_knowledge_base_tool(agent: "Agent[Any, Any]") -> "Agent[Any, Any]":
    """Register the knowledge base tool."""

    @agent.tool
    async def gui_cub_append_to_knowledge_base(
        context: RunContext,
        context_description: str,
        discovery: str,
        what_worked: str | None = None,
        what_failed: str | None = None,
        reusable: str | None = None,
        tags: str | None = None,
    ) -> dict:
        """Append a reusable learning to the persistent knowledge base.

        Use this to record discoveries that will be useful in future sessions.
        The KB accumulates across all GUI-Cub sessions and is automatically
        pruned to keep the most recent learnings.

        Args:
            context_description: What were you doing? (e.g., "Automating Settings workflow")
            discovery: What reusable insight did you learn?
            what_worked: Successful approaches (optional)
            what_failed: Failed approaches to avoid (optional)
            reusable: Links to workflows/scripts created (optional)
            tags: Searchable tags like "#calculator #automation #timing" (optional)

        Returns:
            Dict with success status and message

        Example:
            gui_cub_append_to_knowledge_base(
                context_description="Calculator automation",
                discovery="Number buttons require 0.5s delay after focus",
                what_worked="Focus → Sleep 0.5s → Type works reliably",
                what_failed="Immediate typing after focus drops first 2 chars",
                tags="#calculator #automation #timing #focus"
            )
        """
        success, message = append_to_knowledge_base(
            context=context_description,
            discovery=discovery,
            what_worked=what_worked,
            what_failed=what_failed,
            reusable=reusable,
            tags=tags,
        )

        return {
            "success": success,
            "message": message,
            "kb_path": str(get_gui_cub_base_dir() / "gui_cub_knowledge_base.md"),
        }

    return agent
