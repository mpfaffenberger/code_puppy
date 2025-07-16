#!/usr/bin/env python3
"""
Halo Spinner Demo Script

This script demonstrates all available spinner styles in Halo with colors
that match the Textual dark theme. Press 'y' to see the next spinner
or 'n' to exit.

Usage:
    python spinner_demo_halo.py [start_index]
    
    start_index: Optional index to start from (1-based, e.g. 42 to start from the 42nd spinner)

Requirements:
    pip install halo
"""

import time
import sys
import argparse
from termcolor import colored

# Try to import Halo - handle gracefully if not installed
try:
    from halo import Halo
    HALO_AVAILABLE = True
except ImportError:
    HALO_AVAILABLE = False
    print("Halo not installed. Please install with: pip install halo")
    print("Continuing in demo mode...")

# Get all available spinner styles from Halo/spinners library
def get_all_spinner_styles():
    """Get all available spinner styles from the spinners library."""
    if not HALO_AVAILABLE:
        # Fallback list for demo mode
        return [
            "dots", "dots2", "dots3", "line", "arc", "arrow", "arrow2", "arrow3",
            "bouncingBar", "bouncingBall", "christmas", "clock", "earth", "moon",
            "monkey", "hearts", "star", "star2", "runner", "point", "weather", "smiley"
        ]
    
    try:
        from spinners import Spinners
        # Get all spinner attributes (excluding private ones)
        return [attr for attr in dir(Spinners) if not attr.startswith('_')]
    except ImportError:
        # Fallback if spinners import fails
        return [
            "dots", "dots2", "dots3", "line", "arc", "arrow", "arrow2", "arrow3",
            "bouncingBar", "bouncingBall", "christmas", "clock", "earth", "moon",
            "monkey", "hearts", "star", "star2", "runner", "point", "weather", "smiley"
        ]

# Get all available spinner styles
SPINNER_STYLES = get_all_spinner_styles()

# Colors that work well with dark backgrounds
COLORS = [
    "green", "cyan", "yellow", "magenta", "blue", "white"
]

def demonstrate_spinner(spinner_style, color_idx=0):
    """Demonstrate a single spinner style with pause and user prompt."""
    if not HALO_AVAILABLE:
        print(f"\nStyle: {spinner_style} (Demo mode - Halo not installed)")
        time.sleep(3)
        response = input("Next spinner? (y/n): ").lower()
        return response != 'n'
    
    # Get color (cycle through colors)
    color = COLORS[color_idx % len(COLORS)]
    
    print(f"\n{colored('Style:', 'white', attrs=['bold'])} {colored(spinner_style, color, attrs=['bold'])}")
    
    # Add some space before spinner
    print("\n\n")
    
    # Create and configure spinner
    spinner = Halo(
        text=f"Processing your request...",
        spinner=spinner_style,
        color=color,
        text_color=color,
    )
    
    # Start the spinner
    spinner.start()
    
    try:
        # Show the spinner for a few seconds
        time.sleep(4.8)  # Same duration as Rich demo
    finally:
        # Always stop the spinner to restore cursor
        spinner.stop()
    
    # Add space after spinner
    print("\n")
    
    # Prompt for next spinner
    prompt = colored("▶ Next spinner? (Y/N):", "yellow", attrs=['bold'])
    response = input(f"{prompt} ").lower()
    return response != 'n'

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Halo Spinner Demo - Show all available spinner styles"
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
        print(colored("Available Spinner Styles:", "cyan", attrs=['bold']))
        for i, style in enumerate(SPINNER_STYLES, 1):
            print(f"{i:3d}. {style}")
        return
    
    # Validate start_index
    if args.start_index < 1:
        print(colored("Start index must be at least 1.", "red", attrs=['bold']))
        return
    
    if args.start_index > len(SPINNER_STYLES):
        print(colored(f"Start index must be at most {len(SPINNER_STYLES)}.", "red", attrs=['bold']))
        return
    
    # Adjust for 0-based indexing
    start_idx = args.start_index - 1
    
    # Run the main demo starting from the specified index
    main(start_idx)

def main(start_idx=0):
    """Main function to demonstrate all spinner styles."""
    if sys.platform != "win32":
        # Clear screen (not supported on Windows)
        print("\033c", end="")
    
    # Print header
    print("\n")
    print(colored("████████████████████████████████████", "cyan", attrs=['bold']))
    print(colored("█                                  █", "cyan", attrs=['bold']))
    print(colored("█      HALO SPINNER DEMO           █", "cyan", attrs=['bold']))
    print(colored("█                                  █", "cyan", attrs=['bold']))
    print(colored("████████████████████████████████████", "cyan", attrs=['bold']))
    print("\n\n")
    
    # Print instructions
    print(colored("■■■ SPINNER STYLE SHOWCASE ■■■", attrs=['bold']))
    print("This script demonstrates all available spinner styles in Halo.")
    print(f"Press {colored('Y', 'green', attrs=['bold'])} to see the next spinner or {colored('N', 'green', attrs=['bold'])} to exit.\n")
    
    # Show info about starting position if not at the beginning
    if start_idx > 0:
        print(colored(f"Starting from spinner {start_idx + 1}/{len(SPINNER_STYLES)}", "yellow", attrs=['bold']))
    
    # Skip spinners before the start index
    spinners_to_show = SPINNER_STYLES[start_idx:]
    
    for i, style in enumerate(spinners_to_show, start_idx + 1):
        # Simple spinner counter with color cycling
        color_idx = i % len(COLORS)
        color = COLORS[color_idx]
        print(f"\n{colored(f'SPINNER {i}/{len(SPINNER_STYLES)}', color, attrs=['bold'])}")
        
        if not demonstrate_spinner(style, color_idx):
            print(f"\n{colored('Demo ended by user.', 'red', attrs=['bold'])}")
            break
    else:
        print(f"\n{colored('All spinner styles demonstrated!', 'green', attrs=['bold'])}")
    


if __name__ == "__main__":
    try:
        main_with_args()
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user.")
        sys.exit(0)