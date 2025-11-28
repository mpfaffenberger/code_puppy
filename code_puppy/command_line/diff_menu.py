"""Interactive nested menu for diff configuration.

Now using the fixed arrow_select_async with proper HTML escaping.
Supports cycling through all supported languages with left/right arrows!
"""

import io
import sys
import time
from typing import Callable, Optional

from prompt_toolkit import Application
from prompt_toolkit.formatted_text import ANSI, FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame
from rich.console import Console

# Sample code snippets for each language
LANGUAGE_SAMPLES = {
    "python": (
        "calculator.py",
        """--- a/calculator.py
+++ b/calculator.py
@@ -1,12 +1,15 @@
 def calculate_total(items, tax_rate=0.08):
+    # Calculate total price
+    total = 0
+    for item in items:
+        total += item['price']
-    # Calculate subtotal with discount
-    subtotal = sum(item['price'] * item.get('quantity', 1) for item in items)
-    discount = subtotal * 0.1 if subtotal > 100 else 0
     
+    # Add tax
+    tax = total * tax_rate
+    final_total = total + tax
-    # Apply tax to discounted amount
-    taxable_amount = subtotal - discount
-    tax = round(taxable_amount * tax_rate, 2)
-    final_total = taxable_amount + tax
     
+    return final_total
-    return {
-        'subtotal': subtotal,
-        'discount': discount,
-        'tax': tax,
-        'total': final_total
-    }""",
    ),
    "javascript": (
        "app.js",
        """--- a/app.js
+++ b/app.js
@@ -1,10 +1,12 @@
-function fetchUserData(userId) {
-    return fetch(`/api/users/${userId}`)
-        .then(response => response.json())
-        .then(data => {
-            return data.user;
-        })
-        .catch(error => console.error(error));
+async function fetchUserData(userId) {
+    try {
+        const response = await fetch(`/api/users/${userId}`);
+        const data = await response.json();
+        return data.user;
+    } catch (error) {
+        console.error('Failed to fetch user:', error);
+        throw error;
+    }
 }""",
    ),
    "typescript": (
        "service.ts",
        """--- a/service.ts
+++ b/service.ts
@@ -1,8 +1,11 @@
-class UserService {
-    getUser(id: number) {
-        return this.http.get(`/users/${id}`);
+interface User {
+    id: number;
+    name: string;
+}
+
+class UserService {
+    async getUser(id: number): Promise<User> {
+        const response = await this.http.get<User>(`/users/${id}`);
+        return response.data;
     }
-    deleteUser(id: number) {
-        return this.http.delete(`/users/${id}`);
-    }
 }""",
    ),
    "rust": (
        "main.rs",
        """--- a/main.rs
+++ b/main.rs
@@ -1,8 +1,10 @@
-fn calculate_sum(numbers: Vec<i32>) -> i32 {
-    let mut total = 0;
-    for num in numbers {
-        total = total + num;
+fn calculate_sum(numbers: &[i32]) -> i32 {
+    numbers.iter().sum()
+}
+
+fn calculate_average(numbers: &[i32]) -> f64 {
+    if numbers.is_empty() {
+        return 0.0;
     }
-    total
+    calculate_sum(numbers) as f64 / numbers.len() as f64
 }""",
    ),
    "go": (
        "handler.go",
        """--- a/handler.go
+++ b/handler.go
@@ -1,10 +1,15 @@
-func HandleRequest(w http.ResponseWriter, r *http.Request) {
-    data := getData()
-    json.NewEncoder(w).Encode(data)
+func HandleRequest(w http.ResponseWriter, r *http.Request) error {
+    data, err := getData()
+    if err != nil {
+        http.Error(w, err.Error(), http.StatusInternalServerError)
+        return err
+    }
+    w.Header().Set("Content-Type", "application/json")
+    return json.NewEncoder(w).Encode(data)
 }
 
-func getData() map[string]interface{} {
-    return map[string]interface{}{"status": "ok"}
+func getData() (map[string]interface{}, error) {
+    return map[string]interface{}{"status": "ok"}, nil
 }""",
    ),
    "java": (
        "Calculator.java",
        """--- a/Calculator.java
+++ b/Calculator.java
@@ -1,8 +1,12 @@
 public class Calculator {
-    public int add(int a, int b) {
-        return a + b;
+    public double calculateTotal(List<Double> prices) {
+        return prices.stream()
+            .reduce(0.0, Double::sum);
     }
     
-    public int multiply(int a, int b) {
-        return a * b;
+    public double calculateAverage(List<Double> prices) {
+        if (prices.isEmpty()) {
+            return 0.0;
+        }
+        return calculateTotal(prices) / prices.size();
     }
 }""",
    ),
    "ruby": (
        "calculator.rb",
        """--- a/calculator.rb
+++ b/calculator.rb
@@ -1,8 +1,10 @@
 class Calculator
-  def add(a, b)
-    a + b
+  def calculate_total(items)
+    items.sum { |item| item[:price] }
   end
   
-  def multiply(a, b)
-    a * b
+  def calculate_average(items)
+    return 0 if items.empty?
+    
+    calculate_total(items) / items.size.to_f
   end
 end""",
    ),
    "csharp": (
        "Calculator.cs",
        """--- a/Calculator.cs
+++ b/Calculator.cs
@@ -1,10 +1,14 @@
-public class Calculator {
-    public int Add(int a, int b) {
-        return a + b;
+public class Calculator 
+{
+    public decimal CalculateTotal(IEnumerable<decimal> prices) 
+    {
+        return prices.Sum();
     }
     
-    public int Multiply(int a, int b) {
-        return a * b;
+    public decimal CalculateAverage(IEnumerable<decimal> prices) 
+    {
+        var priceList = prices.ToList();
+        return priceList.Any() ? priceList.Average() : 0m;
     }
 }""",
    ),
    "php": (
        "Calculator.php",
        """--- a/Calculator.php
+++ b/Calculator.php
@@ -1,10 +1,14 @@
 <?php
 class Calculator {
-    public function add($a, $b) {
-        return $a + $b;
+    public function calculateTotal(array $items): float {
+        return array_sum(array_column($items, 'price'));
     }
     
-    public function multiply($a, $b) {
-        return $a * $b;
+    public function calculateAverage(array $items): float {
+        if (empty($items)) {
+            return 0.0;
+        }
+        return $this->calculateTotal($items) / count($items);
     }
 }""",
    ),
    "html": (
        "index.html",
        """--- a/index.html
+++ b/index.html
@@ -1,5 +1,8 @@
 <div class="container">
-    <h1>Welcome</h1>
-    <p>Hello World</p>
+    <header>
+        <h1>Welcome to Our Site</h1>
+        <nav>
+            <a href="#home">Home</a>
+            <a href="#about">About</a>
+        </nav>
+    </header>
 </div>""",
    ),
    "css": (
        "styles.css",
        """--- a/styles.css
+++ b/styles.css
@@ -1,5 +1,10 @@
 .container {
-    width: 100%;
-    padding: 20px;
+    max-width: 1200px;
+    margin: 0 auto;
+    padding: 2rem;
+}
+
+.container header {
+    display: flex;
+    justify-content: space-between;
+    align-items: center;
 }""",
    ),
    "json": (
        "config.json",
        """--- a/config.json
+++ b/config.json
@@ -1,5 +1,8 @@
 {
-    "name": "app",
-    "version": "1.0.0"
+    "name": "my-awesome-app",
+    "version": "2.0.0",
+    "description": "An awesome application",
+    "author": "Code Puppy",
+    "license": "MIT"
 }""",
    ),
    "yaml": (
        "config.yml",
        """--- a/config.yml
+++ b/config.yml
@@ -1,4 +1,8 @@
 app:
   name: myapp
-  version: 1.0
+  version: 2.0
+  environment: production
+  
+database:
+  host: localhost
+  port: 5432""",
    ),
    "bash": (
        "deploy.sh",
        """--- a/deploy.sh
+++ b/deploy.sh
@@ -1,5 +1,9 @@
 #!/bin/bash
-echo \"Deploying...\"
-npm run build
+set -e
+
+echo \"Starting deployment...\"
+npm run build --production
+npm run test
+echo \"Deployment complete!\"""",
    ),
    "sql": (
        "schema.sql",
        """--- a/schema.sql
+++ b/schema.sql
@@ -1,5 +1,9 @@
 CREATE TABLE users (
     id INTEGER PRIMARY KEY,
-    name TEXT
+    name TEXT NOT NULL,
+    email TEXT UNIQUE NOT NULL,
+    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
 );
+
+CREATE INDEX idx_users_email ON users(email);""",
    ),
}

