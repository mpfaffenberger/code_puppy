import json
import logging
from pathlib import Path

from code_puppy.config import MCP_SERVERS_FILE
from code_puppy.plugins.claude_plugin_adapter.config import get_claude_plugins_dir

logger = logging.getLogger(__name__)

def sync_mcp_adapter(plugin_name: str, uninstall: bool = False) -> None:
    """
    Sync a Claude plugin's .mcp.json into Code Puppy's mcp_servers.json.
    If uninstall is True, only removes the entries managed by this plugin.
    """
    plugin_mcp_file = get_claude_plugins_dir() / plugin_name / ".mcp.json"
    mcp_servers_file = Path(MCP_SERVERS_FILE)
    
    managed_tag = f"claude_plugin_adapter:{plugin_name}"
    
    # 1. Load current mcp_servers.json
    current_config = {}
    if mcp_servers_file.exists():
        try:
            with open(mcp_servers_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    current_config = json.loads(content)
        except Exception as e:
            logger.error(f"claude_plugin_adapter: Failed to load current mcp_servers.json: {e}")
            return
            
    mcp_servers = current_config.get("mcp_servers", {})
    if "mcp_servers" not in current_config and "mcpServers" in current_config:
        mcp_servers = current_config.get("mcpServers", {})
        
    # 2. Strip existing entries managed by this plugin
    new_servers = {}
    for s_name, s_config in mcp_servers.items():
        if isinstance(s_config, dict) and s_config.get("_managed_by") == managed_tag:
            continue
        new_servers[s_name] = s_config
        
    # 3. If not uninstalling, load .mcp.json and inject
    if not uninstall and plugin_mcp_file.exists():
        try:
            with open(plugin_mcp_file, "r", encoding="utf-8") as f:
                plugin_mcp_data = json.loads(f.read())
                
            p_servers = plugin_mcp_data.get("mcpServers", plugin_mcp_data.get("mcp_servers", {}))
            for s_name, s_config in p_servers.items():
                if isinstance(s_config, dict):
                    s_config["_managed_by"] = managed_tag
                    new_servers[s_name] = s_config
                    
        except Exception as e:
            logger.error(f"claude_plugin_adapter: Failed to process {plugin_mcp_file}: {e}")
            
    # 4. Save back
    current_config["mcp_servers"] = new_servers
    if "mcpServers" in current_config:
        del current_config["mcpServers"]
        
    try:
        mcp_servers_file.parent.mkdir(parents=True, exist_ok=True)
        with open(mcp_servers_file, "w", encoding="utf-8") as f:
            json.dump(current_config, f, indent=2)
            logger.debug(f"claude_plugin_adapter: Synced MCP servers for {plugin_name}")
    except Exception as e:
        logger.error(f"claude_plugin_adapter: Failed to save mcp_servers.json: {e}")
