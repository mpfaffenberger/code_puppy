"""
MCP Install Wizard Screen - TUI interface for installing MCP servers.
"""

import json
import os

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Input, ListItem, ListView, Static, TextArea


class MCPInstallWizardScreen(ModalScreen):
    """Modal screen for installing MCP servers with full wizard support."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.selected_server = None
        self.env_vars = {}
        self.step = "search"  # search -> configure -> install -> custom_json
        self.search_counter = 0  # Counter to ensure unique IDs
        self.custom_json_mode = False  # Track if we're in custom JSON mode

    DEFAULT_CSS = """
    MCPInstallWizardScreen {
        align: center middle;
    }

    #wizard-container {
        width: 90%;
        max-width: 100;
        height: 80%;
        max-height: 40;
        background: $surface;
        border: solid $primary;
        padding: 1 2;
        layout: vertical;
    }

    #wizard-header {
        width: 100%;
        height: 3;
        text-align: center;
        color: $accent;
        margin-bottom: 1;
    }

    #search-container {
        width: 100%;
        height: auto;
        layout: vertical;
    }

    #search-input {
        width: 100%;
        margin-bottom: 1;
        border: solid $primary;
    }

    #results-list {
        width: 100%;
        height: 20;
        border: solid $primary;
        margin-bottom: 1;
    }

    #config-container {
        width: 100%;
        height: 1fr;
        layout: vertical;
    }

    #server-info {
        width: 100%;
        height: auto;
        max-height: 8;
        border: solid $success;
        padding: 1;
        margin-bottom: 1;
        background: $surface-lighten-1;
    }

    #env-vars-container {
        width: 100%;
        height: 1fr;
        layout: vertical;
        border: solid $warning;
        padding: 1;
        margin-bottom: 1;
        overflow-y: scroll;
    }

    #env-var-input {
        width: 100%;
        margin-bottom: 1;
        border: solid $primary;
    }

    #button-container {
        width: 100%;
        height: 4;
        layout: horizontal;
        align: center bottom;
    }

    #back-button, #next-button, #install-button, #cancel-button {
        width: auto;
        height: 3;
        margin: 0 1;
        min-width: 12;
    }

    .env-var-row {
        width: 100%;
        layout: horizontal;
        height: 3;
        margin-bottom: 1;
    }

    .env-var-label {
        width: 1fr;
        padding: 1 0;
    }

    .env-var-input {
        width: 2fr;
        border: solid $primary;
    }

    #custom-json-container {
        width: 100%;
        height: 1fr;
        layout: vertical;
        display: none;
        padding: 1;
    }

    #custom-json-header {
        width: 100%;
        height: 2;
        text-align: left;
        color: $warning;
        margin-bottom: 1;
    }

    #custom-name-input {
        width: 100%;
        margin-bottom: 1;
        border: solid $primary;
    }

    #custom-json-input {
        width: 100%;
        height: 1fr;
        border: solid $primary;
        margin-bottom: 1;
        background: $surface-darken-1;
    }

    #custom-json-button {
        width: auto;
        height: 3;
        margin: 0 1;
        min-width: 14;
    }
    """

    def compose(self) -> ComposeResult:
        """Create the wizard layout."""
        with Container(id="wizard-container"):
            yield Static("🔌 MCP Server Install Wizard", id="wizard-header")

            # Step 1: Search and select server
            with Container(id="search-container"):
                yield Input(
                    placeholder="Search MCP servers (e.g. 'github', 'postgres')...",
                    id="search-input",
                )
                yield ListView(id="results-list")

            # Step 2: Configure server (hidden initially)
            with Container(id="config-container"):
                yield Static("Server Configuration", id="config-header")
                yield Container(id="server-info")
                yield Container(id="env-vars-container")

            # Step 3: Custom JSON configuration (hidden initially)
            with Container(id="custom-json-container"):
                yield Static("📝 Custom JSON Configuration", id="custom-json-header")
                yield Input(
                    placeholder="Server name (e.g. 'my-sqlite-db')",
                    id="custom-name-input",
                )
                yield TextArea(id="custom-json-input")

            # Navigation buttons
            with Horizontal(id="button-container"):
                yield Button("Cancel", id="cancel-button", variant="default")
                yield Button("Back", id="back-button", variant="default")
                yield Button("Custom JSON", id="custom-json-button", variant="warning")
                yield Button("Next", id="next-button", variant="primary")
                yield Button("Install", id="install-button", variant="success")

    def on_mount(self) -> None:
        """Initialize the wizard."""
        self._show_search_step()
        self._load_popular_servers()

        # Focus the search input
        search_input = self.query_one("#search-input", Input)
        search_input.focus()

    def _show_search_step(self) -> None:
        """Show the search step."""
        self.step = "search"
        self.custom_json_mode = False
        self.query_one("#search-container").display = True
        self.query_one("#config-container").display = False
        self.query_one("#custom-json-container").display = False

        self.query_one("#back-button").display = False
        self.query_one("#custom-json-button").display = True
        self.query_one("#next-button").display = True
        self.query_one("#install-button").display = False

    def _show_config_step(self) -> None:
        """Show the configuration step."""
        self.step = "configure"
        self.custom_json_mode = False
        self.query_one("#search-container").display = False
        self.query_one("#config-container").display = True
        self.query_one("#custom-json-container").display = False

        self.query_one("#back-button").display = True
        self.query_one("#custom-json-button").display = False
        self.query_one("#next-button").display = False
        self.query_one("#install-button").display = True

        self._setup_server_config()

    def _show_custom_json_step(self) -> None:
        """Show the custom JSON configuration step."""
        self.step = "custom_json"
        self.custom_json_mode = True
        self.query_one("#search-container").display = False
        self.query_one("#config-container").display = False
        self.query_one("#custom-json-container").display = True

        self.query_one("#back-button").display = True
        self.query_one("#custom-json-button").display = False
        self.query_one("#next-button").display = False
        self.query_one("#install-button").display = True

        # Pre-populate with SQLite example
        name_input = self.query_one("#custom-name-input", Input)
        name_input.value = "my-sqlite-db"

        json_input = self.query_one("#custom-json-input", TextArea)
        json_input.text = """{
  "type": "stdio",
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-sqlite", "./database.db"],
  "timeout": 30
}"""

        # Focus the name input
        name_input.focus()

    def _load_popular_servers(self) -> None:
        """Load all available servers into the list."""
        self.search_counter += 1
        counter = self.search_counter

        try:
            from code_puppy.mcp.server_registry_catalog import catalog

            # Load ALL servers instead of just popular ones
            servers = catalog.servers

            results_list = self.query_one("#results-list", ListView)
            # Force clear by removing all children
            results_list.remove_children()

            if servers:
                # Sort servers to show popular and verified first
                sorted_servers = sorted(
                    servers,
                    key=lambda s: (not s.popular, not s.verified, s.display_name),
                )

                for i, server in enumerate(sorted_servers):
                    indicators = []
                    if server.verified:
                        indicators.append("✓")
                    if server.popular:
                        indicators.append("⭐")

                    display_name = f"{server.display_name} {''.join(indicators)}"
                    description = (
                        server.description[:60] + "..."
                        if len(server.description) > 60
                        else server.description
                    )

                    item_text = f"{display_name}\n[dim]{description}[/dim]"
                    # Use counter to ensure globally unique IDs
                    item = ListItem(Static(item_text), id=f"item-{counter}-{i}")
                    item.server_data = server
                    results_list.append(item)
            else:
                no_servers_item = ListItem(
                    Static("No servers found"), id=f"no-results-{counter}"
                )
                results_list.append(no_servers_item)

        except ImportError:
            results_list = self.query_one("#results-list", ListView)
            results_list.remove_children()
            error_item = ListItem(
                Static("[red]Server registry not available[/red]"),
                id=f"error-{counter}",
            )
            results_list.append(error_item)

    @on(Input.Changed, "#search-input")
    def on_search_changed(self, event: Input.Changed) -> None:
        """Handle search input changes."""
        query = event.value.strip()

        if not query:
            self._load_popular_servers()  # This now loads all servers
            return

        self.search_counter += 1
        counter = self.search_counter

        try:
            from code_puppy.mcp.server_registry_catalog import catalog

            servers = catalog.search(query)

            results_list = self.query_one("#results-list", ListView)
            # Force clear by removing all children
            results_list.remove_children()

            if servers:
                for i, server in enumerate(servers[:15]):  # Limit results
                    indicators = []
                    if server.verified:
                        indicators.append("✓")
                    if server.popular:
                        indicators.append("⭐")

                    display_name = f"{server.display_name} {''.join(indicators)}"
                    description = (
                        server.description[:60] + "..."
                        if len(server.description) > 60
                        else server.description
                    )

                    item_text = f"{display_name}\n[dim]{description}[/dim]"
                    # Use counter to ensure globally unique IDs
                    item = ListItem(Static(item_text), id=f"item-{counter}-{i}")
                    item.server_data = server
                    results_list.append(item)
            else:
                no_results_item = ListItem(
                    Static(f"No servers found for '{query}'"),
                    id=f"no-results-{counter}",
                )
                results_list.append(no_results_item)

        except ImportError:
            results_list = self.query_one("#results-list", ListView)
            results_list.remove_children()
            error_item = ListItem(
                Static("[red]Server registry not available[/red]"),
                id=f"error-{counter}",
            )
            results_list.append(error_item)

    @on(ListView.Selected, "#results-list")
    def on_server_selected(self, event: ListView.Selected) -> None:
        """Handle server selection."""
        if hasattr(event.item, "server_data"):
            self.selected_server = event.item.server_data

    @on(Button.Pressed, "#next-button")
    def on_next_clicked(self) -> None:
        """Handle next button click."""
        if self.step == "search":
            if self.selected_server:
                self._show_config_step()
            else:
                # Show error - no server selected
                pass

    @on(Button.Pressed, "#back-button")
    def on_back_clicked(self) -> None:
        """Handle back button click."""
        if self.step == "configure":
            self._show_search_step()
        elif self.step == "custom_json":
            self._show_search_step()

    @on(Button.Pressed, "#custom-json-button")
    def on_custom_json_clicked(self) -> None:
        """Handle custom JSON button click."""
        self._show_custom_json_step()

    @on(Button.Pressed, "#install-button")
    def on_install_clicked(self) -> None:
        """Handle install button click."""
        if self.step == "configure" and self.selected_server:
            self._install_server()
        elif self.step == "custom_json":
            self._install_custom_json()

    @on(Button.Pressed, "#cancel-button")
    def on_cancel_clicked(self) -> None:
        """Handle cancel button click."""
        self.dismiss({"success": False, "message": "Installation cancelled"})

    def _setup_server_config(self) -> None:
        """Setup the server configuration step."""
        if not self.selected_server:
            return

        # Show server info
        server_info = self.query_one("#server-info", Container)
        server_info.remove_children()

        info_text = f"""[bold]{self.selected_server.display_name}[/bold]
{self.selected_server.description}