# Get all supported languages in a consistent order
SUPPORTED_LANGUAGES = [
    "python",
    "javascript",
    "typescript",
    "rust",
    "go",
    "java",
    "ruby",
    "csharp",
    "php",
    "html",
    "css",
    "json",
    "yaml",
    "bash",
    "sql",
]


class DiffConfiguration:
    """Holds the current diff configuration state."""

    def __init__(self):
        """Initialize configuration from current settings."""
        from code_puppy.config import (
            get_diff_addition_color,
            get_diff_deletion_color,
        )

        self.current_add_color = get_diff_addition_color()
        self.current_del_color = get_diff_deletion_color()
        self.original_add_color = self.current_add_color
        self.original_del_color = self.current_del_color
        self.current_language_index = 0  # Track current language for preview

    def has_changes(self) -> bool:
        """Check if any changes have been made."""
        return (
            self.current_add_color != self.original_add_color
            or self.current_del_color != self.original_del_color
        )

    def next_language(self):
        """Cycle to the next language."""
        self.current_language_index = (self.current_language_index + 1) % len(
            SUPPORTED_LANGUAGES
        )

    def prev_language(self):
        """Cycle to the previous language."""
        self.current_language_index = (self.current_language_index - 1) % len(
            SUPPORTED_LANGUAGES
        )

    def get_current_language(self) -> str:
        """Get the currently selected language."""
        return SUPPORTED_LANGUAGES[self.current_language_index]


