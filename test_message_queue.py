#!/usr/bin/env python3
"""
Simple test script to verify the message queue system works.
"""

import time

from rich.console import Console
from rich.table import Table

# Test our message queue system
from code_puppy.messaging import (
    SynchronousInteractiveRenderer,
    emit_error,
    emit_info,
    emit_success,
    get_global_queue,
)
from code_puppy.tools.common import console as tools_console


def test_message_queue():
    """Test the message queue system."""
    print("🐶 Testing Code Puppy Message Queue System")

    # Get the global queue
    queue = get_global_queue()

    # Create a renderer that outputs to a real Rich console
    rich_console = Console()
    renderer = SynchronousInteractiveRenderer(queue, rich_console)
    renderer.start()

    print("\n--- Testing direct queue emissions ---")

    # Test direct emissions
    emit_info("This is an info message")
    emit_success("This is a success message")
    emit_error("This is an error message")

    # Give renderer time to process
    time.sleep(0.1)

    print("\n--- Testing tools console (queue-based) ---")

    # Test the tools console (should go through queue)
    tools_console.print("This message comes from tools console!", style="blue")
    tools_console.print("[red]This is a red error message[/red]")
    tools_console.print("[green]This is a green success message[/green]")

    # Test with Rich objects
    table = Table()
    table.add_column("Name")
    table.add_column("Value")
    table.add_row("Test", "123")
    table.add_row("Queue", "Working")

    print("\nDirect Rich console table:")
    rich_console.print(table)

    print("\nTools console table (through queue):")
    tools_console.print(table)

    # Give renderer time to process
    time.sleep(0.2)

    print("\n--- Test completed ---")
    renderer.stop()


if __name__ == "__main__":
    test_message_queue()
