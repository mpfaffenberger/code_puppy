/**
 * MCP client tests. Pure-logic tests (config, prefix, validation, env
 * expansion) run without a server. The integration test spawns a tiny
 * in-process stdio MCP server (node script) to verify tool listing, the
 * namespace prefix, and end-to-end callTool.
 */

import { afterEach, describe, expect, test } from "bun:test";
import { mkdir, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import {
  loadMcpServers,
  saveMcpServers,
  toolPrefix,
  namespacedToolName,
  validateConfig,
  connectServer,
  McpManager,
} from "./mcp";

const tmpRoot = join(tmpdir(), `mist-mcp-test-${Date.now()}`);

async function withTmpFile<T>(fn: (path: string) => Promise<T>): Promise<T> {
  await mkdir(tmpRoot, { recursive: true });
  const path = join(tmpRoot, "mcp_servers.json");
  try {
    return await fn(path);
  } finally {
    await rm(tmpRoot, { recursive: true, force: true });
  }
}

describe("MCP config", () => {
  test("loadMcpServers: missing file → empty (not an error)", async () => {
    const file = await loadMcpServers(join(tmpRoot, "nope.json"));
    expect(file.mcp_servers).toEqual({});
  });

  test("save → load round-trip preserves entries", async () => {
    await withTmpFile(async (path) => {
      const original = {
        mcp_servers: {
          fs: {
            type: "stdio" as const,
            command: "npx",
            args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
          },
          remote: { type: "http" as const, url: "https://example.com/mcp" },
        },
      };
      await saveMcpServers(original, path);
      const loaded = await loadMcpServers(path);
      expect(loaded.mcp_servers).toEqual(original.mcp_servers);
    });
  });

  test("load tolerates file with no mcp_servers key", async () => {
    await withTmpFile(async (path) => {
      await writeFile(path, JSON.stringify({ other: {} }), "utf8");
      const loaded = await loadMcpServers(path);
      expect(loaded.mcp_servers).toEqual({});
    });
  });
});

describe("MCP tool prefix + namespacing", () => {
  test("default prefix is the server name", () => {
    expect(toolPrefix("filesystem", { type: "stdio", command: "x" })).toBe("filesystem");
  });

  test("configured tool_prefix → {server}_{prefix}", () => {
    expect(toolPrefix("fs", { type: "stdio", command: "x", tool_prefix: "v1" })).toBe("fs_v1");
  });

  test("namespaced name joins prefix + tool", () => {
    expect(namespacedToolName("filesystem", "read_file")).toBe("filesystem_read_file");
    expect(namespacedToolName("fs_v1", "read_file")).toBe("fs_v1_read_file");
  });
});

describe("MCP validateConfig", () => {
  test("stdio requires command", () => {
    expect(() => validateConfig("s", { type: "stdio" })).toThrow("command");
  });
  test("sse requires url", () => {
    expect(() => validateConfig("s", { type: "sse" })).toThrow("url");
  });
  test("http requires url", () => {
    expect(() => validateServerUrl("http")).toThrow("url");
  });
  test("rejects unknown type", () => {
    // @ts-expect-error testing runtime guard against bad input
    expect(() => validateConfig("s", { type: "weird" })).toThrow("invalid type");
  });
  test("accepts valid stdio", () => {
    expect(() => validateConfig("s", { type: "stdio", command: "npx", args: ["-y", "x"] })).not.toThrow();
  });
});

function validateServerUrl(t: string): void {
  // @ts-expect-error incomplete shape on purpose
  validateConfig("s", { type: t });
}

// ---- Integration: spawn a real stdio MCP server in-process ----------------

const MCP_ECHO_SERVER = `
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { ListToolsRequestSchema, CallToolRequestSchema } from "@modelcontextprotocol/sdk/types.js";

const server = new Server({ name: "echo", version: "1.0.0" }, { capabilities: { tools: {} } });

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [{
    name: "echo",
    description: "Echoes input",
    inputSchema: { type: "object", properties: { msg: { type: "string" } }, required: ["msg"] }
  }]
}));

server.setRequestHandler(CallToolRequestSchema, async (req) => ({
  content: [{ type: "text", text: "echo: " + (req.params.arguments?.msg ?? "") }]
}));

const transport = new StdioServerTransport();
await server.connect(transport);
`;

describe("MCP connectServer (integration)", () => {
  test("lists tools with namespace prefix and calls them", async () => {
    // Write the echo server to a temp .mjs file.
    const serverPath = join(tmpRoot, "echo_server.mjs");
    await mkdir(tmpRoot, { recursive: true });
    await writeFile(serverPath, MCP_ECHO_SERVER, "utf8");

    const managed = await connectServer("echo", {
      type: "stdio",
      command: process.execPath,
      args: [serverPath],
      timeout: 15,
    });

    expect(managed.status).toBe("running");
    expect(managed.tools).toHaveLength(1);
    expect(managed.tools[0]!.name).toBe("echo_echo");
    expect(managed.tools[0]!.mcpName).toBe("echo");

    // callTool via the manager dispatch.
    const mgr = new McpManager();
    // Inject the already-connected server for dispatch.
    (mgr as unknown as { servers: Map<string, typeof managed> }).servers.set("echo", managed);
    const result = await mgr.callTool("echo_echo", { msg: "hello" });
    const text = (result as { content: { text: string }[] }).content[0]!.text;
    expect(text).toBe("echo: hello");

    await managed.close();
    await rm(tmpRoot, { recursive: true, force: true });
  }, 20000);
});
