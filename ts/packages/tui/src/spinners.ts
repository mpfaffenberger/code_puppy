/**
 * Context-aware spinner glyphs — the visual half of the spinner-verb pools.
 *
 * Design principle (from Hux's lynx-agent-spinners): a single global spinner
 * says nothing; a distinctive glyph per activity makes the timeline legible
 * at a glance. Each VerbContext gets a semantically matched braille animation:
 *
 *   study  → scan       a bar sweeping across (searching/reading)
 *   edit   → fillsweep  cells filling up (writing)
 *   shell  → cascade    output tumbling out (executing)
 *   general→ sparkle    Mist's signature shimmer (thinking/planning)
 *
 * Frames are sourced from lynx-agent-spinners (MIT) and normalized to a fixed
 * 4-cell width so the status line never shifts when the context switches.
 * Each spinner keeps its native interval — pacing is part of the character.
 */

import type { VerbContext } from "./spinnerVerbs";

export interface Spinner {
  frames: readonly string[];
  /** ms per frame */
  interval: number;
}

const B = "⠀"; // braille blank — same advance width as the animated cells

export const SPINNERS: Record<VerbContext, Spinner> = {
  general: {
    // sparkle — the existing Mist signature (unchanged)
    frames: ["⡡⠊⢔⠡", "⠊⡰⡡⡘", "⢔⢅⠈⢢", "⡁⢂⠆⡍", "⢔⠨⢑⢐", "⠨⡑⡠⠊"],
    interval: 150,
  },
  study: {
    // scan — a reading head sweeping the line
    frames: [`⡇${B}${B}${B}`, `⣿${B}${B}${B}`, `⢸⡇${B}${B}`, `${B}⣿${B}${B}`, `${B}⢸⡇${B}`, `${B}${B}⣿${B}`, `${B}${B}⢸⡇`, `${B}${B}${B}⣿`, `${B}${B}${B}⢸`],
    interval: 70,
  },
  edit: {
    // fillsweep — cells filling and draining, centered in the 4-cell slot
    frames: [`${B}⣀⣀${B}`, `${B}⣤⣤${B}`, `${B}⣶⣶${B}`, `${B}⣿⣿${B}`, `${B}⣿⣿${B}`, `${B}⣶⣶${B}`, `${B}⣤⣤${B}`, `${B}⣀⣀${B}`, `${B}${B}${B}${B}`],
    interval: 100,
  },
  shell: {
    // cascade — output tumbling left-to-right
    frames: [`⠁${B}${B}${B}`, `⠋${B}${B}${B}`, `⠞⠁${B}${B}`, `⡴⠋${B}${B}`, `⣠⠞⠁${B}`, `⢀⡴⠋${B}`, `${B}⣠⠞⠁`, `${B}⢀⡴⠋`, `${B}${B}⣠⠞`, `${B}${B}⢀⡴`, `${B}${B}${B}⣠`, `${B}${B}${B}⢀`],
    interval: 60,
  },
};

export function spinnerFor(context: VerbContext): Spinner {
  return SPINNERS[context];
}