async def interactive_diff_picker() -> Optional[dict]:
    """Show an interactive full-screen terminal UI to configure diff settings.

    Returns:
        A dict with changes or None if cancelled
    """
    from code_puppy.tools.command_runner import set_awaiting_user_input

    config = DiffConfiguration()

    set_awaiting_user_input(True)

    # Enter alternate screen buffer once for entire session
    sys.stdout.write("\033[?1049h")  # Enter alternate buffer
    sys.stdout.write("\033[2J\033[H")  # Clear and home
    sys.stdout.flush()
    time.sleep(0.1)  # Minimal delay for state sync

    try:
        # Main menu loop
        while True:
            choices = [
                "Configure Addition Color",
                "Configure Deletion Color",
            ]

            if config.has_changes():
                choices.append("Save & Exit")
            else:
                choices.append("Exit")

            # Dummy update function for main menu (config doesn't change on navigation)
            def dummy_update(choice: str):
                pass

            def get_main_preview():
                return _get_preview_text_for_prompt_toolkit(config)

            try:
                selected = await _split_panel_selector(
                    "Diff Color Configuration",
                    choices,
                    dummy_update,
                    get_preview=get_main_preview,
                    config=config,
                )
            except KeyboardInterrupt:
                break

            # Handle selection
            if "Addition" in selected:
                await _handle_color_menu(config, "additions")
            elif "Deletion" in selected:
                await _handle_color_menu(config, "deletions")
            else:
                # Exit
                break

    except Exception:
        # Silent error - just exit cleanly
        return None
    finally:
        set_awaiting_user_input(False)
        # Exit alternate screen buffer once at end
        sys.stdout.write("\033[?1049l")  # Exit alternate buffer
        sys.stdout.flush()

    # Return changes if any
    if config.has_changes():
        return {
            "add_color": config.current_add_color,
            "del_color": config.current_del_color,
        }

    return None


