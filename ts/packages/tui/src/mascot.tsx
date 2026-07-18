/**
 * The Mist mascot — an owl caricature (Owlgebra AI), as terminal pixel art.
 *
 * Drawn on a pixel grid and rendered with half-block glyphs: each terminal
 * cell shows TWO vertical pixels (▀ foreground = top pixel, background =
 * bottom pixel), the same technique Claude Code uses for its banner robot.
 * Palette from the character sheet: blue body deepening at the wings, light
 * face/belly, big amber eyes with white glints, yellow beak + talons on a
 * brown branch, sparkles in the margins.
 */

import { Box, Text } from "ink";
import React from "react";

const PALETTE: Record<string, string> = {
  D: "#2a4db8", // deep blue — tufts, wing edges
  B: "#5b8dd9", // mid blue — head, wings
  L: "#aecdf0", // light blue — face, belly
  A: "#f0a821", // amber iris
  W: "#ffffff", // eye glint
  P: "#20264d", // pupil
  Y: "#f6c445", // beak + talons
  T: "#7a5230", // branch
  S: "#7b8fe8", // sparkles
};

// 22 × 18 pixel grid ('.' = transparent). Two grid rows per terminal row.
const GRID = [
  "..DB....S.....S...BD..",
  "..BDB..BBBBBBBB..BDB..",
  "S.BBBBBBBBBBBBBBBBBB.S",
  ".BBLLLLLLBBBBLLLLLLBB.",
  ".BLLAAAALLBBLLAAAALLB.",
  ".BLAWPAALLBBLLAAPWALB.",
  ".BLLAAAALLYYLLAAAALLB.",
  ".BBLLLLLLLYYLLLLLLLBB.",
  "..DBLLLLLLLLLLLLLLBD..",
  "..DBLLBLLBLLBLLBLLBD.S",
  "..DBLLLLLLLLLLLLLLBD..",
  "S.DBBLLLLLLLLLLLLBBD..",
  "...DBBLLLLLLLLLLBBD...",
  "....DBBLLLLLLLLBBD....",
  "......YYY....YYY......",
  ".TTTTTTTTTTTTTTTTTTTT.",
  ".........DLLD.........",
  "..........DD..........",
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
