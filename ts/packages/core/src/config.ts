/**
 * Engine configuration — reads Mist's existing config surface so the Bun
 * engine is a drop-in: `~/.mist/mist.cfg` ([mist] model = …) and the
 * `models.json` model registry (repo copy or `~/.mist/models.json`).
 *
 * `/set` and `/show` read/write the same flat key=value pairs in [mist].
 */

import { homedir } from "node:os";
import { join } from "node:path";
import { readFile, writeFile, mkdir } from "node:fs/promises";

export interface ModelDef {
  name: string;
  type: string;
  provider?: string;
  context_length?: number;
  custom_endpoint?: { url: string; api_key?: string; timeout?: number };
}

/** Path to ~/.mist/mist.cfg (the [mist] section shared with Python Mist). */
export function mistCfgPath(): string {
  const home = process.env.HOME || homedir();
  return join(home, ".mist", "mist.cfg");
}

async function readIni(path: string): Promise<Record<string, string>> {
  try {
    const text = await readFile(path, "utf8");
    return parseIni(text);
  } catch {
    return {};
  }
}

function parseIni(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line || line.startsWith("#") || line.startsWith("[")) continue;
    const eq = line.indexOf("=");
    if (eq < 0) continue;
    out[line.slice(0, eq).trim()] = line.slice(eq + 1).trim();
  }
  return out;
}

/** Read all key=value pairs from the [mist] section of mist.cfg. */
export async function readConfig(): Promise<Record<string, string>> {
  return readIni(mistCfgPath());
}

/** Read one setting; returns undefined if not set. */
export async function getConfig(key: string): Promise<string | undefined> {
  const cfg = await readConfig();
  return cfg[key];
}

/**
 * Write one key=value into ~/.mist/mist.cfg. Creates the file if missing,
 * preserves other keys and comments. Atomic (temp + rename).
 */
export async function setConfig(key: string, value: string): Promise<void> {
  const path = mistCfgPath();
  let text: string;
  try {
    text = await readFile(path, "utf8");
  } catch {
    text = "[mist]\n";
  }
  const lines = text.split("\n");
  let replaced = false;
  const out = lines.map((l) => {
    const trimmed = l.trim();
    if (trimmed.startsWith(`${key} =`) || trimmed.startsWith(`${key}=`)) {
      replaced = true;
      return `${key} = ${value}`;
    }
    return l;
  });
  if (!replaced) {
    // Insert after the [mist] header, or at the top if missing.
    const headerIdx = out.findIndex((l) => l.trim() === "[mist]");
    if (headerIdx >= 0) out.splice(headerIdx + 1, 0, `${key} = ${value}`);
    else out.unshift("[mist]", `${key} = ${value}`);
  }
  const dir = join(path, "..");
  await mkdir(dir, { recursive: true });
  const tmp = `${path}.tmp`;
  await writeFile(tmp, out.join("\n"), "utf8");
  await import("node:fs/promises").then((fs) => fs.rename(tmp, path));
}

/** Known /set keys and their validators (for the interactive menu). */
export const SETTING_DEFS: {
  key: string;
  label: string;
  desc: string;
  validate?: (v: string) => string | null;
}[] = [
  {
    key: "verbosity",
    label: "verbosity",
    desc: "output verbosity (quiet · normal · verbose)",
    validate: (v) => (["quiet", "normal", "verbose"].includes(v) ? null : "must be quiet|normal|verbose"),
  },
  {
    key: "reasoning",
    label: "reasoning",
    desc: "reasoning effort (off · low · medium · high)",
    validate: (v) => (["off", "low", "medium", "high"].includes(v) ? null : "must be off|low|medium|high"),
  },
  {
    key: "temperature",
    label: "temperature",
    desc: "model temperature (0.0–2.0)",
    validate: (v) => {
      const n = Number(v);
      return Number.isFinite(n) && n >= 0 && n <= 2 ? null : "must be a number 0–2";
    },
  },
  {
    key: "max_tokens",
    label: "max_tokens",
    desc: "max output tokens per request",
    validate: (v) => {
      const n = Number(v);
      return Number.isFinite(n) && n > 0 ? null : "must be a positive number";
    },
  },
  {
    key: "auto_compact_at",
    label: "auto_compact_at",
    desc: "token threshold for auto-compaction",
    validate: (v) => {
      const n = Number(v);
      return Number.isFinite(n) && n > 0 ? null : "must be a positive number";
    },
  },
];

export async function getConfiguredModelName(): Promise<string> {
  if (process.env.MIST_MODEL) return process.env.MIST_MODEL;
  const cfg = await readIni(join(homedir(), ".mist", "mist.cfg"));
  return cfg["model"] || "minimax-m3";
}

// Resolved lazily so MIST_MODELS_JSON set after import (tests, wrappers) works.
function modelsJsonCandidates(): string[] {
  return [
    process.env.MIST_MODELS_JSON,
    join(homedir(), ".mist", "extra_models.json"), // user-added models (matches Python ModelFactory precedence)
    join(homedir(), ".mist", "models.json"),
    // Repo checkout (dev): ts/packages/core/src → ../../../../code_puppy/models.json
    new URL("../../../../code_puppy/models.json", import.meta.url).pathname,
  ].filter(Boolean) as string[];
}

export async function getModelDef(name: string): Promise<ModelDef> {
  for (const candidate of modelsJsonCandidates()) {
    try {
      const all = (await Bun.file(candidate).json()) as Record<string, Omit<ModelDef, "name">>;
      const def = all[name];
      if (def) return { name, ...def } as ModelDef;
    } catch {
      /* next candidate */
    }
  }
  throw new Error(`model '${name}' not found in models.json (${modelsJsonCandidates().join(", ")})`);
}

/** Persist the chosen model into ~/.mist/mist.cfg (shared with Python Mist). */
export async function persistModelChoice(name: string): Promise<void> {
  await setConfig("model", name);
}

/** All model names known to the registry files (deduped, config order). */
export async function listModelNames(): Promise<string[]> {
  const names: string[] = [];
  for (const candidate of modelsJsonCandidates()) {
    try {
      const all = (await Bun.file(candidate).json()) as Record<string, unknown>;
      for (const key of Object.keys(all)) if (!names.includes(key)) names.push(key);
    } catch {
      /* next */
    }
  }
  return names;
}