[yellow]Category:[/yellow] {self.selected_server.category}
[yellow]Type:[/yellow] {getattr(self.selected_server, "type", "stdio")}"""

        # Show requirements summary
        requirements = self.selected_server.get_requirements()
        req_items = []
        if requirements.required_tools:
            req_items.append(f"Tools: {', '.join(requirements.required_tools)}")
        if requirements.environment_vars:
            req_items.append(f"Env vars: {len(requirements.environment_vars)}")
        if requirements.command_line_args:
            req_items.append(f"Config args: {len(requirements.command_line_args)}")

        if req_items:
            info_text += f"\n[yellow]Requirements:[/yellow] {' | '.join(req_items)}"

        server_info.mount(Static(info_text))

        # Setup configuration requirements
        config_container = self.query_one("#env-vars-container", Container)
        config_container.remove_children()
        config_container.mount(Static("[bold]Server Configuration:[/bold]"))

        # Add server name input
        config_container.mount(Static("\n[bold blue]Server Name:[/bold blue]"))
        name_row = Horizontal(classes="env-var-row")
        config_container.mount(name_row)
        name_row.mount(Static("🏷️ Custom name:", classes="env-var-label"))
        name_input = Input(
            placeholder=f"Default: {self.selected_server.name}",
            value=self.selected_server.name,
            classes="env-var-input",
            id="server-name-input",
        )
        name_row.mount(name_input)

        try:
            # Check system requirements first
            self._setup_system_requirements(config_container)

            # Setup environment variables
            self._setup_environment_variables(config_container)

            # Setup command line arguments
            self._setup_command_line_args(config_container)

            # Show package dependencies info
            self._setup_package_dependencies(config_container)

        except Exception as e:
            config_container.mount(
                Static(f"[red]Error loading configuration: {e}[/red]")
            )

    def _setup_system_requirements(self, parent: Container) -> None:
        """Setup system requirements validation."""
        required_tools = self.selected_server.get_required_tools()

        if not required_tools:
            return

        parent.mount(Static("\n[bold cyan]System Tools:[/bold cyan]"))

        # Import here to avoid circular imports
        from code_puppy.mcp.system_tools import detector

        tool_status = detector.detect_tools(required_tools)

        for tool_name, tool_info in tool_status.items():
            if tool_info.available:
                status_text = f"✅ {tool_name}"
                if tool_info.version:
                    status_text += f" ({tool_info.version})"
                parent.mount(Static(status_text))
            else:
                status_text = f"❌ {tool_name} - {tool_info.error or 'Not found'}"
                parent.mount(Static(f"[red]{status_text}[/red]"))

                # Show installation suggestions
                suggestions = detector.get_installation_suggestions(tool_name)
                if suggestions:
                    parent.mount(Static(f"[dim]   Install: {suggestions[0]}[/dim]"))

    def _setup_environment_variables(self, parent: Container) -> None:
        """Setup environment variables inputs."""
        env_vars = self.selected_server.get_environment_vars()

        if not env_vars:
            return

        parent.mount(Static("\n[bold yellow]Environment Variables:[/bold yellow]"))

        for var in env_vars:
            # Check if already set
            import os

            current_value = os.environ.get(var, "")

            row_container = Horizontal(classes="env-var-row")
            parent.mount(row_container)

            status_indicator = "✅" if current_value else "📝"
            row_container.mount(
                Static(f"{status_indicator} {var}:", classes="env-var-label")
            )

            env_input = Input(
                placeholder=f"Enter {var} value..."
                if not current_value
                else "Already set",
                value=current_value,
                classes="env-var-input",
                id=f"env-{var}",
            )
            row_container.mount(env_input)

    def _setup_command_line_args(self, parent: Container) -> None:
        """Setup command line arguments inputs."""
        cmd_args = self.selected_server.get_command_line_args()

        if not cmd_args:
            return

        parent.mount(Static("\n[bold green]Command Line Arguments:[/bold green]"))

        for arg_config in cmd_args:
            name = arg_config.get("name", "")
            prompt = arg_config.get("prompt", name)
            default = arg_config.get("default", "")
            required = arg_config.get("required", True)

            row_container = Horizontal(classes="env-var-row")
            parent.mount(row_container)

            indicator = "⚡" if required else "🔧"
            label_text = f"{indicator} {prompt}:"
            if not required:
                label_text += " (optional)"

            row_container.mount(Static(label_text, classes="env-var-label"))

            arg_input = Input(
                placeholder=f"Default: {default}" if default else f"Enter {name}...",
                value=default,
                classes="env-var-input",
                id=f"arg-{name}",
            )
            row_container.mount(arg_input)

    def _setup_package_dependencies(self, parent: Container) -> None:
        """Setup package dependencies information."""
        packages = self.selected_server.get_package_dependencies()

        if not packages:
            return

        parent.mount(Static("\n[bold magenta]Package Dependencies:[/bold magenta]"))

        # Import here to avoid circular imports
        from code_puppy.mcp.system_tools import detector

        package_status = detector.check_package_dependencies(packages)

        for package, available in package_status.items():
            if available:
                parent.mount(Static(f"✅ {package} (installed)"))
            else:
                parent.mount(
                    Static(
                        f"[yellow]📦 {package} (will be installed automatically)[/yellow]"
                    )
                )

    def _install_server(self) -> None:
        """Install the selected server with configuration."""
        if not self.selected_server:
            return

        try:
            # Collect configuration inputs
            env_vars = {}
            cmd_args = {}
            server_name = self.selected_server.name  # Default fallback

            all_inputs = self.query(Input)

            for input_widget in all_inputs:
                if input_widget.id == "server-name-input":
                    custom_name = input_widget.value.strip()
                    if custom_name:
                        server_name = custom_name
                elif input_widget.id and input_widget.id.startswith("env-"):
                    var_name = input_widget.id[4:]  # Remove "env-" prefix
                    value = input_widget.value.strip()
                    if value:
                        env_vars[var_name] = value
                elif input_widget.id and input_widget.id.startswith("arg-"):
                    arg_name = input_widget.id[4:]  # Remove "arg-" prefix
                    value = input_widget.value.strip()
                    if value:
                        cmd_args[arg_name] = value

            # Set environment variables in the current environment
            for var, value in env_vars.items():
                os.environ[var] = value

            # Get server config with command line argument overrides
            config_dict = self.selected_server.to_server_config(server_name, **cmd_args)

            # Update the config with actual environment variable values
            if "env" in config_dict:
                for env_key, env_value in config_dict["env"].items():
                    # If it's a placeholder like $GITHUB_TOKEN, replace with actual value
                    if env_value.startswith("$"):
                        var_name = env_value[1:]  # Remove the $
                        if var_name in env_vars:
                            config_dict["env"][env_key] = env_vars[var_name]

            # Create and register the server
            from code_puppy.mcp import ServerConfig
            from code_puppy.mcp.manager import get_mcp_manager

            server_config = ServerConfig(
                id=server_name,
                name=server_name,
                type=config_dict.pop("type"),
                enabled=True,
                config=config_dict,
            )

            manager = get_mcp_manager()
            server_id = manager.register_server(server_config)

            if server_id:
                # Save to mcp_servers.json
                from code_puppy.config import MCP_SERVERS_FILE

                if os.path.exists(MCP_SERVERS_FILE):
                    with open(MCP_SERVERS_FILE, "r") as f:
                        data = json.load(f)
                        servers = data.get("mcp_servers", {})
                else:
                    servers = {}
                    data = {"mcp_servers": servers}

                servers[server_name] = config_dict
                servers[server_name]["type"] = server_config.type

                os.makedirs(os.path.dirname(MCP_SERVERS_FILE), exist_ok=True)
                with open(MCP_SERVERS_FILE, "w") as f:
                    json.dump(data, f, indent=2)

                # Reload MCP servers
                from code_puppy.agent import reload_mcp_servers

                reload_mcp_servers()

                self.dismiss(
                    {
                        "success": True,
                        "message": f"Successfully installed '{server_name}' from {self.selected_server.display_name}",
                        "server_name": server_name,
                    }
                )
            else:
                self.dismiss({"success": False, "message": "Failed to register server"})

        except Exception as e:
            self.dismiss(
                {"success": False, "message": f"Installation failed: {str(e)}"}
            )

    def _install_custom_json(self) -> None:
        """Install server from custom JSON configuration."""
        try:
            name_input = self.query_one("#custom-name-input", Input)
            json_input = self.query_one("#custom-json-input", TextArea)

            server_name = name_input.value.strip()
            json_text = json_input.text.strip()

            if not server_name:
                # Show error - need a name
                return

            if not json_text:
                # Show error - need JSON config
                return

            # Parse JSON
            try:
                config_dict = json.loads(json_text)
            except json.JSONDecodeError:
                # Show error - invalid JSON
                return

            # Validate required fields
            if "type" not in config_dict:
                # Show error - missing type
                return

            # Extract type and create server config
            server_type = config_dict.pop("type")

            # Create and register the server
            from code_puppy.mcp import ServerConfig
            from code_puppy.mcp.manager import get_mcp_manager

            server_config = ServerConfig(
                id=server_name,
                name=server_name,
                type=server_type,
                enabled=True,
                config=config_dict,
            )

            manager = get_mcp_manager()
            server_id = manager.register_server(server_config)

            if server_id:
                # Save to mcp_servers.json
                from code_puppy.config import MCP_SERVERS_FILE

                if os.path.exists(MCP_SERVERS_FILE):
                    with open(MCP_SERVERS_FILE, "r") as f:
                        data = json.load(f)
                        servers = data.get("mcp_servers", {})
                else:
                    servers = {}
                    data = {"mcp_servers": servers}

                # Add the full config including type
                full_config = config_dict.copy()
                full_config["type"] = server_type
                servers[server_name] = full_config

                os.makedirs(os.path.dirname(MCP_SERVERS_FILE), exist_ok=True)
                with open(MCP_SERVERS_FILE, "w") as f:
                    json.dump(data, f, indent=2)

                # Reload MCP servers
                from code_puppy.agent import reload_mcp_servers

                reload_mcp_servers()

                self.dismiss(
                    {
                        "success": True,
                        "message": f"Successfully installed custom server '{server_name}'",
                        "server_name": server_name,
                    }
                )
            else:
                self.dismiss(
                    {"success": False, "message": "Failed to register custom server"}
                )

        except Exception as e:
            self.dismiss(
                {"success": False, "message": f"Installation failed: {str(e)}"}
            )

    def on_key(self, event) -> None:
        """Handle key events."""
        if event.key == "escape":
            self.on_cancel_clicked()
