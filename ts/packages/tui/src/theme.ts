/**
 * Mist visual language — named, runtime-switchable themes.
 *
 * `theme` is a mutable object components read at render time; `applyTheme`
 * swaps its values in place (callers bump a state tick to re-render). The
 * chosen theme persists to ~/.mist/ts-settings.json.
 *
 * - "mist": the pastel brand ramp (Regent St Blue → We Peep) on cool neutrals.
 * - "cinnamon": the warm autumn palette ported from the Python TUI
 *   (cinnamon / pumpkin / butterscotch / milky tan / creamsicle).
 * - "hinokami": Sun Breathing / Hinokami Kagura — Tanjiro's checkered
 *   green-black, Yoriichi's crimson + gold sun crest, flame-arc oranges on
 *   warm parchment. Firelight, not a stock dark theme. A theme may also
 *   carry its own spinner `verbs` (hinokami announces Sun Breathing forms).
 */

import { homedir } from "node:os";
import { join } from "node:path";

export interface Theme {
  name: string;
  ramp: readonly string[]; // brand-lockup letter gradient
  brand: string;
  accent: string;
  text: string;
  dim: string;
  success: string;
  warning: string;
  error: string;
  code: string;
  path: string; // file/dir names — distinct so they pop
  border: string;
  user: string;
  /** Theme-specific spinner verbs — replaces the standard pools when set. */
  verbs?: readonly string[];
}

export const THEMES: Record<string, Theme> = {
  mist: {
    name: "mist",
    ramp: ["#a8d3e1", "#b3e4e6", "#ebf7f9", "#e5b8d1", "#f2cad4"],
    brand: "#a8d3e1",
    accent: "#e5b8d1",
    text: "#e8edf7",
    dim: "#8a93a6",
    success: "#df9241",
    warning: "#d47007",
    error: "#ff6b6b",
    code: "#b3e4e6",
    path: "#a78bfa",
    border: "#5b6478",
    user: "#f2cad4",
  },
  cinnamon: {
    name: "cinnamon",
    ramp: ["#ffecd1", "#f2bd7e", "#df9241", "#d47007", "#7d4e00"],
    brand: "#df9241",
    accent: "#d47007",
    text: "#ffecd1",
    dim: "#c4a59d",
    success: "#e0b067",
    warning: "#d47007",
    error: "#ff6b6b",
    code: "#f2bd7e",
    path: "#b794f4",
    border: "#7d4e00",
    user: "#ffecd1",
  },
  hinokami: {
    name: "hinokami",
    // Flame arc: deep red → crimson → orange → gold → yellow-gold
    ramp: ["#7A1F1F", "#C23B3B", "#FF7A29", "#F2A93C", "#FFC94A"],
    brand: "#FF7A29", // Sun Breathing orange (cursor/functions)
    accent: "#F2A93C", // gold sun crest
    text: "#E9E4D8", // warm parchment — firelight, not white
    dim: "#8B8778",
    success: "#7FA86E", // muted sage green (git added)
    warning: "#F2A93C",
    error: "#C23B3B", // Yoriichi's crimson
    code: "#E8927A", // ember (strings)
    path: "#FFC94A", // bright gold — pops on the green-black
    border: "#4A5442", // checkered-haori sage
    user: "#FFC94A",
    verbs: [
      "Dance",
      "Clear Blue Sky",
      "Raging Sun",
      "Fake Rainbow",
      "Fire Wheel",
      "Burning Bones, Summer Sun",
      "Solar Heat Haze",
      "Sunflower Thrust",
      "Setting Sun Transformation",
      "Beneficent Radiance",
      "Dragon Sun Halo Head Dance",
      "Flame Dance",
    ],
  },
};

// The live theme — mutated in place so every module sees switches instantly.
export const theme: Theme = { ...THEMES.mist! };

const SETTINGS_PATH = () =>
  process.env.MIST_TS_SETTINGS ?? join(homedir(), ".mist", "ts-settings.json");

export function applyTheme(name: string): boolean {
  const next = THEMES[name];
  if (!next) return false;
  Object.assign(theme, next);
  theme.verbs = next.verbs; // explicit — clears a previous theme's override
  return true;
}

export async function persistTheme(name: string): Promise<void> {
  try {
    const path = SETTINGS_PATH();
    const existing = await Bun.file(path)
      .json()
      .catch(() => ({}));
    await Bun.write(path, JSON.stringify({ ...existing, theme: name }, null, 2));
  } catch {
    /* persistence is best-effort */
  }
}

export async function loadPersistedTheme(): Promise<void> {
  try {
    const settings = (await Bun.file(SETTINGS_PATH()).json()) as { theme?: string };
    if (settings.theme) applyTheme(settings.theme);
  } catch {
    /* defaults are fine */
  }
}

/** Per-letter gradient color for the brand lockup. */
export function rampColor(i: number, total: number): string {
  const ramp = theme.ramp;
  if (total <= 1) return ramp[0]!;
  const t = i / (total - 1);
  const idx = Math.min(ramp.length - 1, Math.round(t * (ramp.length - 1)));
  return ramp[idx]!;
}

export const HEARTBEAT = ["○", "◔", "◑", "◕", "●", "◕", "◑", "◔"] as const;
