# MCP Overhaul - Pydantic-AI Compatible Implementation

## Critical Compatibility Requirements

### Must Maintain These Interfaces

1. **Server Classes**: Must return actual pydantic-ai MCP server instances:
   - `pydantic_ai.mcp.MCPServerSSE`
   - `pydantic_ai.mcp.MCPServerStdio`  
   - `pydantic_ai.mcp.MCPServerStreamableHTTP`

2. **Agent Integration**: Must provide `List[MCPServer]` to Agent constructor:
   ```python
   agent = Agent(
       model=model,
       mcp_servers=mcp_servers,  # Must be pydantic-ai server instances
       ...
   )
   ```

3. **Async Context Manager**: Must work with:
   ```python
   async with agent.run_mcp_servers():
       response = await agent.run(...)
   ```

## Revised Architecture - Wrapper Pattern

Instead of replacing pydantic-ai's MCP servers, we'll wrap them with management capabilities:

### Core Design: ManagedMCPServer

```python
from pydantic_ai.mcp import MCPServerSSE, MCPServerStdio, MCPServerStreamableHTTP

class ManagedMCPServer:
    """
    Wrapper that adds management capabilities while maintaining compatibility.
    The actual pydantic-ai server instance is accessible via .server property.
    """
    def __init__(self, server_config: ServerConfig):
        self.id = server_config.id
        self.name = server_config.name
        self.config = server_config
        self.server = None  # The actual pydantic-ai MCP server
        self.state = ServerState.STOPPED
        self.health_monitor = HealthMonitor(self.id)
        self.circuit_breaker = CircuitBreaker(self.id)
        self.metrics = MetricsCollector(self.id)
        
    def get_pydantic_server(self) -> Union[MCPServerSSE, MCPServerStdio, MCPServerStreamableHTTP]:
        """Returns the actual pydantic-ai server instance for Agent use"""
        if not self.server:
            self.server = self._create_server()
        return self.server
    
    def _create_server(self):
        """Creates the appropriate pydantic-ai server based on config"""
        if self.config.type == "sse":
            return MCPServerSSE(url=self.config.url, http_client=self._get_http_client())
        elif self.config.type == "stdio":
            return MCPServerStdio(
                command=self.config.command,
                args=self.config.args,
                timeout=self.config.timeout
            )
        elif self.config.type == "http":
            return MCPServerStreamableHTTP(
                url=self.config.url,
                http_client=self._get_http_client()
            )
```

### Updated MCPManager

```python
class MCPManager:
    """
    Manages MCP servers while maintaining pydantic-ai compatibility
    """
    def __init__(self):
        self.servers: Dict[str, ManagedMCPServer] = {}
        self.registry = ServerRegistry()
        self.status_tracker = ServerStatusTracker()
        
    def get_servers_for_agent(self) -> List[Union[MCPServerSSE, MCPServerStdio, MCPServerStreamableHTTP]]:
        """
        Returns list of pydantic-ai server instances for Agent constructor.
        This is what gets passed to Agent(mcp_servers=...)
        """
        active_servers = []
        for managed_server in self.servers.values():
            if managed_server.is_enabled() and not managed_server.is_quarantined():
                try:
                    # Get the actual pydantic-ai server instance
                    pydantic_server = managed_server.get_pydantic_server()
                    active_servers.append(pydantic_server)
                except Exception as e:
                    # Log error but don't crash
                    logger.error(f"Failed to create server {managed_server.name}: {e}")
        return active_servers
    
    def reload_server(self, server_name: str):
        """Hot reload a specific server"""
        if server_name in self.servers:
            managed = self.servers[server_name]
            # Create new pydantic-ai server instance
            managed.server = None  # Clear old instance
            managed.get_pydantic_server()  # Create new one
```

### Integration with Existing Code

