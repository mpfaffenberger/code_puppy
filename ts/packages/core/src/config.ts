/**
 * Engine configuration — reads Mist's existing config surface so the Bun
 * engine is a drop-in: `~/.mist/mist.cfg` ([mist] model = …) and the
 * `models.json` model registry (repo copy or `~/.mist/models.json`).
 */

import { homedir } from "node:os";
import { join } from "node:path";

export interface ModelDef {
  name: string;
  type: string;
  provider?: string;
  context_length?: number;
  custom_endpoint?: { url: string; api_key?: string; timeout?: number };
}

async function readIni(path: string): Promise<Record<string, string>> {
  try {
    const text = await Bun.file(path).text();
    const out: Record<string, string> = {};
    for (const raw of text.split("\n")) {
      const line = raw.trim();
      if (!line || line.startsWith("#") || line.startsWith("[")) continue;
      const eq = line.indexOf("=");
      if (eq < 0) continue;
      out[line.slice(0, eq).trim()] = line.slice(eq + 1).trim();
    }
    return out;
  } catch {
    return {};
  }
}

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
  const path = join(homedir(), ".mist", "mist.cfg");
  try {
    const text = await Bun.file(path)
      .text()
      .catch(() => "[mist]\n");
    const lines = text.split("\n");
    let replaced = false;
    const out = lines.map((l) => {
      if (l.trim().startsWith("model =") || l.trim().startsWith("model=")) {
        replaced = true;
        return `model = ${name}`;
      }
      return l;
    });
    if (!replaced) out.splice(1, 0, `model = ${name}`);
    await Bun.write(path, out.join("\n"));
  } catch {
    /* best-effort */
  }
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
