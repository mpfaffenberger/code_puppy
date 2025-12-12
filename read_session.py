#!/usr/bin/env python3
"""Simple script to read and display code_puppy session .pkl files.

Usage:
    python read_session.py <path_to_session.pkl>

Example:
    python read_session.py ~/.code_puppy/contexts/my_session.pkl
"""

import json
import pickle
import sys
from pathlib import Path
from typing import Any, List

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text


def extract_text_from_parts(parts: List[Any]) -> str:
    """Extract text content from ModelRequest/ModelResponse parts."""
    texts = []
    for part in parts:
        # Handle TextPart objects
        if hasattr(part, 'content'):
            content = part.content
            # Decode escape sequences
            if isinstance(content, str):
                # Replace escaped newlines and tabs with actual characters
                content = content.replace('\\n', '\n').replace('\\t', '\t')
            texts.append(str(content))
        # Handle dict representations
        elif isinstance(part, dict) and 'content' in part:
            content = part['content']
            if isinstance(content, str):
                content = content.replace('\\n', '\n').replace('\\t', '\t')
            texts.append(str(content))
    return '\n'.join(texts)


def format_tool_args(args: Any) -> str:
    """Format tool arguments with proper newline/tab rendering."""
    if isinstance(args, str):
        try:
            # Try to parse as JSON first
            parsed = json.loads(args)
            # Pretty print with proper indentation
            formatted = json.dumps(parsed, indent=2)
            # Decode any escape sequences in string values
            return formatted
        except (json.JSONDecodeError, TypeError):
            # Not JSON, just decode escape sequences
            return args.replace('\\n', '\n').replace('\\t', '\t')
    elif isinstance(args, dict):
        return json.dumps(args, indent=2)
    return str(args)


def render_model_request_response(console: Console, obj: Any, title: str) -> None:
    """Render a ModelRequest or ModelResponse object."""
    # Check if it has parts attribute (pydantic_ai message objects)
    if hasattr(obj, 'parts'):
        content = extract_text_from_parts(obj.parts)
        if content:
            console.print(Panel(content, title=f"[dim]{title}[/dim]", border_style="dim"))
    elif isinstance(obj, dict) and 'parts' in obj:
        content = extract_text_from_parts(obj['parts'])
        if content:
            console.print(Panel(content, title=f"[dim]{title}[/dim]", border_style="dim"))
    else:
        # Fallback
        console.print(Panel(str(obj), title=f"[dim]{title}[/dim]", border_style="dim"))


