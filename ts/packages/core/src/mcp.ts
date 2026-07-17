/**
 * MCP (Model Context Protocol) client manager — connects to external tool
 * servers over stdio/SSE/HTTP, lists their tools, and exposes them to the
 * engine tool belt under a namespaced prefix (Python parity: prefix =
 * server name, or `{serverName}_{tool_prefix}` when configured).
 *
 * Config source: `~/.mist/mcp_servers.json` — the SAME file + schema the
 * Python app reads, so existing user configs work with zero migration.
 *
 *   { "mcp_servers": { "fs": { "type": "stdio", "command": "npx",
 *       "args": ["-y","@modelcontextprotocol/server-filesystem","/tmp"] } } }
 *
 * Reliability (minimal, per backlog §2): connect with timeout, restart-on-
 * crash. Circuit-breaker/health-monitor deferred until real usage demands it.
 */

import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { join, dirname } from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { SSEClientTransport } from "@modelcontextprotocol/sdk/client/sse.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import type { ToolSpec } from "./models";

// ---- Config shape (mcp_servers.json — Python-compatible) -------------------

export interface McpServerConfig {
  type: "stdio" | "sse" | "http";
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  cwd?: string;
  url?: string;
  headers?: Record<string, string>;
  timeout?: number;
  read_timeout?: number;
  tool_prefix?: string;
  /** Convenience toggles (default enabled=true). */
  enabled?: boolean;
  auto_start?: boolean;
}

export interface McpServersFile {
  mcp_servers: Record<string, McpServerConfig>;
}

export function defaultMcpServersPath(): string {
  const xdg = process.env.XDG_CONFIG_HOME;
  const base = xdg ? join(xdg, "mist") : join(homedir(), ".mist");
  return join(base, "mcp_servers.json");
}

/** Read + validate mcp_servers.json. Missing file → empty config (not an error). */
export async function loadMcpServers(path = defaultMcpServersPath()): Promise<McpServersFile> {
  try {
    const raw = await readFile(path, "utf8");
    const parsed = JSON.parse(raw) as Partial<McpServersFile>;
    return { mcp_servers: parsed.mcp_servers ?? {} };
  } catch (e) {
    if ((e as NodeJS.ErrnoException).code === "ENOENT") return { mcp_servers: {} };
    throw new Error(`failed to read ${path}: ${(e as Error).message}`);
  }
}

/** Atomic write (temp + rename) so concurrent readers never see a partial file. */
export async function saveMcpServers(file: McpServersFile, path = defaultMcpServersPath()): Promise<void> {
  await mkdir(dirname(path), { recursive: true });
  const tmp = `${path}.tmp`;
  await writeFile(tmp, JSON.stringify(file, null, 2), "utf8");
  await rename(tmp, path);
}

// ---- Env-var expansion ($VAR / ${VAR}) in all config string fields --------

function expandVars(s: string): string {
  return s.replace(/\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?/g, (_, name) => process.env[name] ?? "");
}

function expandConfig(cfg: McpServerConfig): McpServerConfig {
  const out: McpServerConfig = { ...cfg, type: cfg.type };
  if (cfg.command) out.command = expandVars(cfg.command);
  if (cfg.args) out.args = cfg.args.map(expandVars);
  if (cfg.env) out.env = Object.fromEntries(Object.entries(cfg.env).map(([k, v]) => [k, expandVars(v)]));
  if (cfg.url) out.url = expandVars(cfg.url);
  if (cfg.headers) out.headers = Object.fromEntries(Object.entries(cfg.headers).map(([k, v]) => [k, expandVars(v)]));
  if (cfg.cwd) out.cwd = expandVars(cfg.cwd);
  return out;
}

// ---- Tool prefix (Python parity) -------------------------------------------

export function toolPrefix(serverName: string, cfg: McpServerConfig): string {
  const configured = cfg.tool_prefix ? expandVars(cfg.tool_prefix) : "";
  return configured ? `${serverName}_${configured}` : serverName;
}

/** Build the namespaced tool name the LLM sees: `{prefix}_{toolName}`. */
export function namespacedToolName(prefix: string, toolName: string): string {
  return `${prefix}_${toolName}`;
}

// ---- A single managed MCP server -------------------------------------------

export type ServerStatus = "stopped" | "starting" | "running" | "error";

export interface ManagedServer {
  name: string;
  status: ServerStatus;
  tools: McpToolSpec[];
  client: Client | null;
  close: () => Promise<void>;
}

export interface McpToolSpec extends ToolSpec {
  /** Original MCP tool name (without the namespace prefix). */
  mcpName: string;
  server: string;
}

/** Validate a server config; throws on missing required fields. */
export function validateConfig(name: string, cfg: McpServerConfig): void {
  if (cfg.type === "stdio") {
    if (!cfg.command) throw new Error(`mcp server '${name}' (stdio) requires 'command'`);
  } else if (cfg.type === "sse" || cfg.type === "http") {
    if (!cfg.url) throw new Error(`mcp server '${name}' (${cfg.type}) requires 'url'`);
  } else {
    throw new Error(`mcp server '${name}' has invalid type '${cfg.type as string}'`);
  }
}

const CONNECT_TIMEOUT_MS = 30_000;

