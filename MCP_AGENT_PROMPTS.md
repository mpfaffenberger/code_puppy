# MCP Implementation - Agent Prompts

## Phase 1: Core Infrastructure

### Agent A1: Managed Server Wrapper Implementation

**Task**: Implement the ManagedMCPServer wrapper class

**Context**: You're building a wrapper around pydantic-ai's MCP server classes that adds management capabilities while maintaining 100% compatibility with the existing Agent interface.

**Requirements**:
1. Create file: `code_puppy/mcp/managed_server.py`
2. Import these pydantic-ai classes: `MCPServerSSE`, `MCPServerStdio`, `MCPServerStreamableHTTP` from `pydantic_ai.mcp`
3. Implement the `ManagedMCPServer` class with these exact methods:
   - `__init__(self, server_config: ServerConfig)`
   - `get_pydantic_server() -> Union[MCPServerSSE, MCPServerStdio, MCPServerStreamableHTTP]`
   - `_create_server()` - Creates appropriate pydantic-ai server based on config type
   - `_get_http_client()` - Creates httpx.AsyncClient with headers from config
   - `enable()` and `disable()` - Toggle server availability
   - `is_enabled() -> bool`
   - `quarantine(duration: int)` - Temporarily disable server
   - `is_quarantined() -> bool`
   - `get_status() -> Dict` - Return current status info

**Data Structures**:
```python
@dataclass
class ServerConfig:
    id: str
    name: str
    type: str  # "sse", "stdio", or "http"
    enabled: bool = True
    config: Dict = field(default_factory=dict)  # Raw config from JSON
    
class ServerState(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"
    QUARANTINED = "quarantined"
```

**Critical Compatibility Requirement**: The `get_pydantic_server()` method MUST return an actual instance of one of the three pydantic-ai MCP server classes. Do not create custom classes or proxies - return the real pydantic-ai objects.

**Example Usage**:
```python
config = ServerConfig(id="123", name="test", type="sse", config={"url": "http://localhost:8080"})
managed = ManagedMCPServer(config)
pydantic_server = managed.get_pydantic_server()  # Returns actual MCPServerSSE instance
```

**Tests to implement**:
- Test server creation for each type (sse, stdio, http)
- Test enable/disable functionality
- Test quarantine with timeout
- Verify returned server is correct pydantic-ai type

---

### Agent A2: Server Registry Implementation

**Task**: Implement the ServerRegistry class for managing server configurations

**Context**: You're building a registry that tracks all MCP server configurations and provides CRUD operations.

**Requirements**:
1. Create file: `code_puppy/mcp/registry.py`
2. Implement the `ServerRegistry` class with these methods:
   - `__init__(self, storage_path: Optional[str] = None)`
   - `register(self, config: ServerConfig) -> str` - Add new server, return ID
   - `unregister(self, server_id: str) -> bool` - Remove server
   - `get(self, server_id: str) -> Optional[ServerConfig]`
   - `get_by_name(self, name: str) -> Optional[ServerConfig]`
   - `list_all() -> List[ServerConfig]`
   - `update(self, server_id: str, config: ServerConfig) -> bool`
   - `exists(self, server_id: str) -> bool`
   - `validate_config(self, config: ServerConfig) -> List[str]` - Return validation errors
   - `_persist()` - Save to disk
   - `_load()` - Load from disk

**Storage Format**:
- Store in `~/.code_puppy/mcp_registry.json`
- Use JSON serialization for ServerConfig objects
- Handle file not existing gracefully

**Validation Rules**:
- Name must be unique
- Type must be one of: "sse", "stdio", "http"
- For "sse"/"http": url is required
- For "stdio": command is required
- Server IDs must be unique

**Thread Safety**: Use threading.Lock for all operations since registry may be accessed from multiple async contexts

**Tests to implement**:
- Test CRUD operations
- Test name uniqueness enforcement
- Test persistence and loading
- Test validation for each server type
- Test thread safety with concurrent operations

---

### Agent A3: Server Status Tracker

**Task**: Implement the ServerStatusTracker for monitoring server states

**Context**: You're building a component that tracks the runtime status of MCP servers including state, metrics, and events.