async def _split_panel_selector(
    title: str,
    choices: list[str],
    on_change: Callable[[str], None],
    get_preview: Callable[[], ANSI],
    config: Optional[DiffConfiguration] = None,
) -> Optional[str]:
    """Split-panel selector with menu on left and live preview on right.

    Supports left/right arrow navigation through languages if config is provided.
    """
    selected_index = [0]
    result = [None]

    def get_left_panel_text():
        """Generate the selector menu text."""
        try:
            lines = []
            lines.append(("bold cyan", title))
            lines.append(("", "\n\n"))

            if not choices:
                lines.append(("fg:ansiyellow", "No choices available"))
                lines.append(("", "\n"))
            else:
                for i, choice in enumerate(choices):
                    if i == selected_index[0]:
                        lines.append(("fg:ansigreen", "▶ "))
                        lines.append(("fg:ansigreen bold", choice))
                    else:
                        lines.append(("", "  "))
                        lines.append(("", choice))
                    lines.append(("", "\n"))

            lines.append(("", "\n"))

            # Add language navigation hint if config is available
            if config is not None:
                current_lang = config.get_current_language()
                lang_hint = f"Language: {current_lang.upper()}  (←→ to change)"
                lines.append(("fg:ansiyellow", lang_hint))
                lines.append(("", "\n"))

            lines.append(
                ("fg:ansicyan", "↑↓ Navigate  │  Enter Confirm  │  Ctrl-C Cancel")
            )
            return FormattedText(lines)
        except Exception as e:
            return FormattedText([("fg:ansired", f"Error: {e}")])

    def get_right_panel_text():
        """Generate the preview panel text."""
        try:
            preview = get_preview()
            # get_preview() now returns ANSI, which is already FormattedText-compatible
            return preview
        except Exception as e:
            return FormattedText([("fg:ansired", f"Preview error: {e}")])

    kb = KeyBindings()

    @kb.add("up")
    def move_up(event):
        if choices:
            selected_index[0] = (selected_index[0] - 1) % len(choices)
            on_change(choices[selected_index[0]])
        event.app.invalidate()

    @kb.add("down")
    def move_down(event):
        if choices:
            selected_index[0] = (selected_index[0] + 1) % len(choices)
            on_change(choices[selected_index[0]])
        event.app.invalidate()

    @kb.add("left")
    def prev_lang(event):
        if config is not None:
            config.prev_language()
            event.app.invalidate()

    @kb.add("right")
    def next_lang(event):
        if config is not None:
            config.next_language()
            event.app.invalidate()

    @kb.add("enter")
    def accept(event):
        if choices:
            result[0] = choices[selected_index[0]]
        else:
            result[0] = None
        event.app.exit()

    @kb.add("c-c")
    def cancel(event):
        result[0] = None
        event.app.exit()

    # Create split layout with left (selector) and right (preview) panels
    left_panel = Window(
        content=FormattedTextControl(lambda: get_left_panel_text()),
        width=50,
    )

    right_panel = Window(
        content=FormattedTextControl(lambda: get_right_panel_text()),
    )

    # Create vertical split (side-by-side panels)
    root_container = VSplit(
        [
            Frame(left_panel, title="Menu"),
            Frame(right_panel, title="Preview"),
        ]
    )

    layout = Layout(root_container)
    app = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=False,  # Don't use full_screen to avoid buffer issues
        mouse_support=False,
        color_depth="DEPTH_24_BIT",  # Enable truecolor support
    )

    sys.stdout.flush()
    sys.stdout.flush()

    # Trigger initial update only if choices is not empty
    if choices:
        on_change(choices[selected_index[0]])

    # Just clear the current buffer (don't switch buffers)
    sys.stdout.write("\033[2J\033[H")  # Clear screen within current buffer
    sys.stdout.flush()

    # Run application (stays in same alternate buffer)
    await app.run_async()

    if result[0] is None:
        raise KeyboardInterrupt()

    return result[0]


