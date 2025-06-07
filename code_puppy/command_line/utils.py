import os
from typing import List, Tuple

from rich.table import Table


def list_directory(path: str = None) -> Tuple[List[str], List[str]]:
    """
    Returns (dirs, files) for the specified path, splitting out directories and files.
    """
    if path is None:
        path = os.getcwd()
    entries = []
    try:
        entries = [e for e in os.listdir(path)]
    except Exception as e:
        raise RuntimeError(f"Error listing directory: {e}")
    dirs = [e for e in entries if os.path.isdir(os.path.join(path, e))]
    files = [e for e in entries if not os.path.isdir(os.path.join(path, e))]
    return dirs, files


def make_directory_table(path: str = None) -> Table:
    """
    Returns a rich.Table object containing the directory listing.
    """
    if path is None:
        path = os.getcwd()
    dirs, files = list_directory(path)
    table = Table(
        title=f"\U0001f4c1 [bold blue]Current directory:[/bold blue] [cyan]{path}[/cyan]"
    )
    table.add_column("Type", style="dim", width=8)
    table.add_column("Name", style="bold")
    for d in sorted(dirs):
        table.add_row("[green]dir[/green]", f"[cyan]{d}[/cyan]")
    for f in sorted(files):
        table.add_row("[yellow]file[/yellow]", f"{f}")
    return table
