def _print_edit_file_result(result, file_path=None, content=None):
    """
    Helper: Always prints error/diff/messages from edit_file (file_modifications.py).
    """
    from code_puppy.tools.common import console

    if result.get("error"):
        console.print(f"[bold red]Error:[/bold red] {result['error']}")
        if "reason" in result:
            console.print(f"[dim]Reason:[/dim] {result['reason']}")
        if "received" in result:
            console.print(f"[dim]Received:[/dim] {result['received']}")
        return
    if (
        (content is not None)
        and (file_path is not None)
        and result.get("success")
        and result.get("changed")
    ):
        try:
            import difflib
            import os

            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as f:
                    current_content = f.read()
                diff_lines = list(
                    difflib.unified_diff(
                        current_content.splitlines(keepends=True),
                        content.splitlines(keepends=True),
                        fromfile=f"a/{os.path.basename(file_path)}",
                        tofile=f"b/{os.path.basename(file_path)}",
                        n=3,
                    )
                )
                diff_text = "".join(diff_lines)
                if diff_text.strip():
                    console.print("[bold cyan]Changes applied:[/bold cyan]")
                    formatted_diff = ""
                    for line in diff_lines:
                        if line.startswith("+") and not line.startswith("+++"):
                            formatted_diff += f"[bold green]{line}[/bold green]"
                        elif line.startswith("-") and not line.startswith("---"):
                            formatted_diff += f"[bold red]{line}[/bold red]"
                        elif line.startswith("@"):
                            formatted_diff += f"[bold cyan]{line}[/bold cyan]"
                        else:
                            formatted_diff += line
                    console.print(formatted_diff)
                else:
                    console.print("[dim]No visible changes[/dim]")
        except Exception as e:
            console.print(f"[bold yellow]Warning printing diff:[/bold yellow] {e}")
    if "diff" in result and result.get("diff"):
        console.print("[bold cyan]Diff:[/bold cyan]")
        console.print(result["diff"])
    if "message" in result:
        console.print(f"[bold magenta]{result['message']}[/bold magenta]")