ADDITION_COLORS = {
    # primary first (darkened)
    "dark green": "#0b3e0b",
    "darker green": "#0b1f0b",
    "dark aqua": "#164952",
    "deep teal": "#143f3c",
    # blues (darkened)
    "sky blue": "#406884",
    "soft blue": "#315c78",
    "steel blue": "#20394e",
    "forest teal": "#124831",
    "cool teal": "#1b4b54",
    "marine aqua": "#275860",
    "slate blue": "#304f69",
    "deep steel": "#1e3748",
    "shadow olive": "#2f3a15",
    "deep moss": "#1f3310",
    # G
    "midnight spruce": "#0f3a29",
    "shadow jade": "#0d4a3a",
    # B
    "abyss blue": "#0d2f4d",
    "midnight fjord": "#133552",
    # I
    "dusky indigo": "#1a234d",
    "nocturne indigo": "#161d3f",
    # V
    "midnight violet": "#2a1a3f",
    "deep amethyst": "#3a2860",
}

DELETION_COLORS = {
    # primary first (darkened)
    "dark red": "#4a0f0f",
    # pinks / reds (darkened)
    "pink": "#7f143b",
    "soft red": "#741f3c",
    "salmon": "#842848",
    "rose": "#681c35",
    "deep rose": "#4f1428",
    # oranges (darkened)
    "burnt orange": "#753b10",
    "deep orange": "#5b2b0d",
    # yellows (darkened)
    "amber": "#69551c",
    # reds (darkened)
    "red": "#5d0b0b",
    "ruby": "#5b141f",
    "wine": "#390e1a",
    # purples (darkened)
    "purple": "#5a4284",
    "soft purple": "#503977",
    "violet": "#432758",
    # ROYGBIV deletions (unchanged)
    # R
    "ember crimson": "#5a0e12",
    "smoked ruby": "#4b0b16",
    # O
    "molten orange": "#70340c",
    "baked amber": "#5c2b0a",
    # Y
    "burnt ochre": "#5a4110",
    "tawny umber": "#4c3810",
    # G
    "swamp olive": "#3c3a14",
    "bog green": "#343410",
    # B
    "dusky petrol": "#2a3744",
    "warm slate": "#263038",
    # I
    "wine indigo": "#311b3f",
    "mulberry dusk": "#3f1f52",
    # V
    "garnet plum": "#4a1e3a",
    "dusky magenta": "#5a1f4c",
}


def _convert_rich_color_to_prompt_toolkit(color: str) -> str:
    """Convert Rich color names to prompt-toolkit compatible names."""
    # Hex colors pass through as-is
    if color.startswith("#"):
        return color
    # Map bright_ colors to ansi equivalents
    if color.startswith("bright_"):
        return "ansi" + color.replace("bright_", "")
    # Basic terminal colors
    if color.lower() in [
        "black",
        "red",
        "green",
        "yellow",
        "blue",
        "magenta",
        "cyan",
        "white",
        "gray",
        "grey",
    ]:
        return color.lower()
    # Default safe fallback for unknown colors
    return "white"


