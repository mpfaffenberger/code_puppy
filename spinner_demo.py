#!/usr/bin/env python3
"""
Rich Spinner Demo Script

This script demonstrates all available spinner styles in Rich with colors
that match the Textual dark theme. Press 'y' to see the next spinner
or 'n' to exit.

Usage:
    python spinner_demo.py [start_index]
    
    start_index: Optional index to start from (1-based, e.g. 42 to start from the 42nd spinner)
"""

import time
import sys
import argparse
from rich.console import Console
from rich.theme import Theme
from rich.spinner import Spinner

# Create a theme that matches Textual dark theme colors
textual_theme = Theme({
    "spinner.text": "#aaaaaa",     # Light gray for text
    "spinner.label": "#ffffff",    # White for label
    "prompt": "#ffcc00",           # Yellow for prompt
    "key": "#00ff00",              # Green for key options
})

console = Console(theme=textual_theme)

# Get list of spinner styles available in Rich
try:
    # In Rich 14.0+, we can get the available spinners directly from Rich
    from rich.spinner import SPINNERS
    SPINNER_STYLES = list(SPINNERS.keys())
except (ImportError, AttributeError):
    # Fallback to a known subset that works with most Rich versions
    SPINNER_STYLES = [
        "dots", "dots2", "dots3", "dots4", "dots5", "dots6", "dots7", "dots8", "dots9",
        "dots10", "dots11", "dots12", "line", "line2", "pipe", "simpleDots", "simpleDotsScrolling",
        "star", "star2", "flip", "hamburger", "growVertical", "growHorizontal",
        "balloon", "balloon2", "noise", "bounce", "boxBounce", "boxBounce2",
        "triangle", "arc", "circle", "squareCorners", "circleQuarters", "circleHalves",
        "squish", "toggle", "toggle2", "toggle3", "toggle4", "toggle5", "toggle6",
        "toggle7", "toggle8", "toggle9", "toggle10", "toggle11", "toggle12", "toggle13"
    ]

# Filtered list of spinner styles to showcase
SPINNER_FILTERED = [
    "dots10",
    "line",
    "simpleDots",
    "simpleDotsScrolling",
    "star",
    "circleQuarters",
    "arrow2",
    "arrow3",
    "bouncingBar",
    "bouncingBall",
    "smiley",
    "clock",
    "earth",
    "weather",
    "point",
    "aesthetic"
]

def demonstrate_spinner(spinner_style):
    """Demonstrate a single spinner style with pause and user prompt."""
    console.print(f"\n[bold]Style:[/bold] [spinner.label]{spinner_style}[/spinner.label]")
    
    # Create and display larger spinner with slower animation (0.5 = half speed)
    status_text = f"[bold][spinner.text]Processing your request...[/spinner.text][/bold]"
    
    # Clear space to make spinner more visible
    for _ in range(2):
        console.print()
        
    # Show spinner with slower animation
    with console.status(status_text, spinner=spinner_style, speed=0.5) as status:
        # Create large visual display area for the spinner
        for _ in range(6):
            # Slow down the animation with longer pauses
            time.sleep(0.8)
    
    # Add space after spinner
    console.print()
    
    # Prompt for next spinner with larger text
    console.print("[bold][prompt]▶ Next spinner? ([key]Y[/key]/[key]N[/key]):[/prompt][/bold] ", end="")
    response = input().lower()
    return response != 'n'

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Rich Spinner Demo - Show all available spinner styles"
    )
    parser.add_argument(
        "start_index", 
        nargs="?", 
        type=int, 
        default=1,
        help="Index of the spinner to start from (1-based)"
    )
    parser.add_argument(
        "--list", 
        action="store_true",
        help="List all available spinner styles and exit"
    )
    return parser.parse_args()

def main_with_args():
    """Main function with command line argument support."""
    args = parse_arguments()
    
    # If --list flag is provided, just list all spinners and exit
    if args.list:
        console.print("[bold cyan]Available Spinner Styles:[/bold cyan]")
        for i, style in enumerate(SPINNER_FILTERED, 1):
            console.print(f"{i:3d}. {style}")
        return
    
    # Validate start_index
    if args.start_index < 1:
        console.print("[bold red]Start index must be at least 1.[/bold red]")
        return
    
    if args.start_index > len(SPINNER_FILTERED):
        console.print(f"[bold red]Start index must be at most {len(SPINNER_FILTERED)}.[/bold red]")
        return
    
    # Adjust for 0-based indexing
    start_idx = args.start_index - 1
    
    # Run the main demo starting from the specified index
    main(start_idx)

def main(start_idx=0):
    """Main function to demonstrate all spinner styles."""
    console.clear()
    
    # Triple-sized header with block characters
    console.print("\n")
    console.print("[bold cyan]████████████████████████████████████[/bold cyan]")
    console.print("[bold cyan]█                                  █[/bold cyan]")
    console.print("[bold cyan]█      RICH SPINNER DEMO           █[/bold cyan]")
    console.print("[bold cyan]█                                  █[/bold cyan]")
    console.print("[bold cyan]████████████████████████████████████[/bold cyan]")
    console.print("\n\n")
    
    # Larger instructions
    console.print("[bold]■■■ SPINNER STYLE SHOWCASE ■■■[/bold]")
    console.print("This script demonstrates all available spinner styles in Rich.")
    console.print("Press [key]Y[/key] to see the next spinner or [key]N[/key] to exit.\n")
    
    # Show info about starting position if not at the beginning
    if start_idx > 0:
        console.print(f"[bold yellow]Starting from spinner {start_idx + 1}/{len(SPINNER_FILTERED)}[/bold yellow]")
    
    # Skip spinners before the start index
    spinners_to_show = SPINNER_FILTERED[start_idx:]
    
    for i, style in enumerate(spinners_to_show, start_idx + 1):
        # Simple spinner counter
        console.print(f"\n[bold cyan]SPINNER {i}/{len(SPINNER_FILTERED)}[/bold cyan]")
        if not demonstrate_spinner(style):
            console.print("\n[bold red]Demo ended by user.[/bold red]")
            break
    else:
        console.print("\n[bold green]All spinner styles demonstrated![/bold green]")

if __name__ == "__main__":
    try:
        main_with_args()
    except KeyboardInterrupt:
        console.print("\n\n[bold]Demo interrupted by user.[/bold]")
        sys.exit(0)