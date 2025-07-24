"""
Tools modal screen.
"""

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Markdown, Static


class ToolsScreen(ModalScreen):
    """Tools modal screen displaying TOOLS.md content."""

    DEFAULT_CSS = """
    ToolsScreen {
        align: center middle;
    }

    #tools-dialog {
        width: 95;
        height: 40;
        border: thick $primary;
        background: $surface;
        padding: 1;
    }

    #tools-content {
        height: 1fr;
        margin: 0 0 1 0;
        overflow-y: auto;
    }

    #tools-buttons {
        layout: horizontal;
        height: 3;
        align: center middle;
    }

    #dismiss-button {
        margin: 0 1;
    }

    #tools-markdown {
        margin: 0;
        padding: 0;
    }

    /* Style markdown elements for better readability */
    Markdown {
        margin: 0;
        padding: 0;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="tools-dialog"):
            yield Static("🛠️  Cooper's Toolkit\n", id="tools-title")
            with VerticalScroll(id="tools-content"):
                yield Markdown(self.get_tools_content(), id="tools-markdown")
            with Container(id="tools-buttons"):
                yield Button("Dismiss", id="dismiss-button", variant="primary")

    def get_tools_content(self) -> str:
        """Get the tools content from TOOLS.md."""
        try:
            # Try to read TOOLS.md from the tools directory
            tools_file_path = "code_puppy/tools/TOOLS.md"
            with open(tools_file_path, "r", encoding="utf-8") as f:
                content = f.read()
            return content
        except FileNotFoundError:
            return """
# 🐶 Woof! TOOLS.md not found, but here's what I can do:

## 🛠️ Available Tools

### 📁 **File Operations**
- **`list_files`** - Browse directories like a good sniffing dog!
- **`read_file`** - Read any file content
- **`edit_file`** - The ultimate file editor!
- **`delete_file`** - Remove files when needed

### 🔍 **Search & Analysis**
- **`grep`** - Search for text across files recursively
- **`code_map`** - Generate beautiful code structure maps

### 💻 **System Operations**
- **`agent_run_shell_command`** - Execute shell commands

### 🌐 **Network Operations**
- **`grab_json_from_url`** - Fetch JSON data from URLs

### 🧠 **Agent Communication**
- **`agent_share_your_reasoning`** - Peek into my thought process
- **`final_result`** - Deliver final responses

I follow **DRY**, **YAGNI**, and **SOLID** principles religiously!
Ready to fetch some code sticks? 🔧✨
"""

    @on(Button.Pressed, "#dismiss-button")
    def dismiss_tools(self) -> None:
        """Dismiss the tools modal."""
        self.dismiss()

    def on_key(self, event) -> None:
        """Handle key events."""
        if event.key == "escape":
            self.dismiss()
