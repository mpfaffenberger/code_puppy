/**
 * Hooks — user/project-defined guardrails that steer the agent and keep it
 * from regressing on the project's intent.
 *
 * Config: `.mist/hooks.json` in the project cwd (wins) merged over
 * `~/.mist/hooks.json`. Shape:
 *
 * {
 *   "intent": "One paragraph of durable project vision. Injected into the
 *              system prompt every turn so long tasks never drift.",
 *   "pre_tool": [
 *     { "tool": "shell", "pattern": "docker\\s+push|kubectl\\s+apply",
 *       "action": "block", "message": "No deploys from the agent." },
 *     { "tool": "*", "pattern": "secrets?\\.env", "action": "warn",
 *       "message": "Touching secrets — double-check." }
 *   ]
 * }
 */

import { homedir } from "node:os";
import { join } from "node:path";

export interface PreToolRule {
  tool: string; // tool name or "*"
  pattern: string; // regex tested against JSON.stringify(input)
  action: "block" | "warn";
  message: string;
}

export interface Hooks {
  intent?: string;
  pre_tool: PreToolRule[];
}

async function readJson(path: string): Promise<Partial<Hooks> | null> {
  try {
    return (await Bun.file(path).json()) as Partial<Hooks>;
  } catch {
    return null;
  }
}

export async function loadHooks(cwd: string): Promise<Hooks> {
  const user = await readJson(join(homedir(), ".mist", "hooks.json"));
  const project = await readJson(join(cwd, ".mist", "hooks.json"));
  return {
    intent: project?.intent ?? user?.intent,
    pre_tool: [...(user?.pre_tool ?? []), ...(project?.pre_tool ?? [])],
  };
}

export interface HookVerdict {
  action: "block" | "warn";
  message: string;
}

export function applyPreToolHooks(
  hooks: Hooks,
  toolName: string,
  input: unknown,
): HookVerdict | null {
  const haystack = JSON.stringify(input ?? {});
  for (const rule of hooks.pre_tool) {
    if (rule.tool !== "*" && rule.tool !== toolName) continue;
    try {
      if (new RegExp(rule.pattern, "i").test(haystack)) {
        return { action: rule.action, message: rule.message };
      }
    } catch {
      /* invalid regex in config — never break the run */
    }
  }
  return null;
}
