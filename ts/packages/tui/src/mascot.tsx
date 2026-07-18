/**
 * The Mist mascot — a crow in a witch hat, as terminal pixel art.
 *
 * Front-facing and STRICTLY symmetric (every grid row mirrors), in the
 * chunky few-color style that makes Anthropic's Clawd read so cleanly:
 * flat colors, big features, solid silhouette, no stray pixels. Charcoal
 * witch hat with green band + gold buckle, slate crow body, two big eyes,
 * orange beak, lighter chest.
 *
 * Rendered with half-block glyphs: each terminal cell shows TWO vertical
 * pixels (▀ foreground = top pixel, background = bottom pixel).
 */

import { Box, Text } from "ink";
import React from "react";

const PALETTE: Record<string, string> = {
  H: "#262c40", // hat charcoal
  G: "#48603c", // hat band green
  U: "#d4af5a", // buckle gold
  B: "#3d4560", // crow slate
  E: "#e8eef7", // eye white
  P: "#10141f", // pupil
  K: "#e09040", // beak orange
  L: "#8b96ad", // chest
};

// 20 × 18 pixel grid ('.' = transparent) — every row is a mirror image.
const GRID = [
  ".........HH.........",
  "........HHHH........",
  "........HHHH........",
  ".......HHHHHH.......",
  ".......HHHHHH.......",
  "......HGGGGGGH......",
  "......HGGUUGGH......",
  "..HHHHHHHHHHHHHHHH..",
  ".HHHHHHHHHHHHHHHHHH.",
  ".....BBBBBBBBBB.....",
  "....BEEEBBBBEEEB....",
  "....BEPEBBBBEPEB....",
  "....BEEEBKKBEEEB....",
  "....BBBBBKKBBBBB....",
  ".....BBBBBBBBBB.....",
  "....BBLLLLLLLLBB....",
  "....BBLLLLLLLLBB....",
  ".....BBBBBBBBBB.....",
];

export function Mascot(): React.JSX.Element {
  const rows: React.JSX.Element[] = [];
  for (let y = 0; y < GRID.length; y += 2) {
    const top = GRID[y] ?? "";
    const bottom = GRID[y + 1] ?? "";
    const cells: React.JSX.Element[] = [];
    const width = Math.max(top.length, bottom.length);
    for (let x = 0; x < width; x++) {
      const t = PALETTE[top[x] ?? "."];
      const b = PALETTE[bottom[x] ?? "."];
      if (t && b) cells.push(<Text key={x} color={t} backgroundColor={b}>▀</Text>);
      else if (t) cells.push(<Text key={x} color={t}>▀</Text>);
      else if (b) cells.push(<Text key={x} color={b}>▄</Text>);
      else cells.push(<Text key={x}> </Text>);
    }
    rows.push(<Text key={y}>{cells}</Text>);
  }
  return <Box flexDirection="column">{rows}</Box>;
}