def _get_preview_text_for_prompt_toolkit(config: DiffConfiguration) -> ANSI:
    """Get preview as ANSI for embedding in selector with live colors.

    Returns ANSI-formatted text that prompt_toolkit can render with full colors.
    """
    from code_puppy.tools.common import format_diff_with_colors

    # Get the current language and its sample
    current_lang = config.get_current_language()
    filename, sample_diff = LANGUAGE_SAMPLES.get(
        current_lang,
        LANGUAGE_SAMPLES["python"],  # Fallback to Python
    )

    # Build header with current settings info using Rich markup
    header_parts = []
    header_parts.append("[bold]═" * 50 + "[/bold]")
    header_parts.append(
        "[bold cyan] LIVE PREVIEW - Syntax Highlighted Diff[/bold cyan]"
    )
    header_parts.append("[bold]═" * 50 + "[/bold]")
    header_parts.append("")
    header_parts.append(f" Addition Color: [bold]{config.current_add_color}[/bold]")
    header_parts.append(f" Deletion Color: [bold]{config.current_del_color}[/bold]")
    header_parts.append("")
    header_parts.append(
        f" [bold yellow]Language: {current_lang.upper()}[/bold yellow]  "
        f"[dim](← → to cycle)[/dim]"
    )
    header_parts.append("")
    header_parts.append(f"[bold] Example ({filename}):[/bold]")
    header_parts.append("")

    header_text = "\n".join(header_parts)

    # Temporarily override config to use current preview settings
    from code_puppy.config import (
        get_diff_addition_color,
        get_diff_deletion_color,
        set_diff_addition_color,
        set_diff_deletion_color,
    )

    # Save original values
    original_add_color = get_diff_addition_color()
    original_del_color = get_diff_deletion_color()

    try:
        # Temporarily set config to preview values
        set_diff_addition_color(config.current_add_color)
        set_diff_deletion_color(config.current_del_color)

        # Get the formatted diff (either Rich Text or Rich markup string)
        formatted_diff = format_diff_with_colors(sample_diff)

        # Render everything with Rich Console to get ANSI output with proper color support
        buffer = io.StringIO()
        console = Console(
            file=buffer,
            force_terminal=True,
            width=90,
            legacy_windows=False,
            color_system="truecolor",
            no_color=False,
            force_interactive=True,  # Force interactive mode for better color support
        )

        # Print header
        console.print(header_text, end="\n")

        # Print diff (handles both Text objects and markup strings)
        console.print(formatted_diff, end="\n\n")

        # Print footer
        console.print("[bold]═" * 50 + "[/bold]", end="")

        ansi_output = buffer.getvalue()

    finally:
        # Restore original config values
        set_diff_addition_color(original_add_color)
        set_diff_deletion_color(original_del_color)

    # Wrap in ANSI() so prompt_toolkit can render it
    return ANSI(ansi_output)


async def _handle_color_menu(config: DiffConfiguration, color_type: str) -> None:
    """Handle color selection with live preview updates."""
    # Text mode only (highlighted disabled)
    if color_type == "additions":
        color_dict = ADDITION_COLORS
        current = config.current_add_color
        title = "Select addition color:"
    else:
        color_dict = DELETION_COLORS
        current = config.current_del_color
        title = "Select deletion color:"

    # Build choices with nice names
    choices = []
    for name, color_value in color_dict.items():
        marker = " ← current" if color_value == current else ""
        choices.append(f"{name}{marker}")

    # Store original color for potential cancellation
    original_color = current

    # Callback for live preview updates
    def update_preview(selected_choice: str):
        # Extract color name and look up the actual color value
        color_name = selected_choice.replace(" ← current", "").strip()
        selected_color = color_dict.get(color_name, list(color_dict.values())[0])
        if color_type == "additions":
            config.current_add_color = selected_color
        else:
            config.current_del_color = selected_color

    # Function to get live preview header with colored diff
    def get_preview_header():
        return _get_preview_text_for_prompt_toolkit(config)

    try:
        # Use split panel selector with live preview (pass config for language switching)
        await _split_panel_selector(
            title,
            choices,
            update_preview,
            get_preview=get_preview_header,
            config=config,
        )
    except KeyboardInterrupt:
        # Restore original color on cancel
        if color_type == "additions":
            config.current_add_color = original_color
        else:
            config.current_del_color = original_color
    except Exception:
        pass  # Silent error handling
