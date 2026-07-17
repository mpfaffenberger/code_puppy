/**
 * Minimal, tasteful markdown → Ink renderer for agent responses.
 *
 * Handles: headers, bold, inline code, bullets, fenced code, blank-run
 * collapse, **pipe tables**, and **file-path highlighting** (violet), so
 * model output like gap analyses renders as structure, not pipe-soup.
 *
 * Tables render two ways:
 *  - compact (≤3 columns, short cells)  → aligned grid with dim separators
 *  - prose-heavy                        → stacked "cards": first cell becomes
 *    the row title, remaining cells render as `Header: value` lines. Far more
 *    readable in a terminal than a squeezed wide grid.
 */

import { Box, Text } from "ink";
import React from "react";
import { theme } from "./theme";

// Path-ish tokens: dir/file.ext, dir/sub/, file.ext:123 — needs a slash or
// an extension+line to avoid recoloring ordinary prose.
const PATH_RE = /(?:[\w.-]+\/[\w./-]+(?::\d+)?|[\w-]+\.[a-z]{1,4}:\d+|[\w./-]*\/(?:[\w.-]+)?)/;

function looksLikePath(token: string): boolean {
  if (!token || token.length < 3) return false;
  if (token.includes("//") && token.includes(":")) return false; // urls keep code color
  return /\//.test(token) || /\.[a-z]{1,4}:\d+$/.test(token);
}

/** Split a line into styled inline segments (bold / code / paths / plain). */
function renderInline(line: string, keyBase: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;

  const pushPlain = (text: string) => {
    // Within plain text, pull out path-looking tokens for violet highlighting.
    let rest = text;
    while (rest.length) {
      const pm = rest.match(PATH_RE);
      if (!pm || pm.index === undefined || !looksLikePath(pm[0])) {
        out.push(<Text key={`${keyBase}-t${i++}`}>{rest}</Text>);
        return;
      }
      if (pm.index > 0) {
        out.push(<Text key={`${keyBase}-t${i++}`}>{rest.slice(0, pm.index)}</Text>);
      }
      out.push(
        <Text key={`${keyBase}-f${i++}`} color={theme.path}>
          {pm[0]}
        </Text>,
      );
      rest = rest.slice(pm.index + pm[0].length);
    }
  };

  while ((m = re.exec(line)) !== null) {
    if (m.index > last) pushPlain(line.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith("**")) {
      out.push(
        <Text key={`${keyBase}-b${i++}`} bold>
          {tok.slice(2, -2)}
        </Text>,
      );
    } else {
      const inner = tok.slice(1, -1);
      out.push(
        <Text key={`${keyBase}-c${i++}`} color={looksLikePath(inner) ? theme.path : theme.code}>
          {inner}
        </Text>,
      );
    }
    last = m.index + tok.length;
  }
  if (last < line.length) pushPlain(line.slice(last));
  return out.length ? out : [<Text key={`${keyBase}-e`}> </Text>];
}

// ---- tables -----------------------------------------------------------------

export interface ParsedTable {
  headers: string[];
  rows: string[][];
}

const isTableLine = (l: string) => l.trim().startsWith("|");
const isSeparatorLine = (l: string) => /^\s*\|[\s:|-]+\|?\s*$/.test(l) && l.includes("-");

function splitRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((c) => c.trim());
}

/** Parse consecutive pipe lines into a table (null if not a real table). */
export function parseTable(lines: string[]): ParsedTable | null {
  if (lines.length < 2 || !isSeparatorLine(lines[1] ?? "")) return null;
  const headers = splitRow(lines[0]!);
  const rows = lines
    .slice(2)
    .map(splitRow)
    .filter((r) => r.some((c) => c.length));
  return headers.length >= 2 ? { headers, rows } : null;
}

/** Compact tables → grid; prose tables → stacked cards. */
export function tableIsCompact(t: ParsedTable): boolean {
  const cells = [t.headers, ...t.rows].flat();
  return t.headers.length <= 3 && cells.every((c) => c.length <= 28);
}