```python
# In code_puppy/agent.py - minimal changes needed

def _load_mcp_servers(extra_headers: Optional[Dict[str, str]] = None):
    """
    Updated to use MCPManager while maintaining compatibility
    """
    manager = get_mcp_manager()  # Get singleton manager
    
    # Load configurations as before
    configs = load_mcp_server_configs()
    
    # Register servers with manager
    for name, conf in configs.items():
        server_config = ServerConfig(
            name=name,
            type=conf.get("type", "sse"),
            config=conf,
            enabled=conf.get("enabled", True)
        )
        manager.register_server(server_config)
    
    # Return pydantic-ai compatible server list
    return manager.get_servers_for_agent()

def reload_code_generation_agent():
    """Existing function - minimal changes"""
    # ... existing code ...
    
    # This line stays exactly the same!
    mcp_servers = _load_mcp_servers()  # Returns List[MCPServer] as before
    
    # Agent initialization stays exactly the same!
    agent = Agent(
        model=model,
        instructions=instructions,
        output_type=str,
        retries=3,
        mcp_servers=mcp_servers,  # Same interface!
        history_processors=[message_history_accumulator],
        model_settings=model_settings,
    )
    # ... rest stays the same ...
```

## Implementation Tasks - Revised for Compatibility

### Task Group A: Core Wrapper Infrastructure

#### A1: Create Managed Server Wrapper
- **File**: `code_puppy/mcp/managed_server.py`
- **Class**: `ManagedMCPServer`
- **Key requirement**: Must return actual pydantic-ai server instances
- **Methods**:
  ```python
  get_pydantic_server() -> Union[MCPServerSSE, MCPServerStdio, MCPServerStreamableHTTP]
  wrap_with_error_isolation(self, server: MCPServer) -> MCPServer
  enable(self) -> None
  disable(self) -> None
  quarantine(self, duration: int) -> None
  ```

#### A2: Create Proxy Server Classes (Optional Enhancement)
- **File**: `code_puppy/mcp/proxies.py`
- **Classes**: `ProxyMCPServerSSE`, `ProxyMCPServerStdio`, `ProxyMCPServerStreamableHTTP`
- **Purpose**: Subclass pydantic-ai servers to add telemetry without breaking interface
- **Example**:
  ```python
  class ProxyMCPServerSSE(MCPServerSSE):
      """Transparent proxy that adds monitoring"""
      def __init__(self, url: str, http_client=None, manager=None):
          super().__init__(url, http_client)
          self.manager = manager
          
      async def __aenter__(self):
          # Record startup
          if self.manager:
              self.manager.record_event("server_starting")
          return await super().__aenter__()
  ```

### Task Group B: Command Interface (No Breaking Changes)

#### B1: MCP Commands Implementation
- **File**: `code_puppy/command_line/mcp_commands.py`
- **Key requirement**: Commands manipulate manager, not servers directly
- **Commands**:
  ```python
  /mcp list         # Shows managed servers with status
  /mcp start <name> # Enables a disabled server
  /mcp stop <name>  # Disables a server (removes from agent on next reload)
  /mcp restart      # Triggers agent reload with updated servers
  /mcp status       # Dashboard showing all servers
  /mcp test <name>  # Tests a server without adding to agent
  ```

### Task Group C: Configuration Compatibility

#### C1: Backward Compatible Config Loading
- **File**: `code_puppy/mcp/config_loader.py`
- **Maintains**: Existing `mcp_servers.json` format
- **Enhancements**: Additional optional fields
  ```json
  {
    "mcp_servers": {
      "existing_server": {
        "type": "sse",
        "url": "http://localhost:8080/sse",
        "headers": {},
        // New optional fields:
        "enabled": true,
        "auto_restart": true,
        "health_check": {
          "enabled": true,
          "interval": 30
        }
      }
    }
  }
  ```

### Task Group D: Agent Creator Integration

#### D1: Agent Creator MCP Support
- **File**: `code_puppy/agents/agent_creator_agent.py` (modifications)
- **New capabilities**:
  ```python
  def create_agent_with_mcp(self, agent_config: Dict) -> Dict:
      """
      Creates agent JSON that includes MCP configuration
      """
      # Agent JSON now includes MCP requirements
      agent_json = {
          "name": "my-agent",
          "tools": ["read_file", "edit_file"],
          "mcp_servers": [  # New field!
              {
                  "type": "stdio",
                  "command": "npx",
                  "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"]
              }
          ]
      }
      return agent_json
  ```

