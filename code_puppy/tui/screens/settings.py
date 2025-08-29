"""
Settings modal screen.
"""

from textual import on
from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Select, Static


class SettingsScreen(ModalScreen):
    """Settings configuration screen."""

    DEFAULT_CSS = """
    SettingsScreen {
        align: center middle;
    }

    #settings-dialog {
        width: 80;
        height: 33;
        border: thick $primary;
        background: $surface;
        padding: 1;
    }

    #settings-form {
        height: 1fr;
    }

    .setting-row {
        layout: horizontal;
        height: 3;
        margin: 0 0 1 0;
    }

    .setting-label {
        width: 20;
        text-align: right;
        padding: 1 1 0 0;
    }

    .setting-input {
        width: 1fr;
        margin: 0 0 0 1;
    }

    /* Additional styling for static input values */
    #yolo-static {
        padding: 1 0 0 0;  /* Align text vertically with other inputs */
        color: $success;   /* Use success color to emphasize it's enabled */
    }

    #settings-buttons {
        layout: horizontal;
        height: 3;
        align: center middle;
    }

    #save-button, #cancel-button {
        margin: 0 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.settings_data = {}

    def compose(self) -> ComposeResult:
        with Container(id="settings-dialog"):
            yield Static("⚙️  Settings Configuration", id="settings-title")
            with Container(id="settings-form"):
                with Container(classes="setting-row"):
                    yield Static("Puppy Name:", classes="setting-label")
                    yield Input(id="puppy-name-input", classes="setting-input")

                with Container(classes="setting-row"):
                    yield Static("Owner Name:", classes="setting-label")
                    yield Input(id="owner-name-input", classes="setting-input")

                with Container(classes="setting-row"):
                    yield Static("Model:", classes="setting-label")
                    yield Select([], id="model-select", classes="setting-input")

                with Container(classes="setting-row"):
                    yield Static("YOLO Mode:", classes="setting-label")
                    yield Static(
                        "✅ Enabled (always on in TUI)",
                        id="yolo-static",
                        classes="setting-input",
                    )

                with Container(classes="setting-row"):
                    yield Static("Protected Tokens:", classes="setting-label")
                    yield Input(
                        id="protected-tokens-input",
                        classes="setting-input",
                        placeholder="e.g., 50000",
                    )

                with Container(classes="setting-row"):
                    yield Static("Compaction Strategy:", classes="setting-label")
                    yield Select(
                        [
                            ("Summarization", "summarization"),
                            ("Truncation", "truncation"),
                        ],
                        id="compaction-strategy-select",
                        classes="setting-input",
                    )

                with Container(classes="setting-row"):
                    yield Static("Compaction Threshold:", classes="setting-label")
                    yield Input(
                        id="compaction-threshold-input",
                        classes="setting-input",
                        placeholder="e.g., 0.85",
                    )

            with Container(id="settings-buttons"):
                yield Button("Save", id="save-button", variant="primary")
                yield Button("Cancel", id="cancel-button")

    def on_mount(self) -> None:
        """Load current settings when the screen mounts."""
        from code_puppy.config import (
            get_model_name,
            get_owner_name,
            get_protected_token_count,
            get_puppy_name,
            get_compaction_strategy,
            get_compaction_threshold,
        )

        # Load current values
        puppy_name_input = self.query_one("#puppy-name-input", Input)
        owner_name_input = self.query_one("#owner-name-input", Input)
        model_select = self.query_one("#model-select", Select)
        protected_tokens_input = self.query_one("#protected-tokens-input", Input)
        compaction_threshold_input = self.query_one(
            "#compaction-threshold-input", Input
        )
        compaction_strategy_select = self.query_one(
            "#compaction-strategy-select", Select
        )

        puppy_name_input.value = get_puppy_name() or ""
        owner_name_input.value = get_owner_name() or ""
        protected_tokens_input.value = str(get_protected_token_count())
        compaction_threshold_input.value = str(get_compaction_threshold())
        compaction_strategy_select.value = get_compaction_strategy()

        # Load available models
        self.load_model_options(model_select)

        # Set current model selection
        current_model = get_model_name()
        model_select.value = current_model

        # YOLO mode is always enabled in TUI mode

    def load_model_options(self, model_select):
        """Load available models into the model select widget."""
        try:
            # Use the same method that interactive mode uses to load models

            from code_puppy.model_factory import ModelFactory

            # Load models using the same path and method as interactive mode
            models_data = ModelFactory.load_config()

            # Create options as (display_name, model_name) tuples
            model_options = []
            for model_name, model_config in models_data.items():
                model_type = model_config.get("type", "unknown")
                display_name = f"{model_name} ({model_type})"
                model_options.append((display_name, model_name))

            # Set the options on the select widget
            model_select.set_options(model_options)

        except Exception:
            # Fallback to a basic option if loading fails
            model_select.set_options([("gpt-4.1 (openai)", "gpt-4.1")])

    @on(Button.Pressed, "#save-button")
    def save_settings(self) -> None:
        """Save the modified settings."""
        from code_puppy.config import (
            set_config_value,
            set_model_name,
            get_model_context_length,
        )

        try:
            # Get values from inputs
            puppy_name = self.query_one("#puppy-name-input", Input).value.strip()
            owner_name = self.query_one("#owner-name-input", Input).value.strip()
            selected_model = self.query_one("#model-select", Select).value
            yolo_mode = "true"  # Always set to true in TUI mode
            protected_tokens = self.query_one(
                "#protected-tokens-input", Input
            ).value.strip()
            compaction_threshold = self.query_one(
                "#compaction-threshold-input", Input
            ).value.strip()

            # Validate and save
            if puppy_name:
                set_config_value("puppy_name", puppy_name)
            if owner_name:
                set_config_value("owner_name", owner_name)

            # Save model selection
            if selected_model:
                set_model_name(selected_model)

            set_config_value("yolo_mode", yolo_mode)

            # Validate and save protected tokens
            if protected_tokens.isdigit():
                tokens_value = int(protected_tokens)
                model_context_length = get_model_context_length()
                max_protected_tokens = int(model_context_length * 0.75)

                if tokens_value >= 1000:  # Minimum validation
                    if tokens_value <= max_protected_tokens:  # Maximum validation
                        set_config_value("protected_token_count", protected_tokens)
                    else:
                        raise ValueError(
                            f"Protected tokens must not exceed 75% of model context length ({max_protected_tokens} tokens for current model)"
                        )
                else:
                    raise ValueError("Protected tokens must be at least 1000")
            elif protected_tokens:  # If not empty but not digit
                raise ValueError("Protected tokens must be a valid number")

            # Validate and save compaction threshold
            if compaction_threshold:
                try:
                    threshold_value = float(compaction_threshold)
                    if 0.8 <= threshold_value <= 0.95:  # Same bounds as config function
                        set_config_value("compaction_threshold", compaction_threshold)
                    else:
                        raise ValueError(
                            "Compaction threshold must be between 0.8 and 0.95"
                        )
                except ValueError as ve:
                    if "must be between" in str(ve):
                        raise ve
                    else:
                        raise ValueError(
                            "Compaction threshold must be a valid decimal number"
                        )

            # Save compaction strategy
            compaction_strategy = self.query_one(
                "#compaction-strategy-select", Select
            ).value
            if compaction_strategy in ["summarization", "truncation"]:
                set_config_value("compaction_strategy", compaction_strategy)

            # Return success message with model change info
            message = "Settings saved successfully!"
            if selected_model:
                message += f" Model switched to: {selected_model}"

            self.dismiss(
                {
                    "success": True,
                    "message": message,
                    "model_changed": bool(selected_model),
                }
            )

        except Exception as e:
            self.dismiss(
                {"success": False, "message": f"Error saving settings: {str(e)}"}
            )

    @on(Button.Pressed, "#cancel-button")
    def cancel_settings(self) -> None:
        """Cancel settings changes."""
        self.dismiss({"success": False, "message": "Settings cancelled"})

    def on_key(self, event) -> None:
        """Handle key events."""
        if event.key == "escape":
            self.cancel_settings()