function TableGrid({ t, keyBase }: { t: ParsedTable; keyBase: string }) {
  const widths = t.headers.map((h, col) =>
    Math.max(h.length, ...t.rows.map((r) => (r[col] ?? "").length)),
  );
  const pad = (s: string, w: number) => s + " ".repeat(Math.max(0, w - s.length));
  return (
    <Box flexDirection="column" marginY={0}>
      <Text>
        {t.headers.map((h, col) => (
          <Text key={`${keyBase}-h${col}`}>
            <Text bold color={theme.brand}>
              {pad(h, widths[col] ?? 0)}
            </Text>
            {col < t.headers.length - 1 ? <Text color={theme.dim}>  │  </Text> : null}
          </Text>
        ))}
      </Text>
      <Text color={theme.dim} dimColor>
        {widths.map((w) => "─".repeat(w)).join("──┼──")}
      </Text>
      {t.rows.map((row, ri) => (
        <Text key={`${keyBase}-r${ri}`}>
          {t.headers.map((_h, col) => (
            <Text key={`${keyBase}-r${ri}c${col}`}>
              {renderInline(pad(row[col] ?? "", widths[col] ?? 0), `${keyBase}-r${ri}c${col}`)}
              {col < t.headers.length - 1 ? <Text color={theme.dim}>  │  </Text> : null}
            </Text>
          ))}
        </Text>
      ))}
    </Box>
  );
}

function TableCards({ t, keyBase }: { t: ParsedTable; keyBase: string }) {
  return (
    <Box flexDirection="column">
      {t.rows.map((row, ri) => (
        <Box key={`${keyBase}-card${ri}`} flexDirection="column" marginBottom={1}>
          <Text>
            <Text color={theme.accent} bold>
              ▪{" "}
            </Text>
            <Text bold>{renderInline(row.slice(0, 2).filter(Boolean).join(" · "), `${keyBase}-ct${ri}`)}</Text>
          </Text>
          {row.slice(2).map((cell, ci) =>
            cell ? (
              <Text key={`${keyBase}-cd${ri}-${ci}`}>
                {"   "}
                <Text color={theme.dim}>{t.headers[ci + 2] ?? `col ${ci + 3}`}: </Text>
                {renderInline(cell, `${keyBase}-cv${ri}-${ci}`)}
              </Text>
            ) : null,
          )}
        </Box>
      ))}
    </Box>
  );
}

// ---- main renderer ----------------------------------------------------------

export function Markdown({ source }: { source: string }): React.ReactElement {
  const lines = source.replaceAll("\r\n", "\n").split("\n");
  const blocks: React.ReactNode[] = [];
  let inFence = false;
  let blankRun = 0;

  for (let idx = 0; idx < lines.length; idx++) {
    const raw = lines[idx]!;
    const key = `md-${idx}`;
    if (raw.trimStart().startsWith("```")) {
      inFence = !inFence;
      blankRun = 0;
      continue;
    }
    if (inFence) {
      blocks.push(
        <Text key={key} color={theme.code}>
          {"  "}
          {raw}
        </Text>,
      );
      continue;
    }
    const line = raw.trimEnd();

    // Table block: consume consecutive pipe lines.
    if (isTableLine(line)) {
      const tableLines: string[] = [];
      let j = idx;
      while (j < lines.length && isTableLine(lines[j]!.trimEnd())) {
        tableLines.push(lines[j]!.trimEnd());
        j++;
      }
      const parsed = parseTable(tableLines);
      if (parsed) {
        blocks.push(
          tableIsCompact(parsed) ? (
            <TableGrid key={key} t={parsed} keyBase={key} />
          ) : (
            <TableCards key={key} t={parsed} keyBase={key} />
          ),
        );
        idx = j - 1;
        blankRun = 0;
        continue;
      }
      // fall through: not a real table, render as text
    }

    if (!line.trim()) {
      blankRun += 1;
      if (blankRun === 1) blocks.push(<Text key={key}> </Text>);
      continue;
    }
    blankRun = 0;
    const h = line.match(/^(#{1,4})\s+(.*)$/);
    if (h) {
      blocks.push(
        <Text key={key} bold color={theme.brand}>
          {h[2]}
        </Text>,
      );
      continue;
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
      continue;
    }
    blocks.push(<Text key={key}>{renderInline(line, key)}</Text>);
  }

  return <Box flexDirection="column">{blocks}</Box>;
}