/** Connect to one MCP server, list its tools, return a ManagedServer. */
export async function connectServer(
  name: string,
  rawCfg: McpServerConfig,
): Promise<ManagedServer> {
  validateConfig(name, rawCfg);
  const cfg = expandConfig(rawCfg);
  const prefix = toolPrefix(name, rawCfg);

  const client = new Client(
    { name: "mist", version: "0.1.0" },
    { capabilities: {} },
  );

  let transport: StdioClientTransport | SSEClientTransport | StreamableHTTPClientTransport;
  if (cfg.type === "stdio") {
    transport = new StdioClientTransport({
      command: cfg.command!,
      args: cfg.args ?? [],
      env: cfg.env ? { ...process.env, ...cfg.env } : undefined,
      cwd: cfg.cwd,
    });
  } else if (cfg.type === "sse") {
    transport = new SSEClientTransport(new URL(cfg.url!), {
      requestInit: { headers: cfg.headers },
    });
  } else {
    transport = new StreamableHTTPClientTransport(new URL(cfg.url!), {
      requestInit: { headers: cfg.headers },
    });
  }

  // Connect with a timeout — never hang forever on a misconfigured server.
  await withTimeout(client.connect(transport), CONNECT_TIMEOUT_MS, name);

  const listed = await client.listTools();
  const tools: McpToolSpec[] = (listed.tools ?? []).map((t) => ({
    name: namespacedToolName(prefix, t.name),
    mcpName: t.name,
    server: name,
    description: t.description ?? "",
    input_schema: (t.inputSchema as Record<string, unknown>) ?? { type: "object", properties: {} },
  }));

  const managed: ManagedServer = {
    name,
    status: "running",
    tools,
    client,
    async close() {
      managed.status = "stopped";
      try {
        await client.close();
      } catch {
        // best-effort
      }
      await transport.close?.().catch(() => {});
    },
  };
  // Wire liveness: without these, status stays "running" forever and the
  // restart-on-crash watchdog can never fire (nor allTools() stop advertising
  // a dead server's tools).
  client.onclose = () => {
    if (managed.status === "running") managed.status = "error";
  };
  client.onerror = () => {
    if (managed.status === "running") managed.status = "error";
  };
  return managed;
}

function withTimeout<T>(p: Promise<T>, ms: number, name: string): Promise<T> {
  let timer: ReturnType<typeof setTimeout>;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Error(`mcp server '${name}' connect timed out after ${ms}ms`)), ms);
  });
  return Promise.race([p, timeout]).finally(() => clearTimeout(timer!)) as Promise<T>;
}

// ---- Manager: owns the live server set, restart-on-crash -------------------

export class McpManager {
  private servers = new Map<string, ManagedServer>();
  private configs: Record<string, McpServerConfig> = {};
  private restarts = new Map<string, number>();

  /** Load config + auto-start enabled servers (best-effort, never throws). */
  async loadAndStart(path = defaultMcpServersPath()): Promise<{ started: string[]; failed: { name: string; error: string }[] }> {
    const file = await loadMcpServers(path);
    this.configs = file.mcp_servers;
    const started: string[] = [];
    const failed: { name: string; error: string }[] = [];
    for (const [name, cfg] of Object.entries(this.configs)) {
      if (cfg.enabled === false) continue;
      if (!cfg.auto_start) continue;
      try {
        const s = await connectServer(name, cfg);
        this.servers.set(name, s);
        started.push(name);
      } catch (e) {
        failed.push({ name, error: (e as Error).message });
      }
    }
    return { started, failed };
  }

  async start(name: string): Promise<void> {
    const cfg = this.configs[name];
    if (!cfg) throw new Error(`unknown mcp server '${name}'`);
    if (this.servers.has(name)) return;
    const s = await connectServer(name, cfg);
    this.servers.set(name, s);
  }

  async stop(name: string): Promise<void> {
    const s = this.servers.get(name);
    if (!s) return;
    await s.close();
    this.servers.delete(name);
  }

  async restart(name: string): Promise<void> {
    await this.stop(name);
    this.restarts.set(name, (this.restarts.get(name) ?? 0) + 1);
    await this.start(name);
  }

  /** Restart a server that crashed (called from a watchdog). */
  async restartIfCrashed(name: string): Promise<boolean> {
    const s = this.servers.get(name);
    if (!s || s.status === "running") return false;
    try {
      await this.restart(name);
      return true;
    } catch {
      return false;
    }
  }

  /** All tools from all running servers, ready to merge into the engine belt. */
  allTools(): McpToolSpec[] {
    const out: McpToolSpec[] = [];
    for (const s of this.servers.values()) {
      if (s.status === "running") out.push(...s.tools);
    }
    return out;
  }

  /** Dispatch a tool call to the owning server. */
  async callTool(namespacedName: string, input: Record<string, unknown>): Promise<unknown> {
    const s = this.findOwner(namespacedName);
    if (!s || !s.client) throw new Error(`mcp tool '${namespacedName}' is not connected`);
    const result = await s.client.callTool({ name: s.tools.find((t) => t.name === namespacedName)!.mcpName, arguments: input });
    return result;
  }

  private findOwner(namespacedName: string): ManagedServer | undefined {
    for (const s of this.servers.values()) {
      if (s.tools.some((t) => t.name === namespacedName)) return s;
    }
    return undefined;
  }

  status(): { name: string; status: ServerStatus; tools: number; restarts: number }[] {
    return [...this.servers.values()].map((s) => ({
      name: s.name,
      status: s.status,
      tools: s.tools.length,
      restarts: this.restarts.get(s.name) ?? 0,
    }));
  }

  configsList(): { name: string; type: string; enabled: boolean }[] {
    return Object.entries(this.configs).map(([name, cfg]) => ({
      name,
      type: cfg.type,
      enabled: cfg.enabled !== false,
    }));
  }

  async stopAll(): Promise<void> {
    await Promise.all([...this.servers.keys()].map((n) => this.stop(n)));
  }
}
