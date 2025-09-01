"""
MCP Install Wizard Screen - TUI interface for installing MCP servers.
"""

import json
import os
from typing import Dict, List, Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button, 
    Input, 
    Label, 
    ListItem, 
    ListView, 
    Static, 
    Select,
    TextArea
)

from code_puppy.messaging import emit_info


class MCPInstallWizardScreen(ModalScreen):
    """Modal screen for installing MCP servers with full wizard support."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.selected_server = None
        self.env_vars = {}
        self.step = "search"  # search -> configure -> install
        self.search_counter = 0  # Counter to ensure unique IDs

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
    """

    def compose(self) -> ComposeResult:
        """Create the wizard layout."""
        with Container(id="wizard-container"):
            yield Static("🔌 MCP Server Install Wizard", id="wizard-header")
            
            # Step 1: Search and select server
            with Container(id="search-container"):
                yield Input(placeholder="Search MCP servers (e.g. 'github', 'postgres')...", id="search-input")
                yield ListView(id="results-list")
            
            # Step 2: Configure server (hidden initially)
            with Container(id="config-container"):
                yield Static("Server Configuration", id="config-header")
                yield Container(id="server-info")
                yield Container(id="env-vars-container")
            
            # Navigation buttons
            with Horizontal(id="button-container"):
                yield Button("Cancel", id="cancel-button", variant="default")
                yield Button("Back", id="back-button", variant="default")
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
        self.query_one("#search-container").display = True
        self.query_one("#config-container").display = False
        
        self.query_one("#back-button").display = False
        self.query_one("#next-button").display = True
        self.query_one("#install-button").display = False

    def _show_config_step(self) -> None:
        """Show the configuration step."""
        self.step = "configure"
        self.query_one("#search-container").display = False
        self.query_one("#config-container").display = True
        
        self.query_one("#back-button").display = True
        self.query_one("#next-button").display = False
        self.query_one("#install-button").display = True
        
        self._setup_server_config()

    def _load_popular_servers(self) -> None:
        """Load popular servers into the list."""
        self.search_counter += 1
        counter = self.search_counter
        
        try:
            from code_puppy.mcp.server_registry_catalog import catalog
            servers = catalog.get_popular(10)
            
            results_list = self.query_one("#results-list", ListView)
            # Force clear by removing all children
            results_list.remove_children()
            
            if servers:
                for i, server in enumerate(servers):
                    indicators = []
                    if server.verified:
                        indicators.append("✓")
                    if server.popular:
                        indicators.append("⭐")
                    
                    display_name = f"{server.display_name} {''.join(indicators)}"
                    description = server.description[:60] + "..." if len(server.description) > 60 else server.description
                    
                    item_text = f"{display_name}\n[dim]{description}[/dim]"
                    # Use counter to ensure globally unique IDs
                    item = ListItem(Static(item_text), id=f"item-{counter}-{i}")
                    item.server_data = server
                    results_list.append(item)
            else:
                no_servers_item = ListItem(Static("No servers found"), id=f"no-results-{counter}")
                results_list.append(no_servers_item)
                
        except ImportError:
            results_list = self.query_one("#results-list", ListView)
            results_list.remove_children()
            error_item = ListItem(Static("[red]Server registry not available[/red]"), id=f"error-{counter}")
            results_list.append(error_item)

    @on(Input.Changed, "#search-input")
    def on_search_changed(self, event: Input.Changed) -> None:
        """Handle search input changes."""
        query = event.value.strip()
        
        if not query:
            self._load_popular_servers()
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
                    description = server.description[:60] + "..." if len(server.description) > 60 else server.description
                    
                    item_text = f"{display_name}\n[dim]{description}[/dim]"
                    # Use counter to ensure globally unique IDs
                    item = ListItem(Static(item_text), id=f"item-{counter}-{i}")
                    item.server_data = server
                    results_list.append(item)
            else:
                no_results_item = ListItem(Static(f"No servers found for '{query}'"), id=f"no-results-{counter}")
                results_list.append(no_results_item)
                
        except ImportError:
            results_list = self.query_one("#results-list", ListView)
            results_list.remove_children()
            error_item = ListItem(Static("[red]Server registry not available[/red]"), id=f"error-{counter}")
            results_list.append(error_item)

    @on(ListView.Selected, "#results-list")
    def on_server_selected(self, event: ListView.Selected) -> None:
        """Handle server selection."""
        if hasattr(event.item, 'server_data'):
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

    @on(Button.Pressed, "#install-button")
    def on_install_clicked(self) -> None:
        """Handle install button click."""
        if self.step == "configure" and self.selected_server:
            self._install_server()

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
[yellow]Type:[/yellow] {getattr(self.selected_server, 'type', 'stdio')}"""
        
        if self.selected_server.requires:
            info_text += f"\n[yellow]Requirements:[/yellow] {', '.join(self.selected_server.requires)}"
        
        server_info.mount(Static(info_text))
        
        # Setup environment variables
        env_container = self.query_one("#env-vars-container", Container)
        env_container.remove_children()
        env_container.mount(Static("[bold]Environment Variables:[/bold]"))
        
        # Get server config to find env vars
        try:
            config_dict = self.selected_server.to_server_config("temp")
            env_vars = []
            
            if 'env' in config_dict:
                for key, value in config_dict['env'].items():
                    if value.startswith('$'):
                        env_vars.append(value[1:])
            
            if env_vars:
                for var in env_vars:
                    # Create a horizontal container for each env var row
                    row_container = Horizontal(classes="env-var-row")
                    # Mount the row container first
                    env_container.mount(row_container)
                    # Then mount children to the row container
                    row_container.mount(Static(f"{var}:", classes="env-var-label"))
                    env_input = Input(placeholder=f"Enter {var} value...", classes="env-var-input", id=f"env-{var}")
                    row_container.mount(env_input)
            else:
                env_container.mount(Static("[dim]No environment variables required[/dim]"))
                
        except Exception as e:
            env_container.mount(Static(f"[red]Error loading configuration: {e}[/red]"))

    def _install_server(self) -> None:
        """Install the selected server with configuration."""
        if not self.selected_server:
            return
        
        try:
            # Collect environment variables
            env_vars = {}
            env_inputs = self.query(Input)
            
            for input_widget in env_inputs:
                if input_widget.id and input_widget.id.startswith("env-"):
                    var_name = input_widget.id[4:]  # Remove "env-" prefix
                    value = input_widget.value.strip()
                    if value:
                        env_vars[var_name] = value
            
            # Set environment variables
            for var, value in env_vars.items():
                os.environ[var] = value
            
            # Generate server name
            import time
            server_name = f"{self.selected_server.name}-{int(time.time()) % 10000}"
            
            # Get server config
            config_dict = self.selected_server.to_server_config(server_name)
            
            # Create and register the server
            from code_puppy.mcp import ServerConfig
            from code_puppy.mcp.manager import get_mcp_manager
            
            server_config = ServerConfig(
                id=f"{server_name}_{hash(server_name)}",
                name=server_name,
                type=config_dict.pop('type'),
                enabled=True,
                config=config_dict
            )
            
            manager = get_mcp_manager()
            server_id = manager.register_server(server_config)
            
            if server_id:
                # Save to mcp_servers.json
                from code_puppy.config import MCP_SERVERS_FILE
                
                if os.path.exists(MCP_SERVERS_FILE):
                    with open(MCP_SERVERS_FILE, 'r') as f:
                        data = json.load(f)
                        servers = data.get("mcp_servers", {})
                else:
                    servers = {}
                    data = {"mcp_servers": servers}
                
                servers[server_name] = config_dict
                servers[server_name]['type'] = server_config.type
                
                os.makedirs(os.path.dirname(MCP_SERVERS_FILE), exist_ok=True)
                with open(MCP_SERVERS_FILE, 'w') as f:
                    json.dump(data, f, indent=2)
                
                # Reload MCP servers
                from code_puppy.agent import reload_mcp_servers
                reload_mcp_servers()
                
                self.dismiss({
                    "success": True,
                    "message": f"Successfully installed '{server_name}' from {self.selected_server.display_name}",
                    "server_name": server_name
                })
            else:
                self.dismiss({
                    "success": False,
                    "message": "Failed to register server"
                })
                
        except Exception as e:
            self.dismiss({
                "success": False,
                "message": f"Installation failed: {str(e)}"
            })

    def on_key(self, event) -> None:
        """Handle key events."""
        if event.key == "escape":
            self.on_cancel_clicked()