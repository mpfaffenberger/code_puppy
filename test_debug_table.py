#!/usr/bin/env python3
"""
Debug script to see what's happening with Rich Table objects.
"""

from rich.console import Console
from rich.table import Table
from code_puppy.messaging import get_global_queue, MessageType

def debug_table():
    queue = get_global_queue()
    
    # Create a table
    table = Table()
    table.add_column("Name")
    table.add_column("Value")
    table.add_row("Test", "123")
    
    print(f"Table type: {type(table)}")
    print(f"Table has __rich_console__: {hasattr(table, '__rich_console__')}")
    print(f"Table str: {str(table)}")
    
    # Emit to queue
    queue.emit_simple(MessageType.INFO, table)
    
    # Get from queue
    message = queue.get_nowait()
    if message:
        print(f"Message content type: {type(message.content)}")
        print(f"Message content has __rich_console__: {hasattr(message.content, '__rich_console__')}")
        print(f"Message content str: {str(message.content)}")
        
        # Try rendering directly
        console = Console()
        print("\nDirect console.print of message.content:")
        console.print(message.content)

if __name__ == "__main__":
    debug_table()