/**
 * Training exporter tests: JSONL shape (anthropic + openai), redaction,
 * min-turns filtering.
 */

import { describe, expect, test } from "bun:test";
import { SessionStore } from "./store";
import { exportTraining, redactSecrets } from "./training_export";
import type { ChatMessage } from "./models";

async function seedSessions(cwd: string): Promise<void> {
  const store = new SessionStore(cwd);
  // A real agentic session with tool traffic and a planted secret.
  await store.create("sess1", "fix the auth bug");
  await store.appendMessages("sess1", [
    { role: "user", content: "fix the auth bug" },
    {
      role: "assistant",
      content: [
        { type: "text", text: "Reading the config first." },
        { type: "tool_use", id: "t1", name: "read_file", input: { path: ".env" } },
      ],
    },
    {
      role: "user",
      content: [
        { type: "tool_result", tool_use_id: "t1", content: "API_KEY=sk-ant-abc123def456ghi789\ndone" },
      ],
    },
    { role: "assistant", content: [{ type: "text", text: "Fixed it." }] },
  ] as ChatMessage[]);
  // An empty throwaway session (should be filtered by min-turns).
  await store.create("sess2", "(tool session)");
}

describe("training export", () => {
  test("anthropic format: one JSONL line per qualifying session, secrets redacted", async () => {
    const cwd = `/tmp/mist-train-${Date.now()}`;
    process.env.MIST_SESSIONS_DIR = `${cwd}/.sessions`;
    try {
      await seedSessions(cwd);
      const out = `${cwd}/out.jsonl`;
      const res = await exportTraining(cwd, out, { format: "anthropic" });
      expect(res.written).toBe(1);
      expect(res.skipped).toBe(1); // the empty session

      const lines = (await Bun.file(out).text()).trim().split("\n");
      expect(lines).toHaveLength(1);
      const traj = JSON.parse(lines[0]!) as {
        system: string;
        tools: { name: string }[];
        messages: ChatMessage[];
      };
      expect(traj.system).toContain("You are Mist");
      expect(traj.tools.map((t) => t.name)).toContain("shell");
      expect(traj.tools.map((t) => t.name)).toContain("invoke_subagent");
      expect(traj.messages).toHaveLength(4);
      // The planted key must be gone.
      expect(lines[0]).not.toContain("sk-ant-abc123");
      expect(lines[0]).toContain("[REDACTED_ANTHROPIC_KEY]");
    } finally {
      delete process.env.MIST_SESSIONS_DIR;
    }
  });

  test("openai format: tool_calls + role:tool shape", async () => {
    const cwd = `/tmp/mist-train-oai-${Date.now()}`;
    process.env.MIST_SESSIONS_DIR = `${cwd}/.sessions`;
    try {
      await seedSessions(cwd);
      const out = `${cwd}/out.jsonl`;
      await exportTraining(cwd, out, { format: "openai" });
      const traj = JSON.parse((await Bun.file(out).text()).trim()) as {
        tools: { type: string; function: { name: string } }[];
        messages: { role: string; tool_calls?: unknown[]; tool_call_id?: string }[];
      };
      expect(traj.tools[0]!.type).toBe("function");
      expect(traj.messages[0]!.role).toBe("system");
      const assistant = traj.messages.find((m) => m.tool_calls);
      expect(assistant).toBeTruthy();
      const toolMsg = traj.messages.find((m) => m.role === "tool");
      expect(toolMsg?.tool_call_id).toBe("t1");
    } finally {
      delete process.env.MIST_SESSIONS_DIR;
    }
  });

  test("redactSecrets scrubs common credential shapes", () => {
    const dirty = [
      "key sk-ant-api03-XXXXXXXXXXXX here",
      "openai sk-abcdefghijklmnopqrstuvwx",
      "github ghp_ABCDEFGHIJKLMNOPQRSTUVWX",
      "curl -H 'Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6'",
      '{"api_key": "super-secret-value"}',
      "aws AKIAIOSFODNN7EXAMPLE",
    ].join("\n");
    const clean = redactSecrets(dirty);
    expect(clean).not.toContain("sk-ant-api03");
    expect(clean).not.toContain("ghp_ABCDEFGH");
    expect(clean).not.toContain("super-secret-value");
    expect(clean).not.toContain("AKIAIOSFODNN7EXAMPLE");
    expect(clean).not.toContain("eyJhbGciOiJIUzI1NiIsInR5cCI6");
    expect(clean).toContain("[REDACTED_GITHUB_TOKEN]");
  });
});
