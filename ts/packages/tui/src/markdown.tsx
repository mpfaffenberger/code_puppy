/**
 * Minimal, tasteful markdown → Ink renderer for agent responses.
 *
 * Deliberately small (headers, bold, inline code, bullets, fenced code,
 * links-as-text) — we control every pixel instead of inheriting a theme from
 * marked-terminal. Renders line-by-line so a future token-streaming engine
 * (Phase 2 `text.delta`) can reuse it incrementally.
 */

import { Box, Text } from "ink";
import React from "react";
import { theme } from "./theme";

/** Split a line into styled inline segments (bold / inline code / plain). */
function renderInline(line: string, keyBase: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  // Tokenize on **bold** and `code` spans.
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(line)) !== null) {
    if (m.index > last) {
      out.push(<Text key={`${keyBase}-p${i++}`}>{line.slice(last, m.index)}</Text>);
    }
    const tok = m[0];
    if (tok.startsWith("**")) {
      out.push(
        <Text key={`${keyBase}-b${i++}`} bold>
          {tok.slice(2, -2)}
        </Text>,
      );
    } else {
      out.push(
        <Text key={`${keyBase}-c${i++}`} color={theme.code}>
          {tok.slice(1, -1)}
        </Text>,
      );
    }
    last = m.index + tok.length;
  }
  if (last < line.length) {
    out.push(<Text key={`${keyBase}-t${i++}`}>{line.slice(last)}</Text>);
  }
  return out.length ? out : [<Text key={`${keyBase}-e`}> </Text>];
}

export function Markdown({ source }: { source: string }): React.ReactElement {
  const lines = source.replaceAll("\r\n", "\n").split("\n");
  const blocks: React.ReactNode[] = [];
  let inFence = false;
  let blankRun = 0;

  lines.forEach((raw, idx) => {
    const key = `md-${idx}`;
    if (raw.trimStart().startsWith("```")) {
      inFence = !inFence;
      blankRun = 0;
      return; // fence markers themselves are chrome, not content
    }
    if (inFence) {
      blocks.push(
        <Text key={key} color={theme.code}>
          {"  "}
          {raw}
        </Text>,
      );
      return;
    }
    const line = raw.trimEnd();
    if (!line.trim()) {
      blankRun += 1;
      if (blankRun === 1) blocks.push(<Text key={key}> </Text>); // collapse runs
      return;
    }
    blankRun = 0;
    const h = line.match(/^(#{1,4})\s+(.*)$/);
    if (h) {
      blocks.push(
        <Text key={key} bold color={theme.brand}>
          {h[2]}
        </Text>,
      );
      return;
    }
    const bullet = line.match(/^(\s*)[-*]\s+(.*)$/);
    if (bullet) {
      blocks.push(
        <Text key={key}>
          {bullet[1]}
          <Text color={theme.accent}>• </Text>
          {renderInline(bullet[2] ?? "", key)}
        </Text>,
      );
      return;
    }
    blocks.push(<Text key={key}>{renderInline(line, key)}</Text>);
  });

  return <Box flexDirection="column">{blocks}</Box>;
}
