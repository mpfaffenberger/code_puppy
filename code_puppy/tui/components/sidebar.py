"""
Sidebar component with tabs for history, files, and models.
"""

import os
from pathlib import Path
from typing import List, Optional

from textual.containers import Container
from textual.widgets import Static, ListView, ListItem, Label, TabbedContent, TabPane, DirectoryTree
from textual.app import ComposeResult
from textual.message import Message
from textual import on


class FileBrowser(Container):
    """File browser component using DirectoryTree."""
    
    class FileSelected(Message):
        """Message sent when a file is selected."""
        def __init__(self, file_path: str) -> None:
            self.file_path = file_path
            super().__init__()
    
    def compose(self) -> ComposeResult:
        """Create the file browser layout."""
        yield DirectoryTree("./", id="file-tree")
    
    @on(DirectoryTree.FileSelected)
    def on_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        """Handle file selection."""
        # Emit our custom message
        self.post_message(self.FileSelected(str(event.path)))


class Sidebar(Container):
    """Sidebar with tabs for session history, file browser, and model selection."""

    DEFAULT_CSS = """
    Sidebar {
        dock: left;
        width: 30;
        min-width: 20;
        max-width: 50;
        background: $surface;
        border-right: solid $primary;
        display: none;
    }

    #sidebar-tabs {
        height: 1fr;
    }

    #history-list {
        height: 1fr;
    }
    
    #file-tree {
        height: 1fr;
    }
    
    #models-list {
        height: 1fr;
    }

    .history-interactive {
        color: #34d399;
    }

    .history-tui {
        color: #60a5fa;
    }

    .history-system {
        color: #fbbf24;
        text-style: italic;
    }

    .history-command {
        color: #f87171;
    }

    .history-generic {
        color: #d1d5db;
    }

    .history-empty {
        color: #6b7280;
        text-style: italic;
    }

    .history-error {
        color: #ef4444;
    }
    
    .file-item {
        color: #d1d5db;
    }
    
    .model-item {
        color: #a78bfa;
    }
    
    .model-active {
        color: #34d399;
        text-style: bold;
    }
    """

    def compose(self) -> ComposeResult:
        """Create the sidebar layout with tabs."""
        with TabbedContent(id="sidebar-tabs"):
            with TabPane("📜 History", id="history-tab"):
                yield ListView(id="history-list")
            with TabPane("📁 Files", id="files-tab"):
                yield FileBrowser()
            with TabPane("🤖 Models", id="models-tab"):
                yield ListView(id="models-list")
    
    def on_mount(self) -> None:
        """Initialize the sidebar when mounted."""
        self.load_models_list()
    
    def load_models_list(self) -> None:
        """Load available models into the models tab."""
        try:
            models_list = self.query_one("#models-list", ListView)
            
            # Import here to avoid circular imports
            from code_puppy.config import get_model_name
            from code_puppy.model_factory import load_config
            
            current_model = get_model_name()
            config = load_config()
            
            if config and 'models' in config:
                for model_name, model_config in config['models'].items():
                    # Show model type and current indicator
                    model_type = model_config.get('type', 'unknown')
                    is_current = model_name == current_model
                    
                    if is_current:
                        display_text = f"● {model_name} ({model_type})"
                        css_class = "model-active"
                    else:
                        display_text = f"  {model_name} ({model_type})"
                        css_class = "model-item"
                    
                    label = Label(display_text, classes=css_class)
                    model_item = ListItem(label)
                    model_item.model_name = model_name  # Store for selection
                    models_list.append(model_item)
            else:
                models_list.append(
                    ListItem(Label("No models configured", classes="history-empty"))
                )
                
        except Exception as e:
            # Fallback if model loading fails
            try:
                models_list = self.query_one("#models-list", ListView)
                models_list.append(
                    ListItem(Label(f"Error loading models: {str(e)}", classes="history-error"))
                )
            except Exception:
                pass  # Silently fail if even error display fails
    
    @on(FileBrowser.FileSelected)
    def on_file_browser_file_selected(self, event: FileBrowser.FileSelected) -> None:
        """Handle file selection from the file browser."""
        # Forward the message to the parent app
        self.post_message(event)