**Requirements**:
1. Create file: `code_puppy/mcp/status_tracker.py`
2. Implement the `ServerStatusTracker` class with these methods:
   - `__init__(self)`
   - `set_status(self, server_id: str, state: ServerState) -> None`
   - `get_status(self, server_id: str) -> ServerState`
   - `set_metadata(self, server_id: str, key: str, value: Any) -> None`
   - `get_metadata(self, server_id: str, key: str) -> Any`
   - `record_event(self, server_id: str, event_type: str, details: Dict) -> None`
   - `get_events(self, server_id: str, limit: int = 100) -> List[Event]`
   - `clear_events(self, server_id: str) -> None`
   - `get_uptime(self, server_id: str) -> Optional[timedelta]`
   - `record_start_time(self, server_id: str) -> None`
   - `record_stop_time(self, server_id: str) -> None`

**Data Structures**:
```python
@dataclass
class Event:
    timestamp: datetime
    event_type: str  # "started", "stopped", "error", "health_check", etc.
    details: Dict
    server_id: str
```

**Storage**: 
- In-memory only (no persistence required)
- Use collections.deque for event storage (automatic size limiting)
- Thread-safe operations

**Tests to implement**:
- Test state transitions
- Test event recording and retrieval
- Test metadata storage
- Test uptime calculation
- Test event limit enforcement

---

### Agent A4: MCP Manager Core

**Task**: Implement the main MCPManager class

**Context**: You're building the central manager that coordinates all MCP server operations while maintaining pydantic-ai compatibility.

**Requirements**:
1. Create file: `code_puppy/mcp/manager.py`
2. Implement the `MCPManager` class with these methods:
   - `__init__(self)`
   - `register_server(self, config: ServerConfig) -> str`
   - `get_servers_for_agent() -> List[Union[MCPServerSSE, MCPServerStdio, MCPServerStreamableHTTP]]`
   - `get_server(self, server_id: str) -> Optional[ManagedMCPServer]`
   - `list_servers() -> List[ServerInfo]`
   - `enable_server(self, server_id: str) -> bool`
   - `disable_server(self, server_id: str) -> bool`
   - `reload_server(self, server_id: str) -> bool`
   - `remove_server(self, server_id: str) -> bool`
   - `get_server_status(self, server_id: str) -> Dict`

**Dependencies**:
- Use `ManagedMCPServer` from managed_server.py
- Use `ServerRegistry` from registry.py
- Use `ServerStatusTracker` from status_tracker.py

