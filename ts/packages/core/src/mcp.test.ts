/**
 * MCP manager integration test: spawns a real in-process MCP server over stdio
 * (using the SDK's Server + StdioServerTransport), connects the McpManager,
 * and verifies tool namespacing + call dispatch end-to-end.
 *
 * The server is a tiny "echo" server exposing one tool: `greet(name) -> str`.
 */

import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { spawn } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { McpManager, loadMcpServers, saveMcpServers, toolPrefix, namespacedToolName } from "./mcp";

// A minimal MCP server script the child process runs. Uses the high-level
// McpServer API (registerTool) which is the simplest stable surface.
// A minimal MCP server script the child process runs. Uses the low-level
// Server API with the schema constants (ListToolsRequestSchema /
// CallToolRequestSchema) which accept plain JSON-Schema input shapes.
const SERVER_SCRIPT = `
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { ListToolsRequestSchema, CallToolRequestSchema } from "@modelcontextprotocol/sdk/types.js";
const server = new Server({ name: "echo", version: "0.0.1" }, { capabilities: { tools: {} } });
server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [{
    name: "greet",
    description: "Greet someone",
    inputSchema: { type: "object", properties: { name: { type: "string" } }, required: ["name"] }
  }]
}));
server.setRequestHandler(CallToolRequestSchema, async (req) => ({
  content: [{ type: "text", text: "hello " + (req.params.arguments?.name ?? "?") }]
}));
const transport = new StdioServerTransport();
await server.connect(transport);
`;

let tmpDir: string;
let serverPath: string;

beforeEach(() => {
  tmpDir = mkdtempSync(join(tmpdir(), "mist-mcp-test-"));
  serverPath = join(tmpDir, "echo-server.js");
  writeFileSync(serverPath, SERVER_SCRIPT);
});

afterEach(() => {
  // best-effort cleanup; processes self-exit on test teardown
});

describe("McpManager (stdio transport, real subprocess)", () => {
  test("connects, lists namespaced tools, and dispatches a call", async () => {
    const manager = new McpManager();
    // Inject config directly via the internal field, then start.
    (manager as unknown as { configs: Record<string, unknown> }).configs = {
      echo: {
        type: "stdio",
        command: "bun",
        args: ["run", serverPath],
        timeout: 15,
      },
    };
    await manager.start("echo");

    const tools = manager.allTools();
    expect(tools).toHaveLength(1);
    expect(tools[0]!.name).toBe("echo_greet");
    expect(tools[0]!.mcpName).toBe("greet");
    expect(tools[0]!.server).toBe("echo");

    const result = await manager.callTool("echo_greet", { name: "world" });
    const text = (result as { content: { type: string; text: string }[] }).content[0]!.text;
    expect(text).toBe("hello world");

    await manager.stopAll();
  }, 20000);

  test("reports status and restarts", async () => {
    const manager = new McpManager();
    (manager as unknown as { configs: Record<string, unknown> }).configs = {
      echo: { type: "stdio", command: "bun", args: ["run", serverPath], timeout: 15 },
    };
    await manager.start("echo");
    const before = manager.status();
    expect(before[0]!.name).toBe("echo");
    expect(before[0]!.status).toBe("running");
    expect(before[0]!.tools).toBe(1);

    await manager.restart("echo");
    const after = manager.status();
    expect(after[0]!.status).toBe("running");
    expect(after[0]!.tools).toBe(1);
    await manager.stopAll();
  }, 20000);
});

describe("mcp_servers.json config layer", () => {
  test("loadMcpServers returns empty for missing file", async () => {
    const result = await loadMcpServers(join(tmpDir, "nope.json"));
    expect(result.mcp_servers).toEqual({});
  });

  test("saveMcpServers + loadMcpServers round-trips the Python schema", async () => {
    const path = join(tmpDir, "mcp_servers.json");
    const file = {
      mcp_servers: {
        fs: {
          type: "stdio",
          command: "npx",
          args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
          env: { FOO: "$HOME" },
        },
        remote: { type: "http", url: "https://example.com/mcp", headers: { Authorization: "Bearer $KEY" } },
      },
    };
    await saveMcpServers(file, path);
    const loaded = await loadMcpServers(path);
    expect(loaded.mcp_servers.fs.type).toBe("stdio");
    expect(loaded.mcp_servers.fs.command).toBe("npx");
    expect(loaded.mcp_servers.remote.type).toBe("http");
    expect(loaded.mcp_servers.remote.url).toBe("https://example.com/mcp");
  });

  test("toolPrefix defaults to server name; honors tool_prefix", () => {
    expect(toolPrefix("fs", { type: "stdio", command: "x" })).toBe("fs");
    expect(toolPrefix("fs", { type: "stdio", command: "x", tool_prefix: "v2" })).toBe("fs_v2");
  });

  test("namespacedToolName joins prefix + tool", () => {
    expect(namespacedToolName("echo", "greet")).toBe("echo_greet");
  });
});
