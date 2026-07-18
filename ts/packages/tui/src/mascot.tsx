/**
 * The Mist mascot — a crow in a witch hat, as terminal pixel art.
 *
 * Side profile from the character sheet: gray-blue crow facing left, big
 * orange beak, green eye, charcoal witch hat (green band, gold buckle,
 * crooked tip), slate wing folded behind a lighter chest.
 *
 * Rendered with half-block glyphs: each terminal cell shows TWO vertical
 * pixels (▀ foreground = top pixel, background = bottom pixel) — the same
 * technique Claude Code uses for its banner robot.
 */

import { Box, Text } from "ink";
import React from "react";

const PALETTE: Record<string, string> = {
  H: "#2b3247", // hat charcoal
  h: "#3d4663", // hat highlight
  G: "#3f5a36", // hat band green
  U: "#c9a24b", // buckle gold
  K: "#d98a3f", // beak orange
  k: "#b06a2a", // beak shadow
  F: "#8fa3b8", // face gray-blue
  f: "#6b7f96", // face shade
  C: "#a8b4c4", // chest light
  c: "#7d8899", // chest shade
  W: "#4a5468", // wing slate
  w: "#343c50", // wing dark
  E: "#b8d94a", // eye green
  P: "#232a3d", // eye socket
};

// 24 × 20 pixel grid ('.' = transparent). Two grid rows per terminal row.
const GRID = [
  "..............wHw.......",
  ".............wHHh.......",
  "...........wHHHHh.......",
  "..........HHHHHh........",
  ".........HHHHHHh........",
  ".........HGGGGGh........",
  "........HHGUUGGHh.......",
  "....HHHHHHHHHHHHHHHh....",
  "..hHHHHHHHHHHHHHHHHHH...",
  "........FFFFFFFFf.......",
  ".......FFFFFFPPPff......",
  "...KKKKFFFFFFPEPff......",
  ".KKKKKKKFFFFFPPPff......",
  ".KKKKKKkFFFFFFFFff......",
  "..KKKKkFFFFFFFFfWW......",
  "....KkFFFFFFFFfWWWw.....",
  ".....CCCCCCCCcfWWWWw....",
  "....CCCCCCCCCcWWWWWw....",
  "....CCCCCCCCCcWWWWww....",
  "...cCCCCCCCCCcwwwww.....",
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
