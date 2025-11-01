"""
Comprehensive settings configuration modal with tabbed interface.
"""

import os
from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Input,
    Label,
    Select,
    Static,
    Switch,
    TabbedContent,
    TabPane,
)


class SettingsScreen(ModalScreen):
    """Comprehensive settings configuration screen with tabbed interface."""

    DEFAULT_CSS = """
    SettingsScreen {
        align: center middle;
    }

    #settings-dialog {
        width: 110;
        height: 40;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    #settings-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin: 0 0 1 0;
    }

    #settings-tabs {
        height: 1fr;
        margin: 0 0 1 0;
    }

    .setting-row {
        layout: horizontal;
        height: auto;
        margin: 0 0 1 0;
        align: left top;
    }

    .setting-label {
        width: 35;
        text-align: left;
        padding: 1 1 0 0;
        content-align: left top;
    }

    .setting-input {
        width: 1fr;
        margin: 0 0 0 1;
    }

    .setting-description {
        color: $text-muted;
        text-style: italic;
        width: 1fr;
        margin: 0 0 1 0;
        height: auto;
    }

    /* Special margin for descriptions after input fields */
    .input-description {
        margin: 0 0 0 36;
    }

    .section-header {
        text-style: bold;
        color: $accent;
        margin: 1 0 0 0;
    }

    Input {
        width: 100%;
    }

    Select {
        width: 100%;
    }

    Switch {
        width: 4;
        height: 1;
        min-width: 4;
        padding: 0;
        margin: 0;
        border: none !important;
        background: transparent;
    }

    Switch:focus {
        border: none !important;
    }

    Switch:hover {
        border: none !important;
    }

    Switch > * {
        border: none !important;
    }

    /* Compact layout for switch rows */
    .switch-row {
        layout: horizontal;
        height: auto;
        margin: 0 0 1 0;
        align: left middle;
    }

    .switch-row .setting-label {
        width: 35;
        margin: 0 1 0 0;
        padding: 0;
        height: auto;
        content-align: left middle;
    }

    .switch-row Switch {
        width: 4;
        margin: 0 2 0 0;
        height: 1;
        padding: 0;
    }

    .switch-row .setting-description {
        width: 1fr;
        margin: 0;
        padding: 0;
        height: auto;
        color: $text-muted;
        text-style: italic;
    }

    #settings-buttons {
        layout: horizontal;
        height: 3;
        align: center middle;
        margin: 1 0 0 0;
    }

    #save-button, #cancel-button {
        margin: 0 1;
        min-width: 12;
    }

    TabPane {
        padding: 1 2;
    }

    #agent-pinning-container {
        margin: 1 0;
    }

    .agent-pin-row {
        layout: horizontal;
        height: auto;
        margin: 0 0 1 0;
        align: left middle;
    }

    .agent-pin-row .setting-label {
        width: 35;
        margin: 0 1 0 0;
        padding: 0;
        height: auto;
    }

    .agent-pin-row Select {
        width: 1fr;
        margin: 0;
        padding: 0 !important;
        border: none !important;
        height: 1;
        min-height: 1;
    }

    .agent-pin-row Select:focus {
        border: none !important;
    }

    .agent-pin-row Select:hover {
        border: none !important;
    }

    .agent-pin-row Select > * {
        border: none !important;
        padding: 0 !important;
    }

    .status-check {
        color: $success;
    }

    .status-error {
        color: $error;
    }

    .tab-scroll {
        height: 1fr;
        overflow: auto;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.settings_data = {}

    def compose(self) -> ComposeResult:
        with Container(id="settings-dialog"):
            yield Label("⚙️  Code Puppy Configuration", id="settings-title")
            with TabbedContent(id="settings-tabs"):
                # Tab 1: General
                with TabPane("General", id="general"):
                    with VerticalScroll(classes="tab-scroll"):
                        with Container(classes="setting-row"):
                            yield Label("Puppy's Name:", classes="setting-label")
                            yield Input(id="puppy-name-input", classes="setting-input")
                        yield Static(
                            "Your puppy's name, shown in the status bar.",
                            classes="input-description",
                        )

                        with Container(classes="setting-row"):
                            yield Label("Owner's Name:", classes="setting-label")
                            yield Input(id="owner-name-input", classes="setting-input")
                        yield Static(
                            "Your name, for a personal touch.",
                            classes="input-description",
                        )

                        with Container(classes="switch-row"):
                            yield Label("YOLO Mode (auto-confirm):", classes="setting-label")
                            yield Switch(id="yolo-mode-switch", classes="setting-input")
                            yield Static(
                                "If enabled, agent commands execute without a confirmation prompt.",
                                classes="setting-description",
                            )

                        with Container(classes="switch-row"):
                            yield Label("Allow Agent Recursion:", classes="setting-label")
                            yield Switch(id="allow-recursion-switch", classes="setting-input")
                            yield Static(
                                "Permits agents to call other agents to complete tasks.",
                                classes="setting-description",
                            )

                # Tab 2: Models & AI
                with TabPane("Models & AI", id="models"):
                    with VerticalScroll(classes="tab-scroll"):
                        with Container(classes="setting-row"):
                            yield Label("Default Model:", classes="setting-label")
                            yield Select([], id="model-select", classes="setting-input")
                        yield Static(
                            "The primary model used for code generation.",
                            classes="input-description",
                        )

                        with Container(classes="setting-row"):
                            yield Label("Vision Model (VQA):", classes="setting-label")
                            yield Select([], id="vqa-model-select", classes="setting-input")
                        yield Static(
                            "Model used for vision and image-related tasks.",
                            classes="input-description",
                        )

                        with Container(classes="setting-row"):
                            yield Label("GPT-5 Reasoning Effort:", classes="setting-label")
                            yield Select(
                                [
                                    ("Low", "low"),
                                    ("Medium", "medium"),
                                    ("High", "high"),
                                ],
                                id="reasoning-effort-select",
                                classes="setting-input",
                            )
                        yield Static(
                            "Reasoning effort for GPT-5 models (only applies to GPT-5).",
                            classes="input-description",
                        )

                # Tab 3: History & Context
                with TabPane("History & Context", id="history"):
                    with VerticalScroll(classes="tab-scroll"):
                        with Container(classes="setting-row"):
                            yield Label("Compaction Strategy:", classes="setting-label")
                            yield Select(
                                [
                                    ("Summarization", "summarization"),
                                    ("Truncation", "truncation"),
                                ],
                                id="compaction-strategy-select",
                                classes="setting-input",
                            )
                        yield Static(
                            "How to compress context when it gets too large.",
                            classes="input-description",
                        )

                        with Container(classes="setting-row"):
                            yield Label("Compaction Threshold:", classes="setting-label")
                            yield Input(
                                id="compaction-threshold-input",
                                classes="setting-input",
                                placeholder="0.85",
                            )
                        yield Static(
                            "Percentage of context usage that triggers compaction (0.80-0.95).",
                            classes="input-description",
                        )

                        with Container(classes="setting-row"):
                            yield Label("Protected Recent Tokens:", classes="setting-label")
                            yield Input(
                                id="protected-tokens-input",
                                classes="setting-input",
                                placeholder="50000",
                            )
                        yield Static(
                            "Number of recent tokens to preserve during compaction.",
                            classes="input-description",
                        )

                        with Container(classes="switch-row"):
                            yield Label("Auto-Save Session:", classes="setting-label")
                            yield Switch(id="auto-save-switch", classes="setting-input")
                            yield Static(
                                "Automatically save the session after each LLM response.",
                                classes="setting-description",
                            )

                        with Container(classes="setting-row"):
                            yield Label("Max Autosaved Sessions:", classes="setting-label")
                            yield Input(
                                id="max-autosaves-input",
                                classes="setting-input",
                                placeholder="20",
                            )
                        yield Static(
                            "Maximum number of autosaves to keep (0 for unlimited).",
                            classes="input-description",
                        )

                # Tab 4: Appearance
                with TabPane("Appearance", id="appearance"):
                    with VerticalScroll(classes="tab-scroll"):
                        with Container(classes="setting-row"):
                            yield Label("Diff Display Style:", classes="setting-label")
                            yield Select(
                                [
                                    ("Plain Text", "text"),
                                    ("Highlighted", "highlighted"),
                                ],
                                id="diff-style-select",
                                classes="setting-input",
                            )
                        yield Static(
                            "Visual style for diff output.",
                            classes="input-description",
                        )

                        with Container(classes="setting-row"):
                            yield Label("Diff Addition Color:", classes="setting-label")
                            yield Input(
                                id="diff-addition-color-input",
                                classes="setting-input",
                                placeholder="sea_green1",
                            )
                        yield Static(
                            "Rich color name or hex code for additions (e.g., 'sea_green1').",
                            classes="input-description",
                        )

                        with Container(classes="setting-row"):
                            yield Label("Diff Deletion Color:", classes="setting-label")
                            yield Input(
                                id="diff-deletion-color-input",
                                classes="setting-input",
                                placeholder="orange1",
                            )
                        yield Static(
                            "Rich color name or hex code for deletions (e.g., 'orange1').",
                            classes="input-description",
                        )

                        with Container(classes="setting-row"):
                            yield Label("Diff Context Lines:", classes="setting-label")
                            yield Input(
                                id="diff-context-lines-input",
                                classes="setting-input",
                                placeholder="6",
                            )
                        yield Static(
                            "Number of unchanged lines to show around a diff (0-50).",
                            classes="input-description",
                        )

                # Tab 5: Agents & Integrations
                with TabPane("Agents & Integrations", id="integrations"):
                    with VerticalScroll(classes="tab-scroll"):
                        yield Label("Agent Model Pinning", classes="section-header")
                        yield Static(
                            "Pin specific models to individual agents. Select '(default)' to use the global model.",
                            classes="setting-description",
                        )
                        yield Container(id="agent-pinning-container")

                        yield Label("MCP & DBOS", classes="section-header")

                        with Container(classes="switch-row"):
                            yield Label("Disable All MCP Servers:", classes="setting-label")
                            yield Switch(id="disable-mcp-switch", classes="setting-input")
                            yield Static(
                                "Globally enable or disable the Model Context Protocol.",
                                classes="setting-description",
                            )

                        with Container(classes="switch-row"):
                            yield Label("Enable DBOS:", classes="setting-label")
                            yield Switch(id="enable-dbos-switch", classes="setting-input")
                            yield Static(
                                "Use DBOS for durable, resumable agent workflows.",
                                classes="setting-description",
                            )

                # Tab 6: API Keys & Status (Read-Only)
                with TabPane("API Keys & Status", id="status"):
                    with VerticalScroll(classes="tab-scroll"):
                        yield Static(
                            "Environment Variable Status (Read-Only)",
                            classes="section-header",
                        )
                        yield Container(id="api-status-container")

            with Horizontal(id="settings-buttons"):
                yield Button("Save & Close", id="save-button", variant="primary")
                yield Button("Cancel", id="cancel-button")

    def on_mount(self) -> None:
        """Load current settings when the screen mounts."""
        from code_puppy.config import (
            get_allow_recursion,
            get_auto_save_session,
            get_compaction_strategy,
            get_compaction_threshold,
            get_diff_addition_color,
            get_diff_context_lines,
            get_diff_deletion_color,
            get_diff_highlight_style,
            get_global_model_name,
            get_max_saved_sessions,
            get_mcp_disabled,
            get_openai_reasoning_effort,
            get_owner_name,
            get_protected_token_count,
            get_puppy_name,
            get_use_dbos,
            get_vqa_model_name,
            get_yolo_mode,
        )

        # Tab 1: General
        self.query_one("#puppy-name-input", Input).value = get_puppy_name() or ""
        self.query_one("#owner-name-input", Input).value = get_owner_name() or ""
        self.query_one("#yolo-mode-switch", Switch).value = get_yolo_mode()
        self.query_one("#allow-recursion-switch", Switch).value = get_allow_recursion()

        # Tab 2: Models & AI
        self.load_model_options()
        self.query_one("#model-select", Select).value = get_global_model_name()
        self.query_one("#vqa-model-select", Select).value = get_vqa_model_name()
        self.query_one("#reasoning-effort-select", Select).value = (
            get_openai_reasoning_effort()
        )

        # Tab 3: History & Context
        self.query_one("#compaction-strategy-select", Select).value = (
            get_compaction_strategy()
        )
        self.query_one("#compaction-threshold-input", Input).value = str(
            get_compaction_threshold()
        )
        self.query_one("#protected-tokens-input", Input).value = str(
            get_protected_token_count()
        )
        self.query_one("#auto-save-switch", Switch).value = get_auto_save_session()
        self.query_one("#max-autosaves-input", Input).value = str(
            get_max_saved_sessions()
        )

        # Tab 4: Appearance
        self.query_one("#diff-style-select", Select).value = get_diff_highlight_style()
        self.query_one("#diff-addition-color-input", Input).value = (
            get_diff_addition_color()
        )
        self.query_one("#diff-deletion-color-input", Input).value = (
            get_diff_deletion_color()
        )
        self.query_one("#diff-context-lines-input", Input).value = str(
            get_diff_context_lines()
        )

        # Tab 5: Agents & Integrations
        self.load_agent_pinning_table()
        self.query_one("#disable-mcp-switch", Switch).value = get_mcp_disabled()
        self.query_one("#enable-dbos-switch", Switch).value = get_use_dbos()

        # Tab 6: API Keys & Status
        self.load_api_status()

    def load_model_options(self):
        """Load available models into the model select widgets."""
        try:
            from code_puppy.model_factory import ModelFactory

            models_data = ModelFactory.load_config()

            # Create options as (display_name, model_name) tuples
            model_options = []
            vqa_options = []

            for model_name, model_config in models_data.items():
                model_type = model_config.get("type", "unknown")
                display_name = f"{model_name} ({model_type})"
                model_options.append((display_name, model_name))

                # Add to VQA options if it supports vision
                if model_config.get("supports_vision") or model_config.get(
                    "supports_vqa"
                ):
                    vqa_options.append((display_name, model_name))

            # Set options on select widgets
            self.query_one("#model-select", Select).set_options(model_options)

            # If no VQA-specific models, use all models
            if not vqa_options:
                vqa_options = model_options

            self.query_one("#vqa-model-select", Select).set_options(vqa_options)

        except Exception:
            # Fallback to basic options if loading fails
            fallback = [("gpt-5 (openai)", "gpt-5")]
            self.query_one("#model-select", Select).set_options(fallback)
            self.query_one("#vqa-model-select", Select).set_options(fallback)

    def load_agent_pinning_table(self):
        """Load agent model pinning dropdowns."""
        from code_puppy.agents import get_available_agents
        from code_puppy.config import get_agent_pinned_model
        from code_puppy.model_factory import ModelFactory

        container = self.query_one("#agent-pinning-container")

        # Get all available agents
        agents = get_available_agents()
        models_data = ModelFactory.load_config()

        # Create model options with "(default)" as first option
        model_options = [("(default)", "")]
        for model_name, model_config in models_data.items():
            model_type = model_config.get("type", "unknown")
            display_name = f"{model_name} ({model_type})"
            model_options.append((display_name, model_name))

        # Add a row for each agent with a dropdown
        for agent_name, display_name in agents.items():
            pinned_model = get_agent_pinned_model(agent_name) or ""

            # Create a horizontal container for this agent row
            agent_row = Container(classes="agent-pin-row")

            # Mount the row to the container FIRST
            container.mount(agent_row)

            # Now add children to the mounted row
            label = Label(f"{display_name}:", classes="setting-label")
            agent_row.mount(label)

            # Create Select widget with unique ID on the right
            select_id = f"agent-pin-{agent_name}"
            agent_select = Select(model_options, id=select_id, value=pinned_model)
            agent_row.mount(agent_select)

    def load_api_status(self):
        """Load and display API key status."""
        api_keys = {
            "OPENAI_API_KEY": "Required for OpenAI GPT models",
            "GEMINI_API_KEY": "Required for Google Gemini models",
            "ANTHROPIC_API_KEY": "Required for Anthropic Claude models",
            "CEREBRAS_API_KEY": "Required for Cerebras models",
            "SYN_API_KEY": "Required for Synthetic provider models",
            "AZURE_OPENAI_API_KEY": "Required for Azure OpenAI",
            "AZURE_OPENAI_ENDPOINT": "Required for Azure OpenAI endpoint",
        }

        container = self.query_one("#api-status-container")

        for key_name, description in api_keys.items():
            key_value = os.getenv(key_name)
            if key_value:
                status_text = f"[green]✔️  {key_name}[/green]: Set"
            else:
                status_text = f"[red]❌  {key_name}[/red]: Not Set"

            with container.app.batch_update():
                container.mount(Static(status_text))
                container.mount(Static(f"   [dim]{description}[/dim]"))

    @on(Button.Pressed, "#save-button")
    def save_settings(self) -> None:
        """Save the modified settings."""
        from code_puppy.config import (
            get_model_context_length,
            set_auto_save_session,
            set_config_value,
            set_diff_addition_color,
            set_diff_deletion_color,
            set_diff_highlight_style,
            set_enable_dbos,
            set_http2,
            set_max_saved_sessions,
            set_model_name,
            set_openai_reasoning_effort,
            set_vqa_model_name,
        )

        try:
            # Tab 1: General
            puppy_name = self.query_one("#puppy-name-input", Input).value.strip()
            owner_name = self.query_one("#owner-name-input", Input).value.strip()
            yolo_mode = self.query_one("#yolo-mode-switch", Switch).value
            allow_recursion = self.query_one("#allow-recursion-switch", Switch).value

            if puppy_name:
                set_config_value("puppy_name", puppy_name)
            if owner_name:
                set_config_value("owner_name", owner_name)
            set_config_value("yolo_mode", "true" if yolo_mode else "false")
            set_config_value("allow_recursion", "true" if allow_recursion else "false")

            # Tab 2: Models & AI
            selected_model = self.query_one("#model-select", Select).value
            selected_vqa_model = self.query_one("#vqa-model-select", Select).value
            reasoning_effort = self.query_one("#reasoning-effort-select", Select).value

            model_changed = False
            if selected_model:
                set_model_name(selected_model)
                model_changed = True
            if selected_vqa_model:
                set_vqa_model_name(selected_vqa_model)
            set_openai_reasoning_effort(reasoning_effort)

            # Tab 3: History & Context
            compaction_strategy = self.query_one(
                "#compaction-strategy-select", Select
            ).value
            compaction_threshold = self.query_one(
                "#compaction-threshold-input", Input
            ).value.strip()
            protected_tokens = self.query_one(
                "#protected-tokens-input", Input
            ).value.strip()
            auto_save = self.query_one("#auto-save-switch", Switch).value
            max_autosaves = self.query_one("#max-autosaves-input", Input).value.strip()

            if compaction_strategy in ["summarization", "truncation"]:
                set_config_value("compaction_strategy", compaction_strategy)

            if compaction_threshold:
                threshold_value = float(compaction_threshold)
                if 0.8 <= threshold_value <= 0.95:
                    set_config_value("compaction_threshold", compaction_threshold)
                else:
                    raise ValueError(
                        "Compaction threshold must be between 0.8 and 0.95"
                    )

            if protected_tokens.isdigit():
                tokens_value = int(protected_tokens)
                model_context_length = get_model_context_length()
                max_protected_tokens = int(model_context_length * 0.75)

                if 1000 <= tokens_value <= max_protected_tokens:
                    set_config_value("protected_token_count", protected_tokens)
                else:
                    raise ValueError(
                        f"Protected tokens must be between 1000 and {max_protected_tokens}"
                    )

            set_auto_save_session(auto_save)

            if max_autosaves.isdigit():
                set_max_saved_sessions(int(max_autosaves))

            # Tab 4: Appearance
            diff_style = self.query_one("#diff-style-select", Select).value
            diff_addition_color = self.query_one(
                "#diff-addition-color-input", Input
            ).value.strip()
            diff_deletion_color = self.query_one(
                "#diff-deletion-color-input", Input
            ).value.strip()
            diff_context_lines = self.query_one(
                "#diff-context-lines-input", Input
            ).value.strip()

            if diff_style:
                set_diff_highlight_style(diff_style)
            if diff_addition_color:
                set_diff_addition_color(diff_addition_color)
            if diff_deletion_color:
                set_diff_deletion_color(diff_deletion_color)
            if diff_context_lines.isdigit():
                lines_value = int(diff_context_lines)
                if 0 <= lines_value <= 50:
                    set_config_value("diff_context_lines", diff_context_lines)
                else:
                    raise ValueError("Diff context lines must be between 0 and 50")

            # Tab 5: Agents & Integrations
            # Save agent model pinning
            from code_puppy.agents import get_available_agents
            from code_puppy.config import set_agent_pinned_model

            agents = get_available_agents()
            for agent_name in agents.keys():
                select_id = f"agent-pin-{agent_name}"
                try:
                    agent_select = self.query_one(f"#{select_id}", Select)
                    pinned_model = agent_select.value
                    # Save the pinned model (empty string means use default)
                    set_agent_pinned_model(agent_name, pinned_model)
                except Exception:
                    # Skip if widget not found
                    pass

            disable_mcp = self.query_one("#disable-mcp-switch", Switch).value
            enable_dbos = self.query_one("#enable-dbos-switch", Switch).value

            set_config_value("disable_mcp", "true" if disable_mcp else "false")
            set_enable_dbos(enable_dbos)

            # Reload agent if model changed
            if model_changed:
                try:
                    from code_puppy.agents import get_current_agent

                    current_agent = get_current_agent()
                    current_agent.reload_code_generation_agent()
                except Exception:
                    pass

            # Return success message
            message = "✅ Settings saved successfully!"
            if model_changed:
                message += f" Model switched to: {selected_model}"

            self.dismiss(
                {
                    "success": True,
                    "message": message,
                    "model_changed": model_changed,
                }
            )

        except Exception as e:
            self.dismiss(
                {"success": False, "message": f"❌ Error saving settings: {str(e)}"}
            )

    @on(Button.Pressed, "#cancel-button")
    def cancel_settings(self) -> None:
        """Cancel settings changes."""
        self.dismiss({"success": False, "message": "Settings cancelled"})

    def on_key(self, event) -> None:
        """Handle key events."""
        if event.key == "escape":
            self.cancel_settings()