def render_message(console: Console, msg: Any, index: int) -> None:
    """Render a single message in chat-like format."""
    # Handle pydantic_ai ModelRequest/ModelResponse objects
    if hasattr(msg, '__class__'):
        class_name = msg.__class__.__name__
        if class_name == 'ModelRequest':
            console.print("\n")
            console.print("[bold cyan]You:[/bold cyan]")
            content = extract_text_from_parts(msg.parts)
            console.print(content)
            console.print()
            return
        elif class_name == 'ModelResponse':
            console.print("\n")
            console.print("[bold green]🐶 Poco:[/bold green]")
            content = extract_text_from_parts(msg.parts)
            try:
                markdown = Markdown(content)
                console.print(markdown)
            except Exception:
                console.print(content)
            console.print()
            return
    
    # Handle dict-like messages (most common)
    if not isinstance(msg, dict):
        console.print(Panel(str(msg), title=f"Message #{index}"))
        return
    
    role = msg.get("role", "unknown")
    content = msg.get("content", "")
    
    # Render based on role
    if role == "user":
        # User messages - cyan with "You" label
        console.print("\n")
        console.print("[bold cyan]You:[/bold cyan]")
        console.print(content)
        console.print()
    
    elif role == "assistant":
        # Assistant messages - render as markdown like in actual session
        console.print("\n")
        console.print("[bold green]🐶 Poco:[/bold green]")
        if content:
            try:
                markdown = Markdown(content)
                console.print(markdown)
            except Exception:
                # Fallback to plain text
                console.print(content)
        console.print()
    
    elif role == "system":
        # System messages - dimmed
        console.print("\n")
        console.print(Panel(content, title="[dim]System[/dim]", border_style="dim"))
    
    elif role == "tool":
        # Tool results - blue with tool name
        tool_name = msg.get("name", "unknown_tool")
        console.print("\n")
        console.print(f"[bold blue]🔧 Tool Result: {tool_name}[/bold blue]")
        
        # Try to parse and pretty-print JSON content
        if content:
            try:
                parsed = json.loads(content)
                
                # Check if it's a serialized ModelRequest/ModelResponse in the result
                if isinstance(parsed, dict):
                    # Pretty print with proper formatting
                    formatted = json.dumps(parsed, indent=2)
                    # Decode escape sequences for display
                    display_text = formatted
                    
                    # If content contains escaped newlines, render them properly
                    if '\\n' in formatted or '\\t' in formatted:
                        # Extract and decode string content
                        for key in ['content', 'reasoning', 'next_steps', 'message', 'output']:
                            if key in parsed and isinstance(parsed[key], str):
                                decoded = parsed[key].replace('\\n', '\n').replace('\\t', '\t')
                                console.print(f"[dim]{key}:[/dim]")
                                console.print(Panel(decoded, border_style="blue"))
                                return
                    
                    syntax = Syntax(
                        display_text,
                        "json",
                        theme="monokai",
                        line_numbers=False
                    )
                    console.print(syntax)
                else:
                    console.print(Panel(str(parsed), border_style="blue"))
            except (json.JSONDecodeError, TypeError):
                # Not JSON, check for escape sequences and decode
                decoded_content = content.replace('\\n', '\n').replace('\\t', '\t')
                console.print(Panel(decoded_content, border_style="blue"))
        console.print()
    
    # Handle tool calls in assistant messages
    tool_calls = msg.get("tool_calls", [])
    if tool_calls and role == "assistant":
        console.print("[bold magenta]🛠️  Tool Calls:[/bold magenta]")
        for tc in tool_calls:
            if isinstance(tc, dict):
                func_name = tc.get("function", {}).get("name", "unknown")
                func_args = tc.get("function", {}).get("arguments", "")
                
                console.print(f"  [cyan]→[/cyan] [bold]{func_name}[/bold]")
                
                # Format and render arguments with proper newline/tab handling
                try:
                    args_obj = json.loads(func_args) if isinstance(func_args, str) else func_args
                    
                    # Check if args contain text with escaped newlines/tabs
                    if isinstance(args_obj, dict):
                        for key, value in args_obj.items():
                            if isinstance(value, str) and ('\\n' in value or '\\t' in value):
                                # Decode and display with proper formatting
                                decoded = value.replace('\\n', '\n').replace('\\t', '\t')
                                console.print(f"    [yellow]{key}:[/yellow]")
                                # Use a panel for multi-line content
                                console.print(Panel(decoded, border_style="magenta", padding=(0, 2)))
                            else:
                                # Regular value, show inline
                                console.print(f"    [yellow]{key}:[/yellow] {json.dumps(value)}")
                    else:
                        # Not a dict, just pretty-print
                        args_str = json.dumps(args_obj, indent=4)
                        syntax = Syntax(
                            args_str,
                            "json",
                            theme="monokai",
                            line_numbers=False,
                            indent_guides=True
                        )
                        console.print(syntax)
                except Exception:
                    # Fallback: decode escape sequences and display
                    decoded = func_args.replace('\\n', '\n').replace('\\t', '\t') if isinstance(func_args, str) else str(func_args)
                    console.print(Panel(decoded, border_style="magenta", padding=(0, 2)))
        console.print()


def read_session(pkl_path: Path) -> None:
    """Read and display a pickled session file."""
    console = Console()
    
    if not pkl_path.exists():
        console.print(f"[bold red]❌ Error: File not found: {pkl_path}[/bold red]")
        sys.exit(1)
    
    if not pkl_path.suffix == ".pkl":
        console.print(f"[yellow]⚠️  Warning: File doesn't have .pkl extension: {pkl_path}[/yellow]")
    
    try:
        with pkl_path.open("rb") as f:
            history: List[Any] = pickle.load(f)
    except Exception as e:
        console.print(f"[bold red]❌ Error reading pickle file: {e}[/bold red]")
        sys.exit(1)
    
    # Header with session info
    console.print("\n")
    console.rule("[bold magenta]📦 Code Puppy Session Replay[/bold magenta]")
    console.print(f"[dim]File:[/dim] {pkl_path}")
    console.print(f"[dim]Total Messages:[/dim] {len(history)}")
    
    # Check for companion metadata file
    meta_path = pkl_path.parent / f"{pkl_path.stem}_meta.json"
    if meta_path.exists():
        try:
            with meta_path.open("r") as mf:
                meta = json.load(mf)
                console.print(f"[dim]Session Name:[/dim] {meta.get('session_name', 'unknown')}")
                console.print(f"[dim]Timestamp:[/dim] {meta.get('timestamp', 'unknown')}")
                console.print(f"[dim]Total Tokens:[/dim] {meta.get('total_tokens', 'unknown')}")
        except Exception:
            pass
    
    console.rule()
    
    # Display each message in chat format
    for idx, msg in enumerate(history, start=1):
        render_message(console, msg, idx)
    
    # Footer
    console.rule()
    console.print(f"\n[bold green]✅ Finished replaying {len(history)} messages[/bold green]\n")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python read_session.py <path_to_session.pkl>")
        print("\nExample:")
        print("  python read_session.py ~/.code_puppy/contexts/my_session.pkl")
        print("\nDefault context location: ~/.code_puppy/contexts/")
        sys.exit(1)
    
    pkl_path = Path(sys.argv[1]).expanduser().resolve()
    read_session(pkl_path)
