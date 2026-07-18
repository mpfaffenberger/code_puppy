/**
 * The Mist mascot — a simple mist-cloud blob ("Misty"), as terminal pixel
 * art. Clawd-style minimalism: ONE body color, dot eyes, rosy cheeks, a tiny
 * mouth, cloud-puff base. Strictly symmetric, 3 colors, 16×12 grid — small
 * enough that nothing can read as noise.
 *
 * Rendered with half-block glyphs: each terminal cell shows TWO vertical
 * pixels (▀ foreground = top pixel, background = bottom pixel).
 */

import { Box, Text } from "ink";
import React from "react";

const PALETTE: Record<string, string> = {
  M: "#a5c3e8", // mist blue
  P: "#232a3d", // eyes + mouth
  R: "#e8a0b4", // rosy cheeks
};

// 12 × 10 pixel grid ('.' = transparent) — every row is a mirror image.
const GRID = [
  "...MMMMMM...",
  ".MMMMMMMMMM.",
  ".MPPMMMMPPM.",
  ".MPPMMMMPPM.",
  "MMMMMPPMMMMM",
  "MMRMMMMMMRMM",
  ".MMMMMMMMMM.",
  ".MMMMMMMMMM.",
  "..MMMMMMMM..",
  "..MM.MM.MM..",
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
