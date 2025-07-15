#!/usr/bin/env python3
"""
Debug script to see what's happening in the renderer.
"""

import time
from rich.console import Console
from rich.table import Table
from code_puppy.messaging import get_global_queue, MessageType, SynchronousInteractiveRenderer

def debug_renderer():
    queue = get_global_queue()
    console = Console()
    
    # Create custom renderer with debug output
    class DebugRenderer(SynchronousInteractiveRenderer):
        def _render_message(self, message):
            print(f"\n[DEBUG] Rendering message:")
            print(f"  Type: {message.type}")
            print(f"  Content type: {type(message.content)}")
            print(f"  Content isinstance str: {isinstance(message.content, str)}")
            print(f"  Content: {repr(message.content)}")
            
            # Call parent method
            super()._render_message(message)
    
    renderer = DebugRenderer(queue, console)
    renderer.start()
    
    # Create and emit a table
    table = Table()
    table.add_column("Debug")
    table.add_column("Test")
    table.add_row("Row1", "Data1")
    
    print("Emitting table to queue...")
    queue.emit_simple(MessageType.INFO, table)
    
    # Give time to process
    time.sleep(0.1)
    
    print("Stopping renderer...")
    renderer.stop()

if __name__ == "__main__":
    debug_renderer()