# WebSocket API Documentation 🐶

Code Puppy's web interface provides three WebSocket endpoints for real-time communication. This document covers connection patterns, message formats, and best practices.

## Table of Contents

- [Overview](#overview)
- [Endpoints](#endpoints)
  - [/ws/terminal - Interactive Terminal](#wsterminal---interactive-terminal)
  - [/ws/events - Real-time Events Stream](#wsevents---real-time-events-stream)
  - [/ws/health - Health Check](#wshealth---health-check)
- [Connection Examples](#connection-examples)
  - [JavaScript](#javascript)
  - [Python](#python)
  - [curl / websocat](#curl--websocat)
- [Error Handling](#error-handling)
- [Reconnection Strategies](#reconnection-strategies)
- [Configuration](#configuration)

---

## Overview

| Endpoint | Purpose | Bidirectional | Auth Required |
|----------|---------|---------------|---------------|
| `/ws/terminal` | Interactive PTY terminal | ✅ Yes | No |
| `/ws/events` | Real-time event streaming | ❌ Server → Client only | No |
| `/ws/health` | Connectivity testing | ✅ Echo | No |

All WebSocket endpoints are available at:
```
ws://localhost:8000/ws/<endpoint>
```

Or with TLS (if configured):
```
wss://your-host:port/ws/<endpoint>
```

---

## Endpoints

### `/ws/terminal` - Interactive Terminal

Creates a PTY (pseudo-terminal) session with a shell, enabling full interactive terminal access through the browser or any WebSocket client.

#### Connection Flow

1. Client connects to `/ws/terminal`
2. Server creates a PTY session with your default shell
3. Server sends `{"type": "session", "id": "..."}` to confirm
4. Bidirectional communication begins

#### Client → Server Messages

| Type | Format | Description |
|------|--------|-------------|
| `input` | `{"type": "input", "data": "string"}` | Send keystrokes/input to terminal |
| `resize` | `{"type": "resize", "cols": 80, "rows": 24}` | Resize the terminal dimensions |

**Input Examples:**
```json
// Send a command
{"type": "input", "data": "ls -la\n"}

// Send Ctrl+C (interrupt)
{"type": "input", "data": "\u0003"}

// Send Ctrl+D (EOF)
{"type": "input", "data": "\u0004"}

// Resize terminal to 120x40
{"type": "resize", "cols": 120, "rows": 40}
```

#### Server → Client Messages

| Type | Format | Description |
|------|--------|-------------|
| `session` | `{"type": "session", "id": "abc123"}` | Session created (sent once on connect) |
| `output` | `{"type": "output", "data": "base64string"}` | Terminal output (base64 encoded UTF-8) |
| `exit` | `{"type": "exit", "code": 0}` | Process exited with status code |

#### Decoding Terminal Output

Terminal output is base64-encoded UTF-8. Here's how to decode it:

**JavaScript:**
```javascript
function decodeTerminalOutput(base64Data) {
  const bytes = Uint8Array.from(atob(base64Data), c => c.charCodeAt(0));
  return new TextDecoder('utf-8').decode(bytes);
}

// Usage
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  if (msg.type === 'output') {
    const text = decodeTerminalOutput(msg.data);
    terminal.write(text); // e.g., xterm.js
  }
};
```

**Python:**
```python
import base64

def decode_terminal_output(base64_data: str) -> str:
    return base64.b64decode(base64_data).decode('utf-8')
```

#### Why Base64?

Terminal output can contain:
- ANSI escape codes (colors, cursor movement)
- Binary data from programs like `vim` or `htop`
- Non-UTF8 byte sequences

Base64 encoding ensures reliable transmission over JSON.

---

### `/ws/events` - Real-time Events Stream

Streams events from the `frontend_emitter` plugin, providing real-time visibility into agent activity, tool calls, and streaming responses.

#### Connection Behavior

1. On connect: Server sends recent events for "catch-up" (configurable buffer size)
2. New events are pushed as they occur
3. If idle for 30+ seconds, server sends `{"type": "ping"}` to keep connection alive

#### Event Structure

All events follow this structure:

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "type": "tool_call_start",
  "timestamp": "2024-01-10T12:00:00.000Z",
  "data": {
    // Event-specific payload
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID string | Unique event identifier |
| `type` | string | Event type (see below) |
| `timestamp` | ISO 8601 | When the event occurred |
| `data` | object | Event-specific payload |

#### Event Types

##### `tool_call_start`

Fired when a tool begins execution.

```json
{
  "id": "abc-123",
  "type": "tool_call_start",
  "timestamp": "2024-01-10T12:00:00.000Z",
  "data": {
    "tool_name": "read_file",
    "tool_args": {
      "file_path": "./src/main.py"
    },
    "start_time": 1704888000.123
  }
}
```

##### `tool_call_complete`

Fired when a tool finishes execution.

```json
{
  "id": "abc-124",
  "type": "tool_call_complete",
  "timestamp": "2024-01-10T12:00:00.500Z",
  "data": {
    "tool_name": "read_file",
    "tool_args": {
      "file_path": "./src/main.py"
    },
    "duration_ms": 45.2,
    "success": true,
    "result_summary": "Read 150 lines from ./src/main.py"
  }
}
```

##### `stream_event`

Fired during streaming responses from the agent (tokens, partial completions).

```json
{
  "id": "abc-125",
  "type": "stream_event",
  "timestamp": "2024-01-10T12:00:01.000Z",
  "data": {
    "event_type": "content_block_delta",
    "event_data": {
      "type": "text_delta",
      "text": "Let me analyze"
    },
    "agent_session_id": "session-abc-456"
  }
}
```

##### `agent_invoked`

Fired when a sub-agent is invoked.

```json
{
  "id": "abc-126",
  "type": "agent_invoked",
  "timestamp": "2024-01-10T12:00:02.000Z",
  "data": {
    "agent_name": "code_reviewer",
    "session_id": "review-auth-a3f2b1",
    "prompt_preview": "Review the authentication module for security..."
  }
}
```

##### `ping`

Keep-alive message sent every 30 seconds if no other events occur.

```json
{
  "type": "ping"
}
```

> 💡 **Tip:** You don't need to respond to pings. They're purely for keep-alive.

---

### `/ws/health` - Health Check

Simple echo server for testing WebSocket connectivity. Useful for:
- Verifying WebSocket support through proxies/firewalls
- Load balancer health checks
- Client connection testing

#### Behavior

Send any text message, receive `echo: <your message>` back.

```
Client: "hello"
Server: "echo: hello"

Client: "ping"
Server: "echo: ping"
```

---

## Connection Examples

### JavaScript

#### Terminal Connection

```javascript
class TerminalConnection {
  constructor(url = 'ws://localhost:8000/ws/terminal') {
    this.url = url;
    this.ws = null;
    this.sessionId = null;
    this.onOutput = null;
    this.onExit = null;
  }

  connect() {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        console.log('Terminal WebSocket connected');
      };

      this.ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        
        switch (msg.type) {
          case 'session':
            this.sessionId = msg.id;
            resolve(this.sessionId);
            break;
          
          case 'output':
            const decoded = this.decodeOutput(msg.data);
            this.onOutput?.(decoded);
            break;
          
          case 'exit':
            this.onExit?.(msg.code);
            this.ws.close();
            break;
        }
      };

      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        reject(error);
      };

      this.ws.onclose = (event) => {
        console.log(`Connection closed: ${event.code} ${event.reason}`);
      };
    });
  }

  decodeOutput(base64Data) {
    const bytes = Uint8Array.from(atob(base64Data), c => c.charCodeAt(0));
    return new TextDecoder('utf-8').decode(bytes);
  }

  sendInput(data) {
    this.ws.send(JSON.stringify({ type: 'input', data }));
  }

  resize(cols, rows) {
    this.ws.send(JSON.stringify({ type: 'resize', cols, rows }));
  }

  close() {
    this.ws?.close();
  }
}

// Usage
const terminal = new TerminalConnection();
terminal.onOutput = (text) => console.log(text);
terminal.onExit = (code) => console.log(`Exited with code ${code}`);

await terminal.connect();
terminal.resize(120, 40);
terminal.sendInput('echo "Hello from Code Puppy!"\n');
```

#### Events Connection

```javascript
class EventsConnection {
  constructor(url = 'ws://localhost:8000/ws/events') {
    this.url = url;
    this.ws = null;
    this.handlers = new Map();
  }

  connect() {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        console.log('Events WebSocket connected');
        resolve();
      };

      this.ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        
        // Ignore pings
        if (msg.type === 'ping') return;
        
        // Call registered handler for this event type
        const handler = this.handlers.get(msg.type);
        handler?.(msg);
        
        // Also call wildcard handlers
        this.handlers.get('*')?.(msg);
      };

      this.ws.onerror = reject;
    });
  }

  on(eventType, handler) {
    this.handlers.set(eventType, handler);
    return this; // chainable
  }

  close() {
    this.ws?.close();
  }
}

// Usage
const events = new EventsConnection();
await events.connect();

events
  .on('tool_call_start', (e) => {
    console.log(`🔧 Tool starting: ${e.data.tool_name}`);
  })
  .on('tool_call_complete', (e) => {
    const status = e.data.success ? '✅' : '❌';
    console.log(`${status} Tool finished: ${e.data.tool_name} (${e.data.duration_ms}ms)`);
  })
  .on('stream_event', (e) => {
    process.stdout.write(e.data.event_data?.text || '');
  })
  .on('*', (e) => {
    // Log all events for debugging
    console.debug('Event:', e.type, e.id);
  });
```

#### Health Check

```javascript
async function checkHealth(url = 'ws://localhost:8000/ws/health', timeout = 5000) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url);
    const timer = setTimeout(() => {
      ws.close();
      reject(new Error('Health check timeout'));
    }, timeout);

    ws.onopen = () => ws.send('ping');
    
    ws.onmessage = (event) => {
      clearTimeout(timer);
      ws.close();
      resolve(event.data === 'echo: ping');
    };

    ws.onerror = (error) => {
      clearTimeout(timer);
      reject(error);
    };
  });
}

// Usage
const isHealthy = await checkHealth();
console.log(`Server healthy: ${isHealthy}`);
```

---

### Python

#### Using `websockets` Library

```python
import asyncio
import json
import base64
from websockets import connect


async def terminal_session():
    """Interactive terminal session example."""
    async with connect("ws://localhost:8000/ws/terminal") as ws:
        # Wait for session confirmation
        msg = json.loads(await ws.recv())
        if msg["type"] == "session":
            print(f"Session started: {msg['id']}")
        
        # Resize terminal
        await ws.send(json.dumps({"type": "resize", "cols": 120, "rows": 40}))
        
        # Send a command
        await ws.send(json.dumps({"type": "input", "data": "echo 'Hello from Python!'\n"}))
        
        # Read output
        while True:
            msg = json.loads(await ws.recv())
            
            if msg["type"] == "output":
                decoded = base64.b64decode(msg["data"]).decode("utf-8")
                print(decoded, end="")
            
            elif msg["type"] == "exit":
                print(f"\nProcess exited with code {msg['code']}")
                break


async def events_stream():
    """Stream events from the agent."""
    async with connect("ws://localhost:8000/ws/events") as ws:
        async for message in ws:
            event = json.loads(message)
            
            if event.get("type") == "ping":
                continue
            
            event_type = event.get("type")
            data = event.get("data", {})
            
            if event_type == "tool_call_start":
                print(f"🔧 Starting: {data.get('tool_name')}")
            
            elif event_type == "tool_call_complete":
                status = "✅" if data.get("success") else "❌"
                print(f"{status} Completed: {data.get('tool_name')} ({data.get('duration_ms'):.1f}ms)")
            
            elif event_type == "agent_invoked":
                print(f"🤖 Sub-agent: {data.get('agent_name')}")


async def health_check() -> bool:
    """Check WebSocket connectivity."""
    try:
        async with connect("ws://localhost:8000/ws/health") as ws:
            await ws.send("ping")
            response = await asyncio.wait_for(ws.recv(), timeout=5.0)
            return response == "echo: ping"
    except Exception:
        return False


if __name__ == "__main__":
    # Run examples
    asyncio.run(health_check())
    # asyncio.run(terminal_session())
    # asyncio.run(events_stream())
```

#### Using `websocket-client` (Synchronous)

```python
import json
import base64
from websocket import create_connection


def simple_terminal_command(command: str) -> str:
    """Execute a single command and return output."""
    ws = create_connection("ws://localhost:8000/ws/terminal")
    output = []
    
    try:
        # Wait for session
        msg = json.loads(ws.recv())
        assert msg["type"] == "session"
        
        # Send command
        ws.send(json.dumps({"type": "input", "data": f"{command}\nexit\n"}))
        
        # Collect output
        while True:
            msg = json.loads(ws.recv())
            
            if msg["type"] == "output":
                decoded = base64.b64decode(msg["data"]).decode("utf-8")
                output.append(decoded)
            
            elif msg["type"] == "exit":
                break
    finally:
        ws.close()
    
    return "".join(output)


result = simple_terminal_command("ls -la")
print(result)
```

---

### curl / websocat

#### Health Check with curl

```bash
# Note: curl's WebSocket support is limited
# For full WebSocket testing, use websocat

# Install websocat (macOS)
brew install websocat

# Install websocat (Linux)
cargo install websocat
# or download from https://github.com/vi/websocat/releases
```

#### Health Check with websocat

```bash
# Simple echo test
echo "ping" | websocat ws://localhost:8000/ws/health
# Output: echo: ping

# Interactive health check
websocat ws://localhost:8000/ws/health
# Type messages, see echoes
```

#### Events Stream with websocat

```bash
# Stream all events (pretty-printed)
websocat ws://localhost:8000/ws/events | jq .

# Filter for tool calls only
websocat ws://localhost:8000/ws/events | jq 'select(.type | startswith("tool_call"))'

# Show just tool names as they execute
websocat ws://localhost:8000/ws/events | \
  jq -r 'select(.type == "tool_call_start") | "🔧 " + .data.tool_name'
```

#### Terminal with websocat

```bash
# Interactive terminal (basic - no resize support)
websocat -t ws://localhost:8000/ws/terminal

# Note: For full terminal experience, use the web UI or a proper client
# websocat doesn't handle JSON framing automatically

# Send a command programmatically
echo '{"type": "input", "data": "ls\n"}' | websocat ws://localhost:8000/ws/terminal
```

---

## Error Handling

### Common Error Scenarios

| Scenario | WebSocket Event | Handling |
|----------|----------------|----------|
| Server unavailable | `onerror` + `onclose` | Retry with backoff |
| Connection dropped | `onclose` (code 1006) | Reconnect immediately |
| Server restart | `onclose` (code 1001) | Reconnect with backoff |
| Invalid message | N/A (server ignores) | Log and continue |
| Terminal process dies | `exit` message | Show exit code, close gracefully |

### Close Codes

| Code | Meaning | Action |
|------|---------|--------|
| 1000 | Normal closure | No action needed |
| 1001 | Going away (server shutdown) | Reconnect with backoff |
| 1006 | Abnormal closure | Reconnect immediately |
| 1011 | Server error | Reconnect with longer backoff |
| 1012 | Service restart | Wait, then reconnect |

### Error Handling Example

```javascript
class RobustWebSocket {
  constructor(url, options = {}) {
    this.url = url;
    this.maxRetries = options.maxRetries ?? 10;
    this.baseDelay = options.baseDelay ?? 1000;
    this.maxDelay = options.maxDelay ?? 30000;
    this.retries = 0;
    this.ws = null;
  }

  connect() {
    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      console.log('Connected');
      this.retries = 0; // Reset on successful connection
      this.onConnect?.();
    };

    this.ws.onclose = (event) => {
      console.log(`Closed: ${event.code}`);
      
      if (event.code === 1000) {
        // Normal closure, don't reconnect
        return;
      }
      
      this.scheduleReconnect();
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      // onclose will fire after onerror
    };

    this.ws.onmessage = (event) => {
      this.onMessage?.(event.data);
    };
  }

  scheduleReconnect() {
    if (this.retries >= this.maxRetries) {
      console.error('Max retries reached');
      this.onMaxRetries?.();
      return;
    }

    // Exponential backoff with jitter
    const delay = Math.min(
      this.baseDelay * Math.pow(2, this.retries) + Math.random() * 1000,
      this.maxDelay
    );
    
    console.log(`Reconnecting in ${delay}ms (attempt ${this.retries + 1})`);
    this.retries++;
    
    setTimeout(() => this.connect(), delay);
  }

  close() {
    this.maxRetries = 0; // Prevent reconnection
    this.ws?.close(1000);
  }
}
```

---

## Reconnection Strategies

### Strategy 1: Exponential Backoff (Recommended)

```javascript
function getBackoffDelay(attempt, baseMs = 1000, maxMs = 30000) {
  const exponential = baseMs * Math.pow(2, attempt);
  const jitter = Math.random() * 1000;
  return Math.min(exponential + jitter, maxMs);
}

// Delays: ~1s, ~2s, ~4s, ~8s, ~16s, ~30s (capped)
```

### Strategy 2: Immediate + Backoff

First retry immediately (connection hiccup), then use backoff:

```javascript
function getReconnectDelay(attempt) {
  if (attempt === 0) return 0; // Immediate first retry
  return getBackoffDelay(attempt - 1);
}
```

### Strategy 3: Connection-Specific

```javascript
const strategies = {
  terminal: {
    // Terminals need fast reconnection
    baseDelay: 500,
    maxRetries: 20,
  },
  events: {
    // Events can tolerate slower reconnection
    baseDelay: 2000,
    maxRetries: Infinity, // Always try
  },
  health: {
    // Health checks shouldn't retry
    maxRetries: 1,
  },
};
```

### Heartbeat / Keep-Alive

For `/ws/events`, the server sends pings every 30s. For `/ws/terminal`, implement client-side heartbeat:

```javascript
class HeartbeatWebSocket {
  constructor(ws, intervalMs = 25000) {
    this.ws = ws;
    this.intervalMs = intervalMs;
    this.timer = null;
  }

  start() {
    this.timer = setInterval(() => {
      if (this.ws.readyState === WebSocket.OPEN) {
        // Send empty input as heartbeat (terminal-specific)
        this.ws.send(JSON.stringify({ type: 'input', data: '' }));
      }
    }, this.intervalMs);
  }

  stop() {
    clearInterval(this.timer);
  }
}
```

---

## Configuration

### Frontend Emitter Settings

The `/ws/events` endpoint is powered by the `frontend_emitter` plugin. Configure it in your agent setup:

```python
from code_puppy.plugins.frontend_emitter import FrontendEmitterPlugin

# Create with custom settings
emitter = FrontendEmitterPlugin(
    buffer_size=100,      # Number of recent events to send on connect
    ping_interval=30.0,   # Seconds between keep-alive pings
)

# Register with your agent
agent.register_plugin(emitter)
```

| Setting | Default | Description |
|---------|---------|-------------|
| `buffer_size` | 100 | Events kept for catch-up on new connections |
| `ping_interval` | 30.0 | Seconds of idle before sending ping |

### Server Configuration

The web server is configured via environment variables or programmatically:

```bash
# Environment variables
export CODE_PUPPY_HOST=0.0.0.0
export CODE_PUPPY_PORT=8000
```

```python
# Programmatic configuration
from api.server import run_server

run_server(
    host="0.0.0.0",
    port=8000,
    # WebSocket settings are handled by the underlying ASGI server
)
```

### Nginx Proxy Configuration

If running behind Nginx, ensure WebSocket support:

```nginx
location /ws/ {
    proxy_pass http://localhost:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_read_timeout 86400; # 24 hours for long-lived connections
}
```

---

## Quick Reference

### Terminal Commands Cheat Sheet

```javascript
// Run a command
ws.send(JSON.stringify({ type: 'input', data: 'ls -la\n' }));

// Ctrl+C (interrupt)
ws.send(JSON.stringify({ type: 'input', data: '\x03' }));

// Ctrl+D (EOF/exit)
ws.send(JSON.stringify({ type: 'input', data: '\x04' }));

// Ctrl+Z (suspend)
ws.send(JSON.stringify({ type: 'input', data: '\x1a' }));

// Ctrl+L (clear screen)
ws.send(JSON.stringify({ type: 'input', data: '\x0c' }));

// Arrow keys (for shells with readline)
ws.send(JSON.stringify({ type: 'input', data: '\x1b[A' })); // Up
ws.send(JSON.stringify({ type: 'input', data: '\x1b[B' })); // Down
ws.send(JSON.stringify({ type: 'input', data: '\x1b[C' })); // Right
ws.send(JSON.stringify({ type: 'input', data: '\x1b[D' })); // Left

// Tab completion
ws.send(JSON.stringify({ type: 'input', data: '\t' }));
```

---

**Happy WebSocket-ing! 🐶**

*Need help? Open an issue on GitHub or ping us in discussions.*