**Critical Method**: `get_servers_for_agent()` must:
1. Return only enabled, non-quarantined servers
2. Return actual pydantic-ai server instances (not wrappers)
3. Handle errors gracefully (log but don't crash)
4. Return empty list if no servers available

**Singleton Pattern**: Implement as singleton using module-level instance:
```python
_manager_instance = None

def get_mcp_manager() -> MCPManager:
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = MCPManager()
    return _manager_instance
```

**Tests to implement**:
- Test server registration and retrieval
- Test get_servers_for_agent returns correct types
- Test enable/disable functionality
- Test singleton pattern
- Test error handling in get_servers_for_agent

---

## Phase 2: Error Handling & Monitoring

### Agent B1: Error Isolator Implementation

**Task**: Implement error isolation for MCP server calls

**Context**: You're building a system to prevent MCP server errors from crashing the application.

**Requirements**:
1. Create file: `code_puppy/mcp/error_isolation.py`
2. Implement the `MCPErrorIsolator` class with these methods:
   - `async isolated_call(self, server_id: str, func: Callable, *args, **kwargs) -> Any`
   - `quarantine_server(self, server_id: str, duration: int) -> None`
   - `is_quarantined(self, server_id: str) -> bool`
   - `release_quarantine(self, server_id: str) -> None`
   - `get_error_stats(self, server_id: str) -> ErrorStats`
   - `should_quarantine(self, server_id: str) -> bool`

**Error Categories** to handle:
- Network errors (ConnectionError, TimeoutError)
- Protocol errors (JSON decode, schema validation)
- Server errors (5xx responses)
- Rate limit errors (429 responses)
- Authentication errors (401, 403)

**Quarantine Logic**:
- Quarantine after 5 consecutive errors
- Quarantine duration increases exponentially (30s, 60s, 120s, etc.)
- Max quarantine duration: 30 minutes
- Reset error count after successful call

**Data Structure**:
```python
@dataclass
class ErrorStats:
    total_errors: int
    consecutive_errors: int
    last_error: Optional[datetime]
    error_types: Dict[str, int]  # Count by error type
    quarantine_count: int
    quarantine_until: Optional[datetime]
```

**Tests to implement**:
- Test error catching for each category
- Test quarantine threshold logic
- Test exponential backoff
- Test successful call resets counter
- Test concurrent error handling

---

### Agent B2: Circuit Breaker Implementation

**Task**: Implement circuit breaker pattern for MCP servers

**Context**: You're building a circuit breaker to prevent cascading failures when MCP servers are unhealthy.

**Requirements**:
1. Create file: `code_puppy/mcp/circuit_breaker.py`
2. Implement the `CircuitBreaker` class with these methods:
   - `__init__(self, failure_threshold: int = 5, success_threshold: int = 2, timeout: int = 60)`
   - `async call(self, func: Callable, *args, **kwargs) -> Any`
   - `record_success() -> None`
   - `record_failure() -> None`
   - `get_state() -> CircuitState`
   - `is_open() -> bool`
   - `is_half_open() -> bool`
   - `is_closed() -> bool`
   - `reset() -> None`
   - `force_open() -> None`
   - `force_close() -> None`

**States**:
```python
class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Blocking calls
    HALF_OPEN = "half_open"  # Testing recovery
```

**State Transitions**:
- CLOSED → OPEN: After failure_threshold consecutive failures
- OPEN → HALF_OPEN: After timeout seconds
- HALF_OPEN → CLOSED: After success_threshold consecutive successes
- HALF_OPEN → OPEN: After any failure

**Behavior**:
- In OPEN state: Raise CircuitOpenError immediately
- In HALF_OPEN state: Allow limited calls to test recovery
- In CLOSED state: Normal operation

**Tests to implement**:
- Test state transitions
- Test threshold triggers
- Test timeout behavior
- Test half-open recovery
- Test concurrent call handling

---

### Agent B3: Health Monitor Implementation

**Task**: Implement health monitoring for MCP servers

**Context**: You're building a system that continuously monitors MCP server health and triggers recovery actions.

**Requirements**:
1. Create file: `code_puppy/mcp/health_monitor.py`
2. Implement the `HealthMonitor` class with these methods:
   - `__init__(self, check_interval: int = 30)`
   - `async start_monitoring(self, server_id: str, server: ManagedMCPServer) -> None`
   - `async stop_monitoring(self, server_id: str) -> None`
   - `async check_health(self, server: ManagedMCPServer) -> HealthStatus`
   - `async perform_health_check(self, server) -> HealthCheckResult`
   - `register_health_check(self, server_type: str, check_func: Callable) -> None`
   - `get_health_history(self, server_id: str, limit: int = 100) -> List[HealthStatus]`
   - `is_healthy(self, server_id: str) -> bool`

**Health Checks by Server Type**:
- **SSE/HTTP**: GET request to health endpoint or base URL
- **Stdio**: Send `ping` or `list-tools` command
- **All types**: Attempt to list available tools

**Data Structures**:
```python
@dataclass
class HealthStatus:
    timestamp: datetime
    is_healthy: bool
    latency_ms: Optional[float]
    error: Optional[str]
    check_type: str  # "ping", "list_tools", etc.

@dataclass
class HealthCheckResult:
    success: bool
    latency_ms: float
    error: Optional[str]
```

**Monitoring Loop**:
- Use asyncio.create_task for background monitoring
- Store task reference for cancellation
- Log health check results
- Trigger recovery on consecutive failures

**Tests to implement**:
- Test health check for each server type
- Test monitoring start/stop
- Test history tracking
- Test concurrent monitoring
- Test error handling in health checks

---

### Agent B4: Retry Manager Implementation

**Task**: Implement retry logic with various backoff strategies

**Context**: You're building a retry manager that handles transient failures in MCP server communication.

**Requirements**:
1. Create file: `code_puppy/mcp/retry_manager.py`
2. Implement the `RetryManager` class with these methods:
   - `async retry_with_backoff(self, func: Callable, max_attempts: int = 3, strategy: str = "exponential") -> Any`
   - `calculate_backoff(self, attempt: int, strategy: str) -> float`
   - `should_retry(self, error: Exception) -> bool`
   - `get_retry_stats(self, server_id: str) -> RetryStats`
   - `record_retry(self, server_id: str, attempt: int, success: bool) -> None`

**Backoff Strategies**:
- **fixed**: Same delay each time (1 second)
- **linear**: Linear increase (1s, 2s, 3s, ...)
- **exponential**: Exponential increase (1s, 2s, 4s, 8s, ...)
- **exponential_jitter**: Exponential with random jitter (±25%)

**Retryable Errors**:
- Network timeouts
- Connection errors
- 5xx server errors
- Rate limit errors (with longer backoff)

**Non-Retryable Errors**:
- Authentication errors (401, 403)
- Client errors (400, 404)
- Schema validation errors

**Data Structure**:
```python
@dataclass
class RetryStats:
    total_retries: int
    successful_retries: int
    failed_retries: int
    average_attempts: float
    last_retry: Optional[datetime]
```

**Tests to implement**:
- Test each backoff strategy
- Test retry decision logic
- Test max attempts enforcement
- Test stats tracking
- Test concurrent retries

---

## Phase 3: Command Interface

### Agent C1: MCP Command Handler

**Task**: Implement the /mcp command interface

**Context**: You're building the command-line interface for managing MCP servers at runtime.

**Requirements**:
1. Create file: `code_puppy/command_line/mcp_commands.py`
2. Implement the `MCPCommandHandler` class with these methods:
   - `handle_mcp_command(self, command: str) -> bool`
   - `cmd_list(self, args: List[str]) -> None`
   - `cmd_start(self, args: List[str]) -> None`
   - `cmd_stop(self, args: List[str]) -> None`
   - `cmd_restart(self, args: List[str]) -> None`
   - `cmd_status(self, args: List[str]) -> None`
   - `cmd_test(self, args: List[str]) -> None`
   - `cmd_add(self, args: List[str]) -> None`
   - `cmd_remove(self, args: List[str]) -> None`
   - `cmd_logs(self, args: List[str]) -> None`
   - `cmd_help(self, args: List[str]) -> None`

**Command Parsing**:
```python
# Handle commands like:
/mcp                    # Show status dashboard
/mcp list              # List all servers
/mcp start server-name # Start specific server
/mcp stop server-name  # Stop specific server
/mcp status server-name # Detailed status
/mcp test server-name  # Test connectivity
/mcp help              # Show help
```

**Integration**: Add to existing command handler in `code_puppy/command_line/command_handler.py`:
```python
if command.startswith("/mcp"):
    from code_puppy.command_line.mcp_commands import MCPCommandHandler
    handler = MCPCommandHandler()
    return handler.handle_mcp_command(command)
```

**Output**: Use Rich library for formatted output:
- Tables for lists
- Status indicators (✓, ✗, ⚠)
- Color coding (green=healthy, red=error, yellow=warning)

**Tests to implement**:
- Test command parsing
- Test each command execution
- Test error handling
- Test output formatting
- Test invalid command handling

---

### Agent C2: MCP Dashboard Implementation

**Task**: Implement the MCP status dashboard

**Context**: You're building a visual dashboard that shows the status of all MCP servers.

**Requirements**:
1. Create file: `code_puppy/mcp/dashboard.py`
2. Implement the `MCPDashboard` class with these methods:
   - `render_dashboard() -> Table`
   - `render_server_row(self, server: ServerInfo) -> List`
   - `render_health_indicator(self, health: HealthStatus) -> str`
   - `render_state_indicator(self, state: ServerState) -> str`
   - `render_metrics_summary(self, metrics: Dict) -> str`
   - `format_uptime(self, start_time: datetime) -> str`
   - `format_latency(self, latency_ms: float) -> str`

**Dashboard Layout**:
```
┌─────────────────────────────────────────────────────────┐
│ MCP Server Status Dashboard                              │
├──────┬────────┬────────┬────────┬──────────┬───────────┤
│ Name │ Type   │ State  │ Health │ Uptime   │ Latency   │
├──────┼────────┼────────┼────────┼──────────┼───────────┤
│ docs │ SSE    │ ✓ Run  │ ✓      │ 2h 15m   │ 45ms      │
│ db   │ Stdio  │ ✗ Stop │ -      │ -        │ -         │
│ api  │ HTTP   │ ⚠ Err  │ ✗      │ 5m 30s   │ timeout   │
└──────┴────────┴────────┴────────┴──────────┴───────────┘
```

**Status Indicators**:
- State: ✓ (running), ✗ (stopped), ⚠ (error), ⏸ (paused)
- Health: ✓ (healthy), ✗ (unhealthy), ? (unknown)
- Colors: green, red, yellow, dim gray

**Use Rich Library**:
```python
from rich.table import Table
from rich.console import Console
```

**Tests to implement**:
- Test rendering with various states
- Test empty dashboard
- Test formatting functions
- Test error handling
- Test large number of servers

---

### Agent C3: Configuration Wizard

**Task**: Implement interactive MCP server configuration wizard

**Context**: You're building an interactive wizard that guides users through configuring new MCP servers.

**Requirements**:
1. Create file: `code_puppy/mcp/config_wizard.py`
2. Implement the `MCPConfigWizard` class with these methods:
   - `async run_wizard() -> ServerConfig`
   - `prompt_server_type() -> str`
   - `prompt_server_name() -> str`
   - `prompt_sse_config() -> Dict`
   - `prompt_http_config() -> Dict`
   - `prompt_stdio_config() -> Dict`
   - `validate_url(self, url: str) -> bool`
   - `validate_command(self, command: str) -> bool`
   - `test_connection(self, config: ServerConfig) -> bool`
   - `prompt_confirmation(self, config: ServerConfig) -> bool`

**Wizard Flow**:
1. Welcome message
2. Prompt for server name (validate uniqueness)
3. Prompt for server type (sse/http/stdio)
4. Based on type, prompt for specific config:
   - SSE/HTTP: URL, headers, timeout
   - Stdio: command, arguments, working directory
5. Test connection (optional)
6. Show summary and confirm
7. Save configuration

**Prompts** using prompt_toolkit or input():
```python
# Example prompts:
name = input("Enter server name: ").strip()
server_type = input("Server type (sse/http/stdio): ").strip().lower()
url = input("Enter server URL: ").strip()
```

**Validation**:
- Name: alphanumeric with hyphens, unique
- URL: valid HTTP/HTTPS URL
- Command: executable exists
- Timeout: positive integer

**Tests to implement**:
- Test wizard flow for each server type
- Test validation logic
- Test connection testing
- Test cancellation handling
- Test config generation

---

## Phase 4: Agent Integration

### Agent D1: Agent MCP Integration

**Task**: Update agent.py to use the new MCP manager

**Context**: You're modifying the existing agent.py to use the new MCP management system while maintaining backward compatibility.

**Requirements**:
1. Modify file: `code_puppy/agent.py`
2. Update the `_load_mcp_servers` function:
   ```python
   def _load_mcp_servers(extra_headers: Optional[Dict[str, str]] = None):
       """Load MCP servers using the new manager"""
       from code_puppy.mcp.manager import get_mcp_manager
       
       manager = get_mcp_manager()
       
       # Load legacy config for backward compatibility
       configs = load_mcp_server_configs()
       
       # Register servers with manager
       for name, conf in configs.items():
           # Convert old format to new ServerConfig
           # Register with manager
           pass
       
       # Return pydantic-ai compatible servers
       return manager.get_servers_for_agent()
   ```

3. Add new function for hot reload:
   ```python
   def reload_mcp_servers():
       """Reload MCP servers without restarting agent"""
       manager = get_mcp_manager()
       return manager.get_servers_for_agent()
   ```

**Backward Compatibility**:
- Still load from `~/.code_puppy/mcp_servers.json`
- Convert old format to new ServerConfig
- Support both old and new config formats

**Tests to implement**:
- Test loading old format configs
- Test loading new format configs
- Test hot reload functionality
- Test error handling
- Test empty config handling

---

### Agent D2: Agent Creator MCP Enhancement

**Task**: Enhance the Agent Creator to support MCP server configuration

**Context**: You're updating the Agent Creator agent to allow creating agents with MCP server requirements.

**Requirements**:
1. Modify file: `code_puppy/agents/agent_creator_agent.py`
2. Add new methods:
   - `suggest_mcp_servers(self, agent_purpose: str) -> List[MCPTemplate]`
   - `prompt_for_mcp_servers(self) -> List[Dict]`
   - `generate_mcp_config(self, template: str, params: Dict) -> Dict`
   - `add_mcp_to_agent_config(self, agent_config: Dict, mcp_configs: List[Dict]) -> Dict`

**Agent JSON Schema Addition**:
```json
{
  "name": "agent-name",
  "tools": ["tool1", "tool2"],
  "mcp_servers": [  // New optional field
    {
      "name": "server-name",
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem"],
      "auto_start": true
    }
  ]
}
```

**MCP Suggestions** based on agent purpose:
- File operations → filesystem MCP server
- Database queries → database MCP server
- Web scraping → browser MCP server
- Documentation → docs MCP server

**Interactive Flow**:
1. After tools selection, ask "Would you like to add MCP servers?"
2. If yes, show suggestions based on selected tools
3. Allow selection from templates or custom config
4. Add to agent JSON

**Tests to implement**:
- Test MCP suggestion logic
- Test agent JSON generation with MCP
- Test template selection
- Test custom MCP config
- Test validation

---

### Agent D3: MCP Template System

**Task**: Implement the MCP template system for common server patterns

**Context**: You're building a template system that provides pre-configured MCP server setups for common use cases.

**Requirements**:
1. Create file: `code_puppy/mcp/templates.py`
2. Implement the `MCPTemplateManager` class with these methods:
   - `load_templates() -> Dict[str, MCPTemplate]`
   - `get_template(self, name: str) -> MCPTemplate`
   - `create_from_template(self, template_name: str, params: Dict) -> ServerConfig`
   - `validate_template_params(self, template: MCPTemplate, params: Dict) -> List[str]`
   - `list_templates() -> List[MCPTemplate]`
   - `register_template(self, template: MCPTemplate) -> None`

**Data Structure**:
```python
@dataclass
class MCPTemplate:
    name: str
    display_name: str
    description: str
    type: str  # "sse", "stdio", "http"
    config_template: Dict
    required_params: List[str]
    optional_params: Dict[str, Any]  # param -> default value
    tags: List[str]  # For categorization
```

**Built-in Templates**:
```python
BUILTIN_TEMPLATES = {
    "filesystem": MCPTemplate(
        name="filesystem",
        display_name="Filesystem Access",
        description="Provides file read/write access to specified directory",
        type="stdio",
        config_template={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "{directory}"]
        },
        required_params=["directory"],
        optional_params={},
        tags=["files", "io"]
    ),
    "postgres": MCPTemplate(
        name="postgres",
        display_name="PostgreSQL Database",
        description="Connect to PostgreSQL database",
        type="stdio",
        config_template={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-postgres", "{connection_string}"]
        },
        required_params=["connection_string"],
        optional_params={"pool_size": 5},
        tags=["database", "sql"]
    ),
    # Add more templates...
}
```

**Tests to implement**:
- Test template loading
- Test parameter substitution
- Test validation
- Test template registration
- Test config generation

---

## Phase 5: Testing

### Agent E1: Unit Test Suite

**Task**: Implement comprehensive unit tests for all MCP components

**Context**: You're creating unit tests that ensure each component works correctly in isolation.

**Requirements**:
1. Create test files in `tests/mcp/`:
   - `test_managed_server.py`
   - `test_registry.py`
   - `test_status_tracker.py`
   - `test_manager.py`
   - `test_error_isolation.py`
   - `test_circuit_breaker.py`
   - `test_health_monitor.py`

**Test Coverage Requirements**:
- Minimum 90% code coverage
- Test all public methods
- Test error conditions
- Test edge cases
- Test concurrent operations

**Mock Strategy**:
- Mock pydantic-ai MCP server classes
- Mock file I/O operations
- Mock network calls
- Mock async operations where needed

**Example Test Structure**:
```python
import pytest
from unittest.mock import Mock, patch
from code_puppy.mcp.managed_server import ManagedMCPServer

class TestManagedMCPServer:
    def test_create_sse_server(self):
        """Test SSE server creation"""
        config = ServerConfig(...)
        managed = ManagedMCPServer(config)
        server = managed.get_pydantic_server()
        assert isinstance(server, MCPServerSSE)
    
    def test_quarantine(self):
        """Test quarantine functionality"""
        # Test implementation
    
    # More tests...
```

**Tests to implement per component**:
- Happy path tests
- Error handling tests
- Boundary condition tests
- State transition tests
- Concurrent access tests

---

### Agent E2: Integration Test Suite

**Task**: Implement integration tests for MCP system interactions

**Context**: You're creating tests that verify components work together correctly.

**Requirements**:
1. Create file: `tests/mcp/test_integration.py`
2. Test scenarios:
   - Full server lifecycle (create, start, stop, remove)
   - Error isolation preventing crashes
   - Circuit breaker state transitions
   - Health monitoring triggering recovery
   - Command execution flows
   - Agent integration with managed servers

**Test Infrastructure**:
```python
@pytest.fixture
async def mock_mcp_server():
    """Create a mock MCP server for testing"""
    # Return mock server that simulates MCP behavior
    
@pytest.fixture
async def mcp_manager():
    """Create manager with test configuration"""
    # Return configured manager
```

**Key Integration Tests**:
```python
async def test_server_lifecycle():
    """Test complete server lifecycle"""
    manager = get_mcp_manager()
    
    # Register server
    config = ServerConfig(...)
    server_id = manager.register_server(config)
    
    # Start server
    assert manager.enable_server(server_id)
    
    # Verify in agent list
    servers = manager.get_servers_for_agent()
    assert len(servers) == 1
    
    # Stop server
    assert manager.disable_server(server_id)
    
    # Verify removed from agent list
    servers = manager.get_servers_for_agent()
    assert len(servers) == 0

async def test_error_isolation():
    """Test that errors don't crash system"""
    # Test implementation

async def test_circuit_breaker_integration():
    """Test circuit breaker with real calls"""
    # Test implementation
```

**Tests to implement**:
- Multi-server management
- Cascading failure prevention
- Recovery mechanisms
- Hot reload functionality
- Command interface integration

---

### Agent E3: End-to-End Test Suite

**Task**: Implement end-to-end tests simulating real usage

**Context**: You're creating tests that verify the entire system works from user perspective.

**Requirements**:
1. Create file: `tests/mcp/test_e2e.py`
2. Test complete user workflows:
   - Configure server via wizard
   - Start/stop servers via commands
   - Create agent with MCP servers
   - Handle server failures gracefully
   - Monitor dashboard updates

**Test Scenarios**:
```python
async def test_wizard_to_usage_flow():
    """Test creating and using server via wizard"""
    # 1. Run wizard
    wizard = MCPConfigWizard()
    config = await wizard.run_wizard()
    
    # 2. Register server
    manager = get_mcp_manager()
    server_id = manager.register_server(config)
    
    # 3. Use in agent
    agent = get_code_generation_agent()
    servers = manager.get_servers_for_agent()
    
    # 4. Verify functionality
    # Test actual MCP calls

async def test_failure_recovery_flow():
    """Test system recovery from failures"""
    # 1. Setup server
    # 2. Simulate failures
    # 3. Verify recovery
    # 4. Check dashboard status

async def test_agent_creation_with_mcp():
    """Test creating agent with MCP requirements"""
    # 1. Create agent config with MCP
    # 2. Load agent
    # 3. Verify MCP servers loaded
    # 4. Test agent functionality
```

**Performance Tests**:
- Load test with many servers
- Concurrent command execution
- Recovery time measurements
- Memory usage monitoring

**Tests to implement**:
- Complete user journeys
- Error recovery scenarios
- Performance benchmarks
- Dashboard accuracy
- Multi-agent scenarios

---

## Implementation Notes for All Agents

### General Requirements:
1. **Python 3.11+** compatibility (use modern Python features)
2. **Type hints** on all functions and methods
3. **Docstrings** for all public methods
4. **Logging** using Python's logging module
5. **Error handling** - never let exceptions bubble up unhandled
6. **Async/await** for all I/O operations
7. **Thread safety** where concurrent access possible

### Code Style:
- Follow existing Code Puppy patterns
- Use dataclasses for data structures
- Use enums for constants
- Use pathlib for file paths
- Use Rich for console output

### Testing:
- Use pytest for all tests
- Use pytest-asyncio for async tests
- Mock external dependencies
- Test coverage > 90%

### Documentation:
- Include usage examples in docstrings
- Document all config options
- Explain error conditions
- Provide troubleshooting tips