#### D2: MCP Template Integration
- **Requirement**: Agent JSON files can specify required MCP servers
- **Implementation**: When loading agent, also configure its MCP servers
- **Example agent.json**:
  ```json
  {
    "name": "doc-search-agent",
    "display_name": "Documentation Expert",
    "tools": ["agent_share_your_reasoning"],
    "mcp_servers": [
      {
        "name": "docs-server",
        "type": "http",
        "url": "http://localhost:3000/mcp",
        "auto_start": true
      }
    ]
  }
  ```

### Task Group E: Testing with Real pydantic-ai Servers

#### E1: Integration Tests with pydantic-ai
- **File**: `tests/mcp/test_pydantic_compatibility.py`
- **Tests**:
  ```python
  async def test_managed_server_returns_pydantic_instance():
      """Ensure we return actual pydantic-ai server instances"""
      managed = ManagedMCPServer(config)
      server = managed.get_pydantic_server()
      assert isinstance(server, (MCPServerSSE, MCPServerStdio, MCPServerStreamableHTTP))
  
  async def test_agent_accepts_managed_servers():
      """Ensure Agent works with our managed servers"""
      manager = MCPManager()
      servers = manager.get_servers_for_agent()
      agent = Agent(model=model, mcp_servers=servers)
      async with agent.run_mcp_servers():
          # Should work exactly as before
          pass
  ```

## Key Differences from Original Plan

1. **No Custom Server Classes**: We use actual pydantic-ai classes, not replacements
2. **Wrapper Pattern**: Management features added via wrapper, not inheritance
3. **Transparent to Agent**: Agent sees standard pydantic-ai servers
4. **Config Compatibility**: Existing configs work without changes
5. **Progressive Enhancement**: New features are optional additions

## Migration Path

### Phase 1: Zero Breaking Changes
1. Implement `ManagedMCPServer` wrapper
2. Update `_load_mcp_servers()` to use manager internally
3. Everything else stays the same

### Phase 2: Add Management Features
1. Implement `/mcp` commands
2. Add health monitoring
3. Add error isolation
4. All opt-in, no breaking changes

### Phase 3: Agent Integration
1. Allow agents to specify MCP requirements
2. Auto-configure MCP when loading agents
3. Template system for common patterns

## Success Criteria

1. **100% Backward Compatible**: Existing code works without modification
2. **Agent Compatible**: Agents created with new system work with existing pydantic-ai
3. **Progressive Enhancement**: New features don't break old configs
4. **Transparent Operation**: pydantic-ai sees standard MCP servers
5. **Dynamic Management**: Can control servers without breaking agent

## Testing Strategy

### Compatibility Tests
```python
# Must pass with zero changes to existing code
async def test_existing_agent_code_still_works():
    """Ensure existing agent.py code works unchanged"""
    mcp_servers = _load_mcp_servers()  # Old function
    agent = Agent(mcp_servers=mcp_servers)  # Old usage
    async with agent.run_mcp_servers():  # Old pattern
        result = await agent.run("test")
    assert result  # Should work
```

### New Feature Tests
```python
# New management features
async def test_runtime_server_control():
    """Test new management capabilities"""
    manager = get_mcp_manager()
    manager.stop_server("test-server")
    assert "test-server" not in manager.get_active_servers()
    manager.start_server("test-server")
    assert "test-server" in manager.get_active_servers()
```

## Implementation Priority

1. **First**: Wrapper implementation with zero breaking changes
2. **Second**: Management commands that don't affect existing flow
3. **Third**: Agent creator integration
4. **Fourth**: Advanced features (templates, marketplace)

This approach ensures we maintain 100% compatibility with pydantic-ai while adding robust management capabilities.