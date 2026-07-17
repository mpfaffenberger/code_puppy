/**
 * Misty — the Mist mascot, as terminal pixel art.
 *
 * The ghost is drawn on a pixel grid and rendered with half-block glyphs:
 * each terminal cell shows TWO vertical pixels (▀ foreground = top pixel,
 * background = bottom pixel), the same technique Claude Code uses for its
 * banner robot. Truecolor hexes are taken straight from the character sheet:
 * a blue-gray cloud body deepening toward the tail, mint arc on the crown,
 * navy eyes, soft highlight.
 */

import { Box, Text } from "ink";
import React from "react";

const PALETTE: Record<string, string> = {
  G: "#8fd9c4", // mint crown arc
  w: "#f2f6fc", // wisp / shine
  H: "#dce6f5", // highlight
  L: "#b9c9e4", // light body
  M: "#9db0d2", // mid body
  B: "#7d8fb8", // lower body
  D: "#5d6f9e", // tail
  E: "#232a4d", // eyes
  S: "#5c6890", // smile
};

// 20 × 16 pixel grid ('.' = transparent). Two grid rows per terminal row.
const GRID = [
  "....GG...w..........",
  "..GG.HHHLLLL........",
  "..G.HHLLLLLLLL......",
  "...HLLELLLLELLL.....",
  "...LLLELLLLELLL.....",
  "...LLLLLSSLLLLL.....",
  "..MLLLLLLLLLLLLM....",
  ".MMMLLLLLLLLLLMMM...",
  "MMM.MLLLLLLLLM.MMM..",
  ".M...MMMMMMMM....M..",
  "......MMMMMMM.......",
  "......BMMMMMB.......",
  ".......BBMMBB.......",
  "........BBBD........",
  ".........DDD........",
  ".......D..DD........",
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